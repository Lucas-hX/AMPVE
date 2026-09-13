import {createSHA256} from 'hash-wasm';
// Reinstall known AMPVE images through the same ROM connection, without running stock first.
import {ensure,sha256,readChunk,BLOCK,FLASH_BYTES} from './audit.js';
import {PARTITIONS} from './profile.js';
import {prepareRecovery} from './recovery.js';

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
    original:recovery.original.slice(),backup_hash:plan.backup_sha256});
  return {plan:result,recovery};
}

export async function inspectPreparedInstallation(reader,plan,policy,progress,signal){
  const known=prepared.get(plan);
  if(!known)return false;
  ensure(known.policy===JSON.stringify(policy) && plan.backup_sha256===known.backup_hash &&
    plan.writes[0].sha256===known.app_hash && plan.writes[1].sha256===known.selection_hash && plan.writes[1].offset===known.selection_offset,
    'Prepare the verified installation again.');
  const app=known.recovery.writes[1],selection=known.selection_offset;
  const whole=await createSHA256(),image=await createSHA256();whole.init();image.init();
  // One complete read while the same device is stopped in the ROM stub. App identity,
  // protected bytes and the original stock boot record are checked in that same stream.
  for(let at=0;at<FLASH_BYTES;at+=BLOCK){
    const bytes=await readChunk(reader,at,BLOCK,signal,n=>progress('Checking device before installation',at+n,FLASH_BYTES));
    whole.update(bytes);
    const lo=Math.max(at,app.offset),hi=Math.min(at+bytes.length,app.offset+app.size);
    if(hi>lo)image.update(bytes.subarray(lo-at,hi-at));
    for(let i=0;i<bytes.length;i++){
      const address=at+i;
      if(bytes[i]===known.original[address])continue;
      ensure((address>=app.offset&&address<app.offset+app.size)||
        (address>=PARTITIONS.nvs.offset&&address<PARTITIONS.nvs.offset+PARTITIONS.nvs.size)||
        (address>=selection&&address<selection+4096),
        'Other device software or original startup selection changed. Nothing was written.');
    }
    progress('Checking device before installation',at+bytes.length,FLASH_BYTES);
  }
  if(whole.digest('hex')!==known.backup_hash){
    const hash=image.digest('hex');
    ensure(hash===known.previous_hash || hash===known.app_hash,
      'The installed application is not a recognized AMPVE image. Nothing was written.');
  }
  return true;
}
