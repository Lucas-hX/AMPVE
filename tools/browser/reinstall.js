// Reinstall known AMPVE images through the same ROM connection, without running stock first.
import {ensure,sha256,readChunk,BLOCK} from './audit.js';
import {PARTITIONS} from './profile.js';
import {executePlan} from './install.js';
import {prepareRecovery,validateRecovery} from './recovery.js';

const prepared=new WeakMap();
export async function prepareReinstall(backup,report,plan,policy,previous,previousPolicy){
  ensure(policy.sequence>=previousPolicy.sequence && policy.bootloader_sha256===previousPolicy.bootloader_sha256 &&
    policy.table_sha256===previousPolicy.table_sha256 && JSON.stringify(policy.compatibility)===JSON.stringify(previousPolicy.compatibility),
    'No compatible previous installation reference is available.');
  ensure(plan.backup_sha256===previous.backup_sha256 && plan.app_sha256===policy.app.sha256 && previous.app_sha256===previousPolicy.app.sha256,
    'Installation references do not match the original backup.');
  const size=Math.max(plan.writes[0].bytes.length,previous.writes[0].bytes.length);
  const pad=bytes=>{const out=new Uint8Array(size).fill(255);out.set(bytes);return out;};
  const bytes=pad(plan.writes[0].bytes),hash=await sha256(bytes);
  const original=new Uint8Array(await backup.slice(PARTITIONS.ota_1.offset,PARTITIONS.ota_1.offset+size).arrayBuffer());
  const result={...plan,writes:[{...plan.writes[0],bytes,sha256:hash},plan.writes[1]],
    recovery:plan.recovery.map(item=>item.offset===PARTITIONS.ota_1.offset?{...item,bytes:original}:item)};
  const recovery=await prepareRecovery(backup,report,result);
  prepared.set(result,{recovery,policy:JSON.stringify(policy),app_hash:hash,
    previous_hash:await sha256(pad(previous.writes[0].bytes)),selection_hash:plan.writes[1].sha256,selection_offset:plan.writes[1].offset,
    backup_hash:plan.backup_sha256});
  return {plan:result,recovery};
}

export async function executeInstallOrReinstall(reader,plan,policy,consent,progress,signal,revalidate){
  const known=prepared.get(plan);
  ensure(known && known.policy===JSON.stringify(policy) && plan.backup_sha256===known.backup_hash &&
    plan.writes[0].sha256===known.app_hash && plan.writes[1].sha256===known.selection_hash && plan.writes[1].offset===known.selection_offset,
    'Prepare the verified installation again.');
  const review=await validateRecovery(reader,known.recovery,progress,signal);
  if(!review.already_original){
    const region=known.recovery.writes[1],app=new Uint8Array(region.size);
    for(let at=0;at<app.length;at+=BLOCK)app.set(await readChunk(reader,region.offset+at,Math.min(BLOCK,app.length-at),signal),at);
    const hash=await sha256(app);
    ensure(hash===known.previous_hash || hash===known.app_hash,
      'The installed application is not a recognized AMPVE image. Nothing was written.');
    // Preserve the original confirmed stock boot record. Only AMPVE's selection may differ.
    const untouched=PARTITIONS.otadata.offset+(plan.writes[1].offset===PARTITIONS.otadata.offset?4096:0);
    const record=await readChunk(reader,untouched,4096,signal);
    ensure(await sha256(record)===await sha256(known.recovery.original.slice(untouched,untouched+4096)),
      'Original startup selection changed. Nothing was written.');
  }
  // executePlan repeats the full comparison on this same ROM connection and revalidates
  // release authority immediately before writing. NVS is never written during reinstall.
  return executePlan(reader,{...plan,backup_sha256:review.current_sha256},policy,consent,progress,signal,revalidate);
}
