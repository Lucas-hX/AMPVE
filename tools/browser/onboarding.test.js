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
await build({stdin:{contents:'export * from "./audit.js"; export * from "./install.js"; export * from "./review.js";',resolveDir:process.cwd()},bundle:true,platform:'node',format:'esm',outfile:'build/test-api.mjs'});
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
  let pending=[];const writes=[];
  const reader={loader:{ESP_READ_FLASH:0xd2,checkCommand:async(_,op,payload)=>{
    const v=new DataView(payload.buffer),readAt=v.getUint32(0,true),readSize=v.getUint32(4,true);
    const bytes=flash.slice(readAt,readAt+readSize);
    if(failAppReadback&&writes.length&&readAt>=0xe00000&&readAt<0x11f0000)bytes[0]^=1;
    pending=[];for(let at=0;at<bytes.length;at+=4096)pending.push(bytes.slice(at,at+4096));
    pending.push(Uint8Array.from((await md5(bytes)).match(/../g),h=>parseInt(h,16)));
  },writeFlash:async options=>{
    assert.equal(options.eraseAll,false);assert.equal(options.flashMode,'keep');assert.equal(options.fileArray.length,1);
    const item=options.fileArray[0];writes.push(item.address);flash.set(item.data,item.address);
  },after:async()=>writes.push('reset')},transport:{read:async()=>pending.shift(),write:async()=>{}}};
  return {reader,writes};
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
