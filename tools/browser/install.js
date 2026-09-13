// AMPVE's guarded integration uses ESP Web Tools manifest conventions and its
// pinned esptool-js writer. Its generic install dialog cannot keep our audited
// connection or verify the app before switching boot selection; do not expose it.
import crc32 from 'pako/lib/zlib/crc32.js';
import {createSHA256} from 'hash-wasm';
import {ensure,sha256,inspectImage,readChunk,FLASH_BYTES,BLOCK,PROFILE} from './audit.js';
import {HARDWARE_PROFILE, CONTRACT, PARTITIONS, matchesContract} from './profile.js';

const SLOT=PARTITIONS[HARDWARE_PROFILE.layout.initial_app], OTA=PARTITIONS.otadata;
const BOOT=HARDWARE_PROFILE.layout.bootloader_offset, TABLE=HARDWARE_PROFILE.layout.table_offset;

export function selectBoot(data) {
  ensure(data.length===8192,'Incomplete boot selection.');
  const valid=[];
  for(let i=0;i<2;i++) {
    const start=i*4096,view=new DataView(data.buffer,data.byteOffset+start,32);
    const seq=view.getUint32(0,true),state=view.getUint32(24,true),crc=view.getUint32(28,true);
    if(seq!==0xffffffff && ![3,4].includes(state) && (crc32(-1,data,4,start)>>>0)===crc) {
      ensure(seq>0 && [0,1,2,0xffffffff].includes(state),'Unknown stock OTA state.');
      valid.push({seq,state,index:i});
    }
  }
  ensure(valid.length || data.every(b=>b===255),'No unambiguous stock boot selection.');
  if(valid.length===2 && valid[0].seq===valid[1].seq) ensure(valid[0].state===valid[1].state,'Ambiguous boot states.');
  valid.sort((a,b)=>b.seq-a.seq || b.index-a.index);
  const current=valid[0];
  if(current) ensure((current.seq-1)%2===0 && [2,0xffffffff].includes(current.state),'Stock ota_0 must be confirmed; target slot cannot be active.');
  const sequence=current?current.seq+1:2,index=current?1-current.index:0;
  ensure(sequence<0xfffffffe,'Boot sequence needs manual review.');
  const bytes=data.slice(index*4096,(index+1)*4096),view=new DataView(bytes.buffer);
  bytes.fill(255,0,32);view.setUint32(0,sequence,true);view.setUint32(24,0,true);
  view.setUint32(28,crc32(-1,bytes,4,0)>>>0,true);
  return {offset:OTA.offset+index*4096,bytes,current:current||null};
}

export async function verifyRelease(data, now=Date.now()) {
  ensure(data.status==='reviewed-development-release' && /^[a-f0-9]{64}$/.test(data.publisher_key||''),'No authenticated installation release is available.');
  const decode=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  const raw=decode(data.envelope.payload),key=await crypto.subtle.importKey('raw',Uint8Array.from(data.publisher_key.match(/../g),h=>parseInt(h,16)),{name:'Ed25519'},false,['verify']);
  ensure(await crypto.subtle.verify('Ed25519',key,decode(data.envelope.signature),raw),'Release publisher verification failed.');
  const policy=JSON.parse(new TextDecoder().decode(raw));
  ensure(matchesContract(policy.compatibility),'This release targets a different board, layout, version or firmware lineage.','profile_contract_mismatch');
  ensure(policy.installable===true && policy.profile===PROFILE && policy.chip_revision===103 && policy.flash_bytes===FLASH_BYTES,'Incompatible release profile.');
  ensure(Number.isFinite(Date.parse(policy.expires_at)) && Date.parse(policy.expires_at)>now,'Release approval expired.');
  ensure(policy.bootloader_review && policy.c6_review && policy.recovery_review,'Compatibility/recovery review is missing.');
  for(const value of [policy.bootloader_sha256,policy.table_sha256,policy.app?.sha256]) ensure(/^[a-f0-9]{64}$/.test(value||''),'Missing release fingerprints.');
  ensure(Number.isInteger(policy.app.size) && policy.app.size>0 && policy.app.size<=SLOT.size && policy.app.offset===SLOT.offset,'App exceeds the stock target slot.');
  return policy;
}

export async function makePlan(file, report, policy, app) {
  ensure(matchesContract(policy.compatibility) && report.owner_confirmed_profile===CONTRACT.profile_id,
    'Confirm the printed Waveshare 7B model. A shared chip or USB identity is insufficient.','model_unconfirmed');
  ensure(report.stock_layout_matches && report.ota_1_erased && report.independent_reads_match,'Verified independent backups and an empty stock slot are required.');
  ensure(await sha256(app)===policy.app.sha256 && app.length===policy.app.size,'App download integrity failed.');
  await inspectImage(app);
  const view=new DataView(app.buffer,app.byteOffset,app.byteLength);
  ensure(app.length>=24 && app[0]===0xe9 && view.getUint16(12,true)===18 && app[23]===1,'Expected a digested ESP32-P4 application.');
  ensure(view.getUint16(15,true)<=103 && (!view.getUint16(17,true) || view.getUint16(17,true)>=103),'Image revision does not include P4 1.3.');
  const boot=new Uint8Array(await file.slice(BOOT,TABLE).arrayBuffer());
  const table=new Uint8Array(await file.slice(TABLE,(TABLE+4096)).arrayBuffer());
  ensure(await sha256(boot)===policy.bootloader_sha256 && await sha256(table)===policy.table_sha256,'This stock bootloader/table has not been reviewed for the release.');
  const otadata=new Uint8Array(await file.slice(OTA.offset,(OTA.offset+OTA.size)).arrayBuffer()),selection=selectBoot(otadata);
  const appPadded=new Uint8Array(Math.ceil(app.length/4096)*4096).fill(255);appPadded.set(app);
  return {profile:PROFILE,backup_sha256:report.sha256,app_sha256:policy.app.sha256,
    writes:[{name:'AMPVE application',offset:SLOT.offset,bytes:appPadded,sha256:await sha256(appPadded)},
      {name:'Boot selection (one sector)',offset:selection.offset,bytes:selection.bytes,sha256:await sha256(selection.bytes)}],
    recovery:[{name:'restore-otadata.bin',offset:OTA.offset,bytes:otadata},
      {name:'restore-nvs-after-boot.bin',offset:PARTITIONS.nvs.offset,bytes:new Uint8Array(await file.slice(PARTITIONS.nvs.offset,OTA.offset).arrayBuffer())},
      {name:'restore-ota1-touched-sectors.bin',offset:SLOT.offset,bytes:new Uint8Array(await file.slice(SLOT.offset,SLOT.offset+appPadded.length).arrayBuffer())}]};
}

export async function executePlan(reader, plan, policy, consent, progress=()=>{}, signal) {
  ensure(consent?.exact_plan===true && consent?.separate_copy===true && consent?.rom_recovery===true,'Explicit plan and recovery confirmation required.');
  ensure(matchesContract(policy?.compatibility),'Prepare a matching versioned release.','profile_contract_mismatch');
  ensure(plan.profile===PROFILE && policy?.installable===true && Date.parse(policy.expires_at)>Date.now() && plan.app_sha256===policy.app.sha256,'Invalid or expired plan.');
  ensure(plan.writes.length===2 && plan.writes[0].offset===SLOT.offset && plan.writes[0].bytes.length<=SLOT.size &&
    [OTA.offset,(OTA.offset+4096)].includes(plan.writes[1].offset) && plan.writes[1].bytes.length===4096,'Unexpected write regions.');
  const hash=await createSHA256();hash.init();
  // Re-read the whole physical flash on this SAME connection before the first write.
  // This rejects stale backups and any swapped device. No MAC-based ownership claim.
  for(let at=0;at<FLASH_BYTES;at+=BLOCK) {
    hash.update(await readChunk(reader,at,BLOCK,signal));progress('Final device/backup comparison',at+BLOCK,FLASH_BYTES);
  }
  ensure(hash.digest('hex')===plan.backup_sha256,'The connected flash changed. Make new backups before installing.');
  for(const item of plan.writes) ensure(await sha256(item.bytes)===item.sha256,'Plan bytes changed.');
  if(signal?.aborted) throw new DOMException('Cancelled','AbortError');
  ensure(Date.parse(policy.expires_at)>Date.now(),'Release approval expired during preflight. Prepare a new approved plan.');
  // After this point do not cancel/disconnect automatically. App first, readback,
  // then one boot-selection sector. No full erase, bootloader/table or C6 writes.
  for(const item of plan.writes) {
    progress('Writing '+item.name,0,item.bytes.length);
    await reader.loader.writeFlash({fileArray:[{data:item.bytes,address:item.offset}],flashSize:'keep',flashMode:'keep',flashFreq:'keep',eraseAll:false,compress:true,
      reportProgress:(_,written,total)=>progress('Writing '+item.name,written,total)});
    const verify=await createSHA256();verify.init();
    for(let at=0;at<item.bytes.length;at+=BLOCK) {
      const size=Math.min(BLOCK,item.bytes.length-at);
      verify.update(await readChunk(reader,item.offset+at,size));progress('Verifying '+item.name,at+size,item.bytes.length);
    }
    ensure(verify.digest('hex')===item.sha256,'Write verification failed. Keep power stable and use the saved recovery plan.');
  }
  await reader.loader.after('hard_reset');
  return {written_and_read_back:true,physical_startup_verified:false};
}
