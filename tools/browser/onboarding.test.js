import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {webcrypto} from 'node:crypto';
import {md5} from 'hash-wasm';
import crc32 from 'pako/lib/zlib/crc32.js';
import {readFileSync} from 'node:fs';
const profile=JSON.parse(readFileSync('../../firmware/profiles/waveshare-7b-stock-v1.json'));
const contract={profile_id:profile.id,profile_version:profile.version,layout_id:profile.layout.id,firmware_lineage:profile.firmware_lineage};
if(!globalThis.crypto)globalThis.crypto=webcrypto;
await build({stdin:{contents:'export {Transport, ESPLoader} from "esptool-js"; export * from "./reset.js"; export * from "./audit.js"; export * from "./install.js"; export * from "./review.js"; export * from "./baselines.js"; export * from "./recovery.js"; export * from "./reinstall.js"; export * from "./c6-probe.js"; export * from "./commissioning.js";',resolveDir:process.cwd()},bundle:true,platform:'node',format:'esm',outfile:'build/test-api.mjs'});
const api=await import('./build/test-api.mjs');
const {parseTable,STOCK,matchesStock,decodeSecurity,readChunk,openReader,selectBoot,verifyRelease,executePlan,sha256,FLASH_BYTES}=api;
function record(seq,state=2,index=0){const b=new Uint8Array(8192).fill(255),v=new DataView(b.buffer);v.setUint32(index*4096,seq,true);v.setUint32(index*4096+24,state,true);v.setUint32(index*4096+28,crc32(-1,b,4,index*4096)>>>0,true);return b;}
async function table(entries=STOCK){const b=new Uint8Array(4096).fill(255),v=new DataView(b.buffer);entries.forEach(([name,type,subtype,offset,size],i)=>{const at=i*32;b.fill(0,at,at+32);v.setUint16(at,0x50aa,true);b[at+2]=type;b[at+3]=subtype;v.setUint32(at+4,offset,true);v.setUint32(at+8,size,true);b.set(new TextEncoder().encode(name),at+12);});const end=entries.length*32;v.setUint16(end,0xebeb,true);b.set(Uint8Array.from((await md5(b.slice(0,end))).match(/../g),h=>parseInt(h,16)),end+16);return b;}
function security(){const b=new Uint8Array(20);new DataView(b.buffer).setUint32(12,18,true);return b;}

test('MD5-verified stock layout and malformed/overlapping tables fail closed',async()=>{
  const good=await table();assert.ok(matchesStock(await parseTable(good)));
  const corrupt=good.slice();corrupt[10]^=1;await assert.rejects(parseTable(corrupt));
  await assert.rejects(parseTable(await table([...STOCK.slice(0,1),['overlap',1,2,0x9000,4096]])));
  await assert.rejects(parseTable(await table([['outside',0,0,0x2000000,4096]])));
  const flags=good.slice();new DataView(flags.buffer).setUint32(28,1,true);await assert.rejects(parseTable(flags));
});

test('security rejects unknown, protected, wrong-chip and truncated responses',()=>{
  assert.equal(decodeSecurity(security()).flash_crypt_cnt,0);
  for(const index of [0,4,12]){const bytes=security();bytes[index]^=1;assert.throws(()=>decodeSecurity(bytes));}
  assert.throws(()=>decodeSecurity(new Uint8Array(12)));
});

test('reader refuses protection before RAM stub upload and closes connection',async()=>{
  const calls=[];
  class Transport{async disconnect(){calls.push('close');}}
  class Loader{constructor(){this.chip={CHIP_NAME:'ESP32-P4',getChipRevision:async()=>103};}async connect(){} async checkCommand(){const b=security();b[4]=1;return b;}async runStub(){calls.push('stub');}}
  await assert.rejects(openReader({}, {Loader,SerialTransport:Transport}));assert.deepEqual(calls,['close']);
});

test('bounded flash transfer verifies final MD5 and rejects short/oversize packets',async()=>{
  const data=new Uint8Array(4096).fill(42),digest=Uint8Array.from((await md5(data)).match(/../g),h=>parseInt(h,16));
  for(const [packets,ok] of [[[data,digest],true],[[data,new Uint8Array(16)],false],[[data.slice(0,4000)],false],[[new Uint8Array(8192)],false]]){
    const reader={loader:{ESP_READ_FLASH:0xd2,checkCommand:async()=>{}},transport:{read:async()=>packets.shift(),write:async()=>{}}};
    if(ok)assert.deepEqual(await readChunk(reader,0,4096),data);else await assert.rejects(readChunk(reader,0,4096));
  }
});

test('cancelled read sends no command',async()=>{const c=new AbortController();c.abort();await assert.rejects(readChunk({loader:{}},0,4096,c.signal),{name:'AbortError'});});

test('boot selection targets inactive metadata sector with Espressif CRC and preserves old record',()=>{
  const old=record(5),copy=old.slice(),next=selectBoot(old),v=new DataView(next.bytes.buffer);
  assert.deepEqual(old,copy);assert.equal(next.offset,0x10e000);assert.equal(v.getUint32(0,true),6);assert.equal(v.getUint32(24,true),0);
  assert.equal(v.getUint32(28,true),crc32(-1,next.bytes,4,0)>>>0);
  assert.equal(new DataView(selectBoot(new Uint8Array(8192).fill(255)).bytes.buffer).getUint32(0,true),2);
  for(const data of [record(2),record(1,0),record(1,1),record(1,9),new Uint8Array(8192)])assert.throws(()=>selectBoot(data));
});

async function signed(policy){const key=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']),payload=new TextEncoder().encode(JSON.stringify(policy));return {status:'reviewed-development-release',minimum_sequence:1,release_id:await sha256(payload),publisher_key:Buffer.from(await crypto.subtle.exportKey('raw',key.publicKey)).toString('hex'),envelope:{payload:Buffer.from(payload).toString('base64'),signature:Buffer.from(await crypto.subtle.sign('Ed25519',key.privateKey,payload)).toString('base64')}};}
const policy=JSON.parse(readFileSync('../../tests/fixtures/initial-release-v2.json'));
test('only signed, unexpired and complete release policies pass',async()=>{
  const good=await signed(policy);assert.equal((await verifyRelease(good)).profile,policy.profile);
  good.envelope.payload=Buffer.from('{}').toString('base64');await assert.rejects(verifyRelease(good));
  for(const change of [{compatibility:undefined},{compatibility:{...contract,profile_id:'waveshare-p4-4b'}},{compatibility:{...contract,profile_version:2}},{compatibility:{...contract,layout_id:'other-layout'}},{compatibility:{...contract,firmware_lineage:'other-firmware'}},{installable:false},{expires_at:'2000-01-01'},{c6_review:''},{app:{...policy.app,offset:0x110000}}])await assert.rejects(verifyRelease(await signed({...policy,...change})));
});

test('USB verifier rejects OTA purpose, stale sequence, changed identity and missing provenance',async()=>{
  for(const change of [{purpose:'ota',installable:false},{sequence:true},{sequence:0},{schema:1},{provenance:{}},{extra:'unknown'}])
    await assert.rejects(verifyRelease(await signed({...policy,...change})));
  const stale=await signed(policy);stale.minimum_sequence=policy.sequence+1;await assert.rejects(verifyRelease(stale));
  const changed=await signed(policy);changed.release_id='0'.repeat(64);await assert.rejects(verifyRelease(changed));
});

test('installer refuses missing consent or invalid regions before any serial command',async()=>{
  await assert.rejects(executePlan({}, {},policy,{}));
  await assert.rejects(executePlan({}, {profile:policy.profile,app_sha256:policy.app.sha256,writes:[{offset:0x8000,bytes:new Uint8Array(4096)}]},policy,{exact_plan:true,separate_copy:true,rom_recovery:true}));
});

test('a matching P4 chip cannot substitute for owner-confirmed board identity',async()=>{
  for(const model of [undefined,'waveshare-esp32-p4-wifi6-touch-lcd-4b']) {
    await assert.rejects(api.makePlan({}, {owner_confirmed_profile:model},policy,new Uint8Array()),{code:'model_unconfirmed'});
  }
  await assert.rejects(executePlan({}, {},{...policy,compatibility:{...contract,profile_id:'waveshare-esp32-p4-wifi6-touch-lcd-4b'}},
    {exact_plan:true,separate_copy:true,rom_recovery:true}),{code:'profile_contract_mismatch'});
});

function flashFixture(flash,{failAppReadback=false}={}) {
  let pending=[];const writes=[],reads=[];
  const reader={loader:{ESP_READ_FLASH:0xd2,checkCommand:async(_,op,payload)=>{
    const v=new DataView(payload.buffer),readAt=v.getUint32(0,true),readSize=v.getUint32(4,true);
    reads.push({offset:readAt,size:readSize});
    const bytes=flash.slice(readAt,readAt+readSize);
    if(failAppReadback&&writes.length&&readAt>=0xe00000&&readAt<0x11f0000)bytes[0]^=1;
    pending=[];for(let at=0;at<bytes.length;at+=4096)pending.push(bytes.slice(at,at+4096));
    pending.push(Uint8Array.from((await md5(bytes)).match(/../g),h=>parseInt(h,16)));
  },writeFlash:async options=>{
    assert.equal(options.eraseAll,false);assert.equal(options.flashMode,'keep');assert.equal(options.fileArray.length,1);
    const item=options.fileArray[0];writes.push(item.address);flash.set(item.data,item.address);
  },after:async()=>writes.push('reset')},transport:{read:async()=>pending.shift(),write:async()=>{}}};
  return {reader,writes,reads};
}

test('app is read back before boot selection; failed verification never writes otadata',async()=>{
  for(const failAppReadback of [false,true]) {
    const flash=new Uint8Array(FLASH_BYTES).fill(255),app=new Uint8Array(4096).fill(42),selection=selectBoot(flash.slice(0x10d000,0x10f000));
    const plan={profile:policy.profile,backup_sha256:await sha256(flash),app_sha256:policy.app.sha256,
      writes:[{offset:0xe00000,bytes:app,sha256:await sha256(app)},{offset:selection.offset,bytes:selection.bytes,sha256:await sha256(selection.bytes)}]};
    const {reader,writes}=flashFixture(flash,{failAppReadback});
    const action=executePlan(reader,plan,policy,{exact_plan:true,separate_copy:true,rom_recovery:true});
    if(failAppReadback){await assert.rejects(action);assert.deepEqual(writes,[0xe00000]);}
    else{assert.equal((await action).physical_startup_verified,false);assert.deepEqual(writes,[0xe00000,0x10d000,'reset']);assert.ok(flash.slice(0x2000,0x9000).every(b=>b===255));}
  }
});

test('changed physical flash blocks writes even with a matching release',async()=>{
  const flash=new Uint8Array(FLASH_BYTES).fill(255),selection=selectBoot(flash.slice(0x10d000,0x10f000)),app=new Uint8Array(4096);
  const plan={profile:policy.profile,backup_sha256:'0'.repeat(64),app_sha256:policy.app.sha256,writes:[{offset:0xe00000,bytes:app,sha256:await sha256(app)},{offset:selection.offset,bytes:selection.bytes,sha256:await sha256(selection.bytes)}]};
  const {reader,writes}=flashFixture(flash);
  await assert.rejects(executePlan(reader,plan,policy,{exact_plan:true,separate_copy:true,rom_recovery:true}));assert.deepEqual(writes,[]);
});

test('revocation during full comparison prevents the first flash write',async()=>{
  const flash=new Uint8Array(FLASH_BYTES).fill(255),app=new Uint8Array(4096).fill(42);
  const selection=selectBoot(flash.slice(0x10d000,0x10f000));
  const plan={profile:policy.profile,backup_sha256:await sha256(flash),app_sha256:policy.app.sha256,
    writes:[{offset:0xe00000,bytes:app,sha256:await sha256(app)},
      {offset:selection.offset,bytes:selection.bytes,sha256:await sha256(selection.bytes)}]};
  const {reader,writes}=flashFixture(flash);let compared=false,rechecked=false;
  await assert.rejects(executePlan(reader,plan,policy,{exact_plan:true,separate_copy:true,rom_recovery:true},
    (_,n,total)=>{if(n===total)compared=true;},undefined,async()=>{
      rechecked=true;assert.equal(compared,true);throw new Error('Revoked fixture release');
    }),/Revoked fixture/);
  assert.equal(rechecked,true);assert.deepEqual(writes,[]);
});

test('approval expiry during preflight prevents writes but never interrupts a started installation',async(t)=>{
  const start=Date.parse('2030-01-01T00:00:00Z');let now=start;
  t.mock.method(Date,'now',()=>now);
  const expiring={...policy,expires_at:new Date(start+60000).toISOString()};
  for(const expireDuringPreflight of [true,false]) {
    now=start;
    const flash=new Uint8Array(FLASH_BYTES).fill(255),app=new Uint8Array(4096).fill(42);
    const selection=selectBoot(flash.slice(0x10d000,0x10f000));
    const plan={profile:policy.profile,backup_sha256:await sha256(flash),app_sha256:policy.app.sha256,
      writes:[{offset:0xe00000,bytes:app,sha256:await sha256(app)},
        {offset:selection.offset,bytes:selection.bytes,sha256:await sha256(selection.bytes)}]};
    const {reader,writes}=flashFixture(flash);
    const action=executePlan(reader,plan,expiring,{exact_plan:true,separate_copy:true,rom_recovery:true},
      phase=>{if(expireDuringPreflight || phase.startsWith('Writing'))now=start+60000;});
    if(expireDuringPreflight){await assert.rejects(action,/expired during preflight/);assert.deepEqual(writes,[]);}
    else{await action;assert.deepEqual(writes,[0xe00000,0x10d000,'reset']);}
  }
});

test('storage failure aborts the backup and cannot return a completed hash',async()=>{
  const flash=new Uint8Array(FLASH_BYTES).fill(255),{reader}=flashFixture(flash);let aborted=false,closed=false;
  const handle={createWritable:async()=>({write:async()=>{throw new Error('quota fixture');},abort:async()=>{aborted=true;},close:async()=>{closed=true;}})};
  await assert.rejects(api.captureRead(reader,handle,undefined,()=>{}));assert.equal(aborted,true);assert.equal(closed,false);
});

test('shareable summary allowlists metadata and never exports private capture strings',()=>{
 const secret='PRIVATE-FIXTURE-DO-NOT-EXPORT';
 const report={schema:1,matching_files:true,independent_reads_match:true,sha256:'a'.repeat(64),table_sha256:'b'.repeat(64),flash_bytes:FLASH_BYTES,partition_table_offset:0x8000,partition_table_md5_verified:true,stock_layout_matches:true,ota_1_erased:true,
  hardware:{identity:secret,security:{secret}},connections:[secret],path:secret,evidence:secret,
  partitions:[{name:secret,type:1,subtype:2,offset:0x9000,size:4096,flags:0,secret}],
  images:[{name:'bootloader',offset:0x2000,image_bytes:112,chip_id:18,min_revision:100,max_revision:199,internal_checksum_verified:true,appended_sha256_verified:true,region_sha256:'c'.repeat(64),application:{version:secret,project:secret,idf:secret},secret}]};
 for(const source of ['live-browser-capture','imported-capture-record']){
  const result=api.reviewSummary(report,source);assert.equal(result.installable,false);assert.equal(result.evidence.current_physical_state_verified,false);assert.equal(result.evidence.source,source);assert.ok(!JSON.stringify(result).includes(secret));assert.equal(result.images[0].region_sha256,'c'.repeat(64));
 }
 for(const altered of [{...report,matching_files:false},{...report,sha256:secret},{...report,images:[{...report.images[0],offset:-1}]}])assert.throws(()=>api.reviewSummary(altered,'imported-capture-record'));
 assert.throws(()=>api.reviewSummary(report,secret));
});


test('unsigned candidate review plans cannot reach a serial reader or writer',async()=>{
  const reader=new Proxy({}, {get(){throw new Error('Unexpected hardware access');}});
  await assert.rejects(executePlan(reader,{review_only:true},policy,{exact_plan:true,separate_copy:true,rom_recovery:true}),
    error=>error.userMessage==='An unsigned review plan cannot write hardware.');
  for(const candidate of [{status:'reviewed-development-release'},
    {status:'development-review',installable:false,profile:'waveshare-7b-stock-v1',app:{offset:0x8000,size:112}}]){
    await assert.rejects(api.makeReviewPlan({}, {},candidate,new Uint8Array()));
  }
});


test('known vendor fingerprints are recognized without approving unknown hardware or releases',()=>{
  const catalog=JSON.parse(readFileSync('../../firmware/profiles/stock-baselines.json'));
  const baseline=catalog.baselines[0];
  const report={stock_layout_matches:true,matching_files:true,partition_table_md5_verified:true,partition_table_offset:0x8000,
    table_sha256:baseline.regions.find(r=>r.name==='table').sha256,
    images:[{name:'bootloader',offset:0x2000,region_sha256:baseline.regions.find(r=>r.name==='bootloader').sha256,internal_checksum_verified:true,appended_sha256_verified:true}]};
  assert.equal(api.recognizeBaseline(report),baseline.id);
  assert.equal(baseline.installable,false);
  for(const changed of [{...report,matching_files:false},{...report,stock_layout_matches:false},{...report,partition_table_offset:0},
    {...report,table_sha256:'0'.repeat(64)},{...report,images:[{...report.images[0],region_sha256:'0'.repeat(64)}]},
    {...report,images:[{...report.images[0],internal_checksum_verified:false}]}])assert.equal(api.recognizeBaseline(changed),null);
});


async function recoveryFixture(){
  const original=new Uint8Array(FLASH_BYTES).fill(255),backup=new Blob([original]),digest=await sha256(original);
  const report={matching_files:true,independent_reads_match:true,stock_layout_matches:true,ota_1_erased:true,sha256:digest};
  const installation={backup_sha256:digest,writes:[{offset:0xe00000,bytes:new Uint8Array(4096)}]};
  return {original,plan:await api.prepareRecovery(backup,report,installation)};
}
const recoveryConsent={restore_original:true,discard_ampve_settings:true,stable_usb_power:true};

test('recovery restores only exact original regions, selection last, and verifies the full backup',async()=>{
  const {original,plan}=await recoveryFixture();const flash=original.slice();
  flash[0x3b000]=12;flash[0xe00000]=42;flash[0x10d000]=1;
  const {reader,writes}=flashFixture(flash);
  const check=await api.validateRecovery(reader,plan);
  assert.equal(check.changed_bytes,3);assert.equal(check.physical_restore_verified,false);
  const result=await api.executeRecovery(reader,plan,check,recoveryConsent);
  assert.deepEqual(writes,[0x3b000,0xe00000,0x10d000,'reset']);
  assert.equal(result.full_backup_readback_verified,true);assert.equal(result.physical_stock_startup_verified,false);
  assert.equal(await sha256(flash),await sha256(original));
});

test('recovery refuses other changed areas, stale review, modified source, expansion and missing consent',async()=>{
  const {original,plan}=await recoveryFixture();const flash=original.slice();const {reader,writes}=flashFixture(flash);
  flash[0x8000]=0;await assert.rejects(api.validateRecovery(reader,plan));assert.deepEqual(writes,[]);flash[0x8000]=255;
  const check=await api.validateRecovery(reader,plan);flash[0xe00000]=0;
  await assert.rejects(api.executeRecovery(reader,plan,check,recoveryConsent));assert.deepEqual(writes,[]);
  await assert.rejects(api.executeRecovery(reader,plan,check,{}));assert.deepEqual(writes,[]);
  plan.writes[1].bytes=new Uint8Array(8192).fill(255);plan.writes[1].size=8192;plan.writes[1].sha256=await sha256(plan.writes[1].bytes);
  await assert.rejects(api.validateRecovery(reader,plan));
});

test('failed recovery readback never restores boot selection or claims stock startup',async()=>{
  const {original,plan}=await recoveryFixture();const flash=original.slice();flash[0xe00000]=0;
  const {reader,writes}=flashFixture(flash,{failAppReadback:true});const check=await api.validateRecovery(reader,plan);
  await assert.rejects(api.executeRecovery(reader,plan,check,recoveryConsent));assert.deepEqual(writes,[0x3b000,0xe00000]);
});

test('C6 diagnostics bind the current nonce and never infer Wi-Fi or recovery success',()=>{
  const nonce='a'.repeat(32),record={kind:'ampve-c6-probe',schema:1,nonce,status:'observed',version:[2,12,13]};
  const result=api.probeResult(JSON.stringify(record),nonce);assert.equal(result.version_matches,true);assert.equal(result.wifi_function_verified,false);
  for(const status of ['timeout','unavailable','identity_unavailable'])assert.equal(api.probeResult(JSON.stringify({...record,status}),nonce).version_matches,false);
  assert.equal(api.probeResult(JSON.stringify({...record,version:[1,4,0]}),nonce).version_matches,false);
  for(const changed of [{...record,nonce:'b'.repeat(32)},{...record,version:[256,0,0]},{...record,secret:'fixture'}])assert.throws(()=>api.probeResult(JSON.stringify(changed),nonce));
});

test('RAM diagnostic refuses flash-mapped, overlapping and tampered images',async()=>{
  const bytes=new Uint8Array(40),v=new DataView(bytes.buffer);bytes[0]=0xe9;bytes[1]=1;
  v.setUint32(4,0x4ff20000,true);v.setUint16(12,18,true);v.setUint16(15,100,true);v.setUint16(17,199,true);
  v.setUint32(24,0x4ff20000,true);v.setUint32(28,8,true);
  const manifest={schema:1,kind:'ampve-c6-ram-probe',chip_revision:103,flash_writes:false,size:bytes.length,sha256:await sha256(bytes)};
  assert.equal((await api.ramSegments(bytes,manifest)).entry,0x4ff20000);
  v.setUint32(24,0x40000000,true);await assert.rejects(api.ramSegments(bytes,{...manifest,sha256:await sha256(bytes)}));
  v.setUint32(24,0x4ff20000,true);bytes[39]^=1;await assert.rejects(api.ramSegments(bytes,manifest));
});

test('RAM probe reuses the real esptool reader and closes on success, cancellation or invalid response',async()=>{
  const bytes=new Uint8Array(40),v=new DataView(bytes.buffer);bytes[0]=0xe9;bytes[1]=1;
  v.setUint32(4,0x4ff20000,true);v.setUint16(12,18,true);v.setUint16(15,100,true);v.setUint16(17,199,true);
  v.setUint32(24,0x4ff20000,true);v.setUint32(28,8,true);
  const manifest={schema:1,kind:'ampve-c6-ram-probe',chip_revision:103,flash_writes:false,size:40,sha256:await sha256(bytes)};
  for(const mode of ['success','cancel','stale','oversize']){
    const controller=new AbortController(),commands=[];let input,loop,disconnected=false,released=false;
    const port={readable:new ReadableStream({start(c){input=c;}}),
      writable:{getWriter:()=>({write:async data=>{
        const nonce=mode==='stale'?'b'.repeat(32):new TextDecoder().decode(data).trim();
        const frame=mode==='oversize'?'x'.repeat(16385):JSON.stringify({kind:'ampve-c6-probe',schema:1,nonce,status:'observed',version:[2,12,13]})+'\n';
        input.enqueue(new TextEncoder().encode(frame));
      },releaseLock:()=>{released=true;}})},close:async()=>{assert.equal(port.readable.locked,false);disconnected=true;}};
    const transport=new api.Transport(port,false);transport.trace=()=>{};
    const connect=async(selected,options)=>{
      assert.equal(selected,port);assert.deepEqual(options,{baud:115200,stub:false});
      loop=transport.readLoop();assert.equal(port.readable.locked,true);
      return {hardware:{identity:'PRIVATE-FIXTURE-UNIT'},loader:{memBegin:async(...args)=>commands.push(['begin',...args]),
        memBlock:async()=>commands.push(['block']),memFinish:async entry=>{
          commands.push(['finish',entry]);if(mode==='cancel')setTimeout(()=>controller.abort(),10);
        }},transport};
    };
    const result=api.runProbe(port,bytes,manifest,()=>{},controller.signal,connect);
    if(mode==='cancel')await assert.rejects(result,{name:'AbortError'});
    else if(mode==='success'){const observed=await result;assert.equal(observed.version_matches,true);assert.equal(observed.unit_identity,'PRIVATE-FIXTURE-UNIT');}
    else await assert.rejects(result);
    await loop;
    assert.equal(disconnected,true);assert.equal(released,mode!=='cancel');assert.equal(port.readable.locked,false);
    assert.deepEqual(commands,[['begin',8,1,1024,0x4ff20000],['block'],['finish',0x4ff20000]]);
  }
});

test('C6 failure stages retain bounded error codes and never establish compatibility',()=>{
  const nonce='a'.repeat(32);
  for(const status of ['host_init_failed','connection_failed','version_query_failed','event_loop_failed','task_start_failed']){
    const record={kind:'ampve-c6-probe',schema:1,nonce,status,version:[0,0,0],error_code:-1};
    const result=api.probeResult(JSON.stringify(record),nonce);
    assert.equal(result.status,status);assert.equal(result.error_code,-1);assert.equal(result.version_matches,false);
    for(const error_code of [-2,65536,true,'private'])assert.throws(()=>api.probeResult(JSON.stringify({...record,error_code}),nonce));
  }
  const good={kind:'ampve-c6-probe',schema:1,nonce,status:'observed',version:[2,12,13],error_code:0};
  assert.equal(api.probeResult(JSON.stringify(good),nonce).version_matches,true);
  assert.throws(()=>api.probeResult(JSON.stringify({...good,error_code:-1}),nonce));
});

test('USB commissioning requires an explicit signed initial-install review',async()=>{
  const usb={...policy,commissioning:'usb-assisted-v1',usb_review:'Software fixture: core-only startup with separate network acceptance.'};
  assert.equal(api.allowsUsbCommissioning(await verifyRelease(await signed(usb))),true);
  assert.equal(api.allowsUsbCommissioning(policy),false);
  for(const change of [{usb_review:undefined},{commissioning:undefined},{commissioning:'anything'},{purpose:'ota'}])
    await assert.rejects(verifyRelease(await signed({...usb,...change})));
});
const runtimeExpected={version:'fixture-0.1',sha256:'a'.repeat(64)};
function runtimeFrame(nonce,extra={}){return JSON.stringify({kind:'ampve-usb-status',schema:1,nonce,phase:'network_unavailable',firmware_version:runtimeExpected.version,app_sha256:runtimeExpected.sha256,core_confirmed:true,wifi_initialized:false,display_ready:false,touch_ready:false,...extra});}
test('USB status binds nonce and installed bytes without claiming network or peripheral success',()=>{
  const nonce='b'.repeat(32),line=runtimeFrame(nonce),result=api.runtimeStatus(line,nonce,runtimeExpected);
  assert.equal(result.core_confirmed,true);assert.equal(result.wifi_initialized,false);assert.equal(Object.hasOwn(result,'nonce'),false);
  for(const extra of [{nonce:'c'.repeat(32)},{app_sha256:'d'.repeat(64)},{app_sha256:''},{firmware_version:'stock'},{core_confirmed:1},{secret:'never allowed'},{phase:'unknown'}])
    assert.throws(()=>api.runtimeStatus(runtimeFrame(nonce,extra),nonce,runtimeExpected));
  assert.throws(()=>api.runtimeStatus(line.replace('"schema":1','"schema":1,"schema":1'),nonce,runtimeExpected));
});
function runtimePort(reply){let controller;const port={closed:false,async open(){this.readable=new ReadableStream({start(c){controller=c;}});this.writable=new WritableStream({write(bytes){reply(new TextDecoder().decode(bytes),controller);}});},async close(){assert.equal(this.readable.locked,false);assert.equal(this.writable.locked,false);this.closed=true;}};return port;}
test('USB commissioning uses one reader and closes it on success, wrong image and timeout',async()=>{
  for(const mode of ['success','wrong','timeout']){
    const port=runtimePort((request,c)=>{if(mode==='timeout')return;const nonce=request.trim().split(' ')[1];const bytes=new TextEncoder().encode('private log discarded\n'+runtimeFrame(nonce,mode==='wrong'?{app_sha256:'d'.repeat(64)}:{})+'\n');c.enqueue(bytes.slice(0,80));c.enqueue(bytes.slice(80));});
    const check=api.checkRuntime(port,runtimeExpected,()=>{},undefined,50);
    if(mode==='success')assert.equal((await check).core_confirmed,true);else await assert.rejects(check);
    assert.equal(port.closed,true);
  }
});
test('USB commissioning cancellation releases the port without sending Wi-Fi credentials',async()=>{
  const abort=new AbortController();const port=runtimePort((request)=>{assert.match(request,/^AMPVE_STATUS [a-f0-9]{32}\n$/);queueMicrotask(()=>abort.abort());});
  await assert.rejects(api.checkRuntime(port,runtimeExpected,()=>{},abort.signal,100),{name:'AbortError'});assert.equal(port.closed,true);
});
test('USB setup waits for core confirmation even when earlier status replies are valid',async()=>{
  let requests=0,reports=0;
  const port=runtimePort((request,c)=>{const nonce=request.trim().split(' ')[1];c.enqueue(new TextEncoder().encode(runtimeFrame(nonce,{core_confirmed:++requests>1})+'\n'));});
  const result=await api.checkRuntime(port,runtimeExpected,()=>++reports,undefined,3000);
  assert.equal(result.core_confirmed,true);assert.equal(reports,2);assert.equal(port.closed,true);
});
test('failed USB startup exports bounded categories rather than private UART text',async()=>{
  const port=runtimePort((request,c)=>{c.enqueue(new TextEncoder().encode('SSID private-network password private-secret\nGuru Meditation Error: Core 0 panic\nwaiting for download\n'));});
  let failure;
  try{await api.checkRuntime(port,runtimeExpected,()=>{},undefined,30);}catch(error){failure=error.startupSummary;}
  assert.equal(failure.kind,'ampve-usb-startup-failure');assert.equal(failure.timed_out,true);
  assert.deepEqual(failure.observations,['download_mode','panic']);assert.equal(failure.physical_startup_verified,false);
  assert.equal(JSON.stringify(failure).includes('private-'),false);assert.equal(port.closed,true);
});
test('startup categories do not expose diagnostic lines or accept oversized lines',()=>{
  assert.deepEqual(api.bootObservations('invalid header: 0xffffffff'),['invalid_image']);
  assert.deepEqual(api.bootObservations('Task watchdog got triggered'),['watchdog']);
  assert.deepEqual(api.bootObservations('PSRAM ID read error'),['memory_initialization']);
  assert.deepEqual(api.bootObservations('private SSID and password'),[]);
  assert.deepEqual(api.bootObservations('invalid header:'+'x'.repeat(768)),[]);
});
test('application reset uses the actual pinned loader to assert and release EN without asserting BOOT',async()=>{
  const signals=[];const port={setSignals:async value=>signals.push(value),getInfo:()=>({usbVendorId:0x1a86,usbProductId:0x55d3})};
  const loader=new api.ESPLoader({transport:new api.Transport(port),baudrate:115200,terminal:{write(){},writeLine(){},clean(){}}});
  await api.resetApplication({loader});
  assert.deepEqual(signals.filter(s=>Object.hasOwn(s,'requestToSend')).map(s=>s.requestToSend),[true,false]);
  assert.ok(signals.filter(s=>Object.hasOwn(s,'dataTerminalReady')).every(s=>s.dataTerminalReady===false));
});
test('startup retries a lost early request using one nonce and performs reset after opening its reader',async()=>{
  const signals=[];let requests=0,nonce;
  const port=runtimePort((request,c)=>{const current=request.trim().split(' ')[1];if(nonce)assert.equal(current,nonce);nonce=current;
    if(++requests===2)c.enqueue(new TextEncoder().encode(runtimeFrame(nonce)+'\n'));});
  port.getInfo=()=>({usbVendorId:0x1a86,usbProductId:0x55d3});
  port.setSignals=async value=>{assert.equal(port.readable.locked,true);signals.push(value);};
  const result=await api.checkRuntime(port,runtimeExpected,()=>{},undefined,3000,true);
  assert.equal(result.core_confirmed,true);assert.equal(requests,2);assert.equal(port.closed,true);
  assert.deepEqual(signals.filter(s=>Object.hasOwn(s,'requestToSend')).map(s=>s.requestToSend),[true,false]);
});
test('panic details distinguish allocator failures and expose only instruction PCs',()=>{
  assert.deepEqual(api.bootFailureDetails('E (41) esp_psram: Failed to allocate dummy cacheline for PSRAM memory barrier!').details,['psram_memory_barrier_allocation','allocation_failed']);
  assert.deepEqual(api.bootFailureDetails('E (44) LvglPsramPool: Failed to allocate 204800 bytes in PSRAM').details,['lvgl_psram_pool_allocation','allocation_failed']);
  assert.deepEqual(api.bootFailureDetails('abort() was called at PC 0x4ff01234 on core 0').program_counters,['0x4ff01234']);
  assert.deepEqual(api.bootFailureDetails('ESP_ERROR_CHECK failed: esp_err_t 0xffffffff (ESP_FAIL) at 0x4801abcd').program_counters,['0x4801abcd']);
  assert.deepEqual(api.bootFailureDetails('E (21) esp-sha: Failed to allocate aligned SPIRAM memory').details,['allocation_failed','sha_aligned_input_allocation']);
  assert.deepEqual(api.bootFailureDetails('MEPC : 0x48012340 RA : 0x482abcde SP : 0x4ff54320').program_counters,['0x48012340']);
  assert.deepEqual(api.bootFailureDetails('ELF file SHA256: 12345678abcdef00...').elf_prefixes,['12345678abcdef00']);
  assert.deepEqual(api.bootFailureDetails('ELF file SHA256: private-password').elf_prefixes,[]);
  for(const line of ['password private-secret /private/path','A0 : 0x48012340','MEPC : 0x00000000','abort() was called at PC 0x4ff01234'+'x'.repeat(768)])assert.deepEqual(api.bootFailureDetails(line),{details:[],program_counters:[],elf_prefixes:[],init_failures:[]});
});
test('first panic ends capture with a bounded tail instead of waiting for repeated-boot overflow',async()=>{
  const port=runtimePort((request,c)=>{c.enqueue(new TextEncoder().encode('E (1) LvglPsramPool: Failed to allocate 512 bytes in PSRAM\nabort() was called at PC 0x4ff01234 on core 0\nMEPC : 0x48012340\nSSID private-network password private-secret\n'));});
  let summary;
  try{await api.checkRuntime(port,runtimeExpected,()=>{},undefined,4000);}catch(error){summary=error.startupSummary;}
  assert.equal(summary.capture_stop,'panic_captured');assert.equal(summary.timed_out,false);
  assert.deepEqual(summary.panic_program_counters,['0x4ff01234','0x48012340']);
  assert.ok(summary.failure_details.includes('lvgl_psram_pool_allocation'));
  assert.equal(JSON.stringify(summary).includes('private-'),false);assert.equal(port.closed,true);
});

test('system initializer evidence preserves the failed callee separately from generic abort PCs',async()=>{
  const line='\x1b[0;31mE (82) cpu_start: init function 0x48001234 has failed (0x101), aborting\x1b[0m';
  assert.deepEqual(api.bootFailureDetails(line).init_failures,[{function_address:'0x48001234',error_code:'0x101'}]);
  for(const invalid of ['init function 0x00000000 has failed (0x101), aborting','init function private-path has failed (private-secret), aborting','init function 0x48001234 has failed (0x101), aborting private-secret'])assert.deepEqual(api.bootFailureDetails(invalid).init_failures,[]);
  const port=runtimePort((request,c)=>c.enqueue(new TextEncoder().encode(line+'\nabort() was called at PC 0x480019e9 on core 0\nELF file SHA256: 6ea09dd6d\n')));
  let summary;try{await api.checkRuntime(port,runtimeExpected,()=>{},undefined,4000);}catch(error){summary=error.startupSummary;}
  assert.deepEqual(summary.startup_initializer_failures,[{function_address:'0x48001234',error_code:'0x101'}]);
  assert.deepEqual(summary.panic_program_counters,['0x480019e9']);assert.equal(summary.capture_stop,'panic_captured');
});

test('initializer symbol labels require both the published app and observed matching ELF prefix',()=>{
  const expected={sha256:'9431969a70d060db94f92a11873ce5200d597a6df199ceeed90c80de2deae33e'};
  const failures=[{function_address:'0x481a3ce6',error_code:'0x101'}];
  assert.equal(api.resolveStartupInitializers(expected,['6ea09dd6d'],failures)[0].matched_build_function,'psram_core_stage_init');
  for(const prefixes of [[],['aaaaaaaa'],['6ea09dd6d','aaaaaaaa'],['6ea']])assert.deepEqual(api.resolveStartupInitializers(expected,prefixes,failures),failures);
  assert.deepEqual(api.resolveStartupInitializers({sha256:'a'.repeat(64)},['6ea09dd6d'],failures),failures);
});

test('startup symbol catalog distinguishes current and previous builds without cross-labeling',()=>{
  const builds=JSON.parse(readFileSync('startup-symbols.json'));
  assert.ok(builds.length>=2);
  assert.equal(new Set(builds.map(item=>item.app_sha256)).size,builds.length);
  assert.equal(new Set(builds.map(item=>item.elf_sha256)).size,builds.length);
  for(const build of builds){
    const [address,name]=Object.entries(build.functions)[0];
    const failures=[{function_address:address,error_code:'0x101'}];
    assert.equal(api.resolveStartupInitializers({sha256:build.app_sha256},[build.elf_sha256.slice(0,9)],failures)[0].matched_build_function,name);
    for(const other of builds.filter(item=>item!==build))
      assert.deepEqual(api.resolveStartupInitializers({sha256:build.app_sha256},[other.elf_sha256.slice(0,9)],failures),failures);
  }
  assert.equal(Object.values(builds[1].functions).includes('sleep_clock_icg_startup_init'),false);
});

async function reinstallFixture(){
  const original=new Uint8Array(FLASH_BYTES).fill(255),backup=new Blob([original]),digest=await sha256(original);
  const report={matching_files:true,independent_reads_match:true,stock_layout_matches:true,ota_1_erased:true,sha256:digest};
  const selection=selectBoot(original.slice(0x10d000,0x10f000));
  const make=async bytes=>({profile:policy.profile,backup_sha256:digest,app_sha256:await sha256(bytes),
    writes:[{offset:0xe00000,bytes,sha256:await sha256(bytes)},{offset:selection.offset,bytes:selection.bytes,sha256:await sha256(selection.bytes)}],
    recovery:[{offset:0xe00000,bytes:original.slice(0xe00000,0xe00000+bytes.length)}]});
  const old=await make(new Uint8Array(8192).fill(41)),next=await make(new Uint8Array(4096).fill(42));
  const latest={...policy,sequence:8,app:{...policy.app,sha256:next.app_sha256}},previous={...policy,app:{...policy.app,size:8192,sha256:old.app_sha256}};
  const {plan}=await api.prepareReinstall(backup,report,next,latest,old,previous);
  const flash=original.slice();flash.set(old.writes[0].bytes,0xe00000);flash.set(selection.bytes,selection.offset);flash[0x3b000]=12;
  return {flash,original,plan,latest};
}
const installConsent={exact_plan:true,separate_copy:true,rom_recovery:true};
test('same install action replaces a known failed image, clears its longer tail and preserves NVS without a stock reboot',async()=>{
  const {flash,plan,latest}=await reinstallFixture(),{reader,writes,reads}=flashFixture(flash);let revalidated=false;
  const result=await api.executeInstallOrReinstall(reader,plan,latest,installConsent,()=>{},undefined,async()=>{revalidated=true;});
  assert.equal(revalidated,true);assert.equal(result.physical_startup_verified,false);
  assert.equal(reads.reduce((sum,read)=>sum+read.size,0),FLASH_BYTES+8192+4096);
  assert.equal(result.installation_summary.preflight_bytes,FLASH_BYTES);
  assert.deepEqual(writes,[0xe00000,0x10d000,'reset']);assert.equal(flash[0x3b000],12);
  assert.ok(flash.slice(0xe00000,0xe01000).every(b=>b===42));assert.ok(flash.slice(0xe01000,0xe02000).every(b=>b===255));
  assert.equal(plan.recovery[0].bytes.length,8192);
});
test('adaptive installation also accepts the untouched original and an exact retry of the latest image',async()=>{
  for(const state of ['original','latest']){
    const {flash,original,plan,latest}=await reinstallFixture();
    if(state==='original')flash.set(original);else flash.set(plan.writes[0].bytes,0xe00000);
    const {reader,writes}=flashFixture(flash);
    await api.executeInstallOrReinstall(reader,plan,latest,installConsent,()=>{},undefined,async()=>{});
    assert.deepEqual(writes,[0xe00000,0x10d000,'reset']);
  }
});
test('reinstall rejects unknown images, protected changes, changed stock selection, cancellation and revocation before writing',async()=>{
  for(const failure of ['unknown','protected','selection','cancel','revoked','readback']){
    const {flash,plan,latest}=await reinstallFixture();
    if(failure==='unknown')flash[0xe00010]^=1;
    if(failure==='protected')flash[0x8000]^=1;
    if(failure==='selection')flash[0x10e000]^=1;
    const {reader,writes}=flashFixture(flash,{failAppReadback:failure==='readback'});
    const controller=new AbortController();if(failure==='cancel')controller.abort();
    await assert.rejects(api.executeInstallOrReinstall(reader,plan,latest,installConsent,()=>{},controller.signal,async()=>{if(failure==='revoked')throw new Error('Revoked');}));
    assert.deepEqual(writes,failure==='readback'?[0xe00000]:[],failure);
  }
});

test('installation failure result distinguishes a verified flash from restart failure and excludes raw exception text',async()=>{
  const {flash,plan,latest}=await reinstallFixture(),{reader,writes}=flashFixture(flash);
  reader.loader.after=async()=>{throw new TypeError('PRIVATE_PASSWORD /private/path serial dump');};
  let error;try{await api.executeInstallOrReinstall(reader,plan,latest,installConsent);}catch(e){error=e;}
  assert.equal(error.installationSummary.phase,'restart');
  assert.equal(error.installationSummary.app_readback_verified,true);
  assert.equal(error.installationSummary.selection_readback_verified,true);
  assert.equal(error.installationSummary.reset_completed,false);
  assert.equal(error.userMessage.includes('written and verified'),true);
  assert.equal(JSON.stringify(error.installationSummary).includes('PRIVATE'),false);
  assert.deepEqual(writes,[0xe00000,0x10d000]);
});
test('write transport failure exports its actual phase without claiming a verified application',async()=>{
  const {flash,plan,latest}=await reinstallFixture(),{reader}=flashFixture(flash);
  reader.loader.writeFlash=async()=>{throw new Error('PRIVATE serial output');};
  let error;try{await api.executeInstallOrReinstall(reader,plan,latest,installConsent);}catch(e){error=e;}
  assert.equal(error.installationSummary.phase,'app_write');
  assert.equal(error.installationSummary.write_attempted,true);
  assert.equal(error.installationSummary.app_readback_verified,false);
  assert.equal(error.installationSummary.preflight_bytes,FLASH_BYTES);
  assert.equal(error.userMessage.includes('PRIVATE'),false);
});

test('completed MD5 failure retries only that block; malformed frames and exhausted retries stop',async()=>{
  const bytes=new Uint8Array(4096).fill(19),good=Uint8Array.from((await md5(bytes)).match(/../g),h=>parseInt(h,16));
  for(const mode of ['transient','persistent','short']){
    let commands=0,packets=[];
    const reader={loader:{ESP_READ_FLASH:0xd2,checkCommand:async()=>{commands++;packets=mode==='short'?[bytes.slice(0,10)]:[bytes,mode==='transient'&&commands===2?good:new Uint8Array(16)];}},transport:{read:async()=>packets.shift(),write:async()=>{}}};
    if(mode==='transient')assert.deepEqual(await readChunk(reader,0x1380000,4096),bytes);
    else{
      let failure;try{await readChunk(reader,0x1380000,4096);}catch(error){failure=error.readFailure;}
      assert.equal(failure.code,mode==='short'?'flash_packet_incomplete':'flash_transfer_md5_mismatch');
      assert.equal(failure.offset,0x1380000);assert.equal(failure.attempt,mode==='short'?1:3);
    }
    assert.equal(commands,mode==='transient'?2:mode==='short'?1:3);
  }
});
test('read retry budget is bounded across the connection and cancellation prevents a retry',async()=>{
  const bytes=new Uint8Array(4096).fill(19),good=Uint8Array.from((await md5(bytes)).match(/../g),h=>parseInt(h,16));
  let commands=0,packets=[];
  const reader={loader:{ESP_READ_FLASH:0xd2,checkCommand:async()=>{commands++;packets=[bytes,commands%2===0?good:new Uint8Array(16)];}},transport:{read:async()=>packets.shift(),write:async()=>{}}};
  for(let i=0;i<8;i++)await readChunk(reader,i*4096,4096);
  await assert.rejects(readChunk(reader,8*4096,4096));assert.equal(commands,17);
  const controller=new AbortController();commands=0;
  reader.loader.checkCommand=async()=>{commands++;packets=[bytes,new Uint8Array(16)];};
  reader.transport.read=async()=>{const packet=packets.shift();if(packet.length===16)controller.abort();return packet;};
  await assert.rejects(readChunk(reader,0,4096,controller.signal),{name:'AbortError'});assert.equal(commands,1);
});
test('mid-preflight USB corruption recovers without rereading earlier flash or accepting bad bytes',async()=>{
  const {flash,plan,latest}=await reinstallFixture(),{reader,writes,reads}=flashFixture(flash);
  const command=reader.loader.checkCommand,read=reader.transport.read;let corrupt=false,injected=false;
  reader.loader.checkCommand=async(...args)=>{
    await command(...args);const offset=new DataView(args[2].buffer).getUint32(0,true);
    if(offset===0x1380000&&!injected){injected=true;corrupt=true;}
  };
  reader.transport.read=async(...args)=>{const packet=await read(...args);if(corrupt){corrupt=false;packet[0]^=1;}return packet;};
  const result=await api.executeInstallOrReinstall(reader,plan,latest,installConsent);
  assert.equal(result.installation_summary.read_retry_count,1);
  assert.equal(reads.filter(read=>read.offset===0).length,1);
  assert.equal(reads.filter(read=>read.offset===0x1380000).length,2);
  assert.equal(reads.reduce((sum,read)=>sum+read.size,0),FLASH_BYTES+65536+8192+4096);
  assert.deepEqual(writes,[0xe00000,0x10d000,'reset']);
});

test('persistent USB corruption reports the failed read block and never reaches a flash write',async()=>{
  const {flash,plan,latest}=await reinstallFixture(),{reader,writes}=flashFixture(flash);
  const command=reader.loader.checkCommand,read=reader.transport.read;let corrupt=false;
  reader.loader.checkCommand=async(...args)=>{await command(...args);corrupt=new DataView(args[2].buffer).getUint32(0,true)===0x1380000;};
  reader.transport.read=async(...args)=>{const packet=await read(...args);if(corrupt){corrupt=false;packet[0]^=1;}return packet;};
  let error;try{await api.executeInstallOrReinstall(reader,plan,latest,installConsent);}catch(e){error=e;}
  const result=error.installationSummary;
  assert.equal(result.error_category,'flash_transfer_md5_mismatch');
  assert.equal(result.phase,'preflight');assert.equal(result.write_attempted,false);
  assert.equal(result.read_failure.offset,0x1380000);assert.equal(result.read_failure.attempt,3);
  assert.equal(result.read_retry_count,2);assert.deepEqual(writes,[]);
});

test('assertion locations omit expressions and private paths and reject malformed records',()=>{
  const location=api.startupAssertion('assert failed: uart_driver_install /private/build/components/driver/uart.c:1720 (secret_expression == 1)');
  assert.deepEqual(location,{function:'uart_driver_install',file:'uart.c',line:1720});
  assert.equal(JSON.stringify(location).includes('private'),false);
  assert.equal(JSON.stringify(location).includes('secret'),false);
  for(const line of ['password secret','assert failed: f x.c:0 (x)','assert failed: f x.c:10 (x) leaked','assert failed: f secret.txt:10 (x)','x'.repeat(769)])assert.equal(api.startupAssertion(line),null);
});

test('early heap checkpoints accept only bounded numeric internal-memory counts',()=>{
  assert.deepEqual(api.startupHeap('AMPVE_BOOT_HEAP scheduler_pending 15000 12000'),{phase:'scheduler_pending',internal_free_bytes:15000,internal_largest_block_bytes:12000});
  for(const line of ['AMPVE_BOOT_HEAP unknown 10 1','AMPVE_BOOT_HEAP runtime_pending 1 2','AMPVE_BOOT_HEAP scheduler_pending 1048577 0','AMPVE_BOOT_HEAP scheduler_pending 10 1 private','private'])assert.equal(api.startupHeap(line),null);
});

test('startup failure reports retain only the last bounded checkpoint per phase',async()=>{
  const port=runtimePort((request,c)=>c.enqueue(new TextEncoder().encode('AMPVE_BOOT_HEAP scheduler_pending 20000 18000\nAMPVE_BOOT_HEAP scheduler_pending 19000 17000\nAMPVE_BOOT_HEAP runtime_pending 400000 390000\nAMPVE_BOOT_HEAP private 2 1\nassert failed: vApplicationGetIdleTaskMemory port_common.c:53 (private-expression)\n')));
  let summary;try{await api.checkRuntime(port,runtimeExpected,()=>{},undefined,4000);}catch(error){summary=error.startupSummary;}
  assert.deepEqual(summary.startup_heap,[{phase:'scheduler_pending',internal_free_bytes:19000,internal_largest_block_bytes:17000},{phase:'runtime_pending',internal_free_bytes:400000,internal_largest_block_bytes:390000}]);
  assert.equal(JSON.stringify(summary).includes('private'),false);assert.equal(port.closed,true);
});

test('observed old ELF never labels the expected new candidate as the failed build',()=>{
  const expected={sha256:'ca04872053e00abd412ef9f074ed71f43efa39477487d74e423dd20de964d1b9'};
  assert.deepEqual(api.startupIdentity(expected,['c441d686a']),{build_identity:'different_known_build',observed_app_sha256:'bc334f7d5c744d693f0de9034aaaea26de0694dfc94aed90fcf8087eba466406'});
  assert.deepEqual(api.startupIdentity(expected,['39deeabeb']),{build_identity:'expected_build',observed_app_sha256:expected.sha256});
  for(const prefixes of [[],['private'],['aaaaaaaa'],['39deeabeb','c441d686a'],['39deeab']])assert.deepEqual(api.startupIdentity(expected,prefixes),{build_identity:'unresolved',observed_app_sha256:null});
});

test('backup gates explain saved-file failures before reading files or candidate bytes',async()=>{
  const report={owner_confirmed_profile:contract.profile_id,stock_layout_matches:true,independent_reads_match:true,ota_1_erased:true};
  for(const [field,code] of [['stock_layout_matches','backup_layout_mismatch'],['independent_reads_match','backup_capture_missing'],['ota_1_erased','backup_not_original']]){
    const file=new Proxy({}, {get(){throw Error('Unexpected file access');}});
    await assert.rejects(api.makePlan(file,{...report,[field]:false},policy,new Uint8Array()),{code});
  }
});
