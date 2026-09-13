import {resetApplication} from './reset.js';
// Exact return-to-stock preparation. Never restore arbitrary uploaded region files.
import {FLASH_BYTES,BLOCK,ensure,sha256,readChunk} from './audit.js';
import {PARTITIONS,CONTRACT} from './profile.js';
import {createSHA256} from 'hash-wasm';

const cancelled=signal=>{if(signal?.aborted)throw new DOMException('Cancelled','AbortError');};
const prepared=new WeakMap();

export async function prepareRecovery(backup,report,installation) {
  ensure(backup?.size===FLASH_BYTES && report?.matching_files===true && report.independent_reads_match===true,
    'Select the verified original backup first.');
  ensure(report.stock_layout_matches===true && report.ota_1_erased===true && installation?.backup_sha256===report.sha256,
    'Recovery must use the original backup and its installation plan.');
  const app=installation.writes?.[0];
  ensure(app?.offset===PARTITIONS.ota_1.offset && app.bytes instanceof Uint8Array && app.bytes.length>0 &&
    app.bytes.length<=PARTITIONS.ota_1.size && app.bytes.length%4096===0,'Invalid original installation region.');
  const original=new Uint8Array(await backup.arrayBuffer());
  ensure(await sha256(original)===report.sha256,'Original backup changed.');
  // Selection is restored last. Neither bootloader/table nor factory/ota_0 is writable.
  const regions=[{name:'Original settings',offset:PARTITIONS.nvs.offset,size:PARTITIONS.nvs.size},
    {name:'Original empty AMPVE area',offset:app.offset,size:app.bytes.length},
    {name:'Original startup selection',offset:PARTITIONS.otadata.offset,size:PARTITIONS.otadata.size}];
  const writes=[];
  for(const region of regions){
    const bytes=original.slice(region.offset,region.offset+region.size);
    writes.push({...region,bytes,sha256:await sha256(bytes)});
  }
  const plan={compatibility:CONTRACT,backup_sha256:report.sha256,original,writes};
  prepared.set(plan,{backup_sha256:report.sha256,app_size:app.bytes.length});return plan;
}

async function checkPlan(plan){
  ensure(prepared.has(plan),'Prepare recovery in this browser session.');
  const recorded=prepared.get(plan);
  ensure(plan.backup_sha256===recorded.backup_sha256 && await sha256(plan.original)===recorded.backup_sha256,'Recovery source changed.');
  const expected=[PARTITIONS.nvs,PARTITIONS.ota_1,PARTITIONS.otadata];
  ensure(plan.writes.length===3,'Invalid recovery regions.');
  for(let i=0;i<3;i++){
    const item=plan.writes[i],region=expected[i];
    ensure(item.offset===region.offset && item.bytes.length===item.size && item.size>0 && item.size%4096===0 &&
      (i===1?item.size===recorded.app_size:item.size===region.size),'Recovery is outside the original installation regions.');
    ensure(await sha256(item.bytes)===item.sha256 &&
      await sha256(plan.original.slice(item.offset,item.offset+item.size))===item.sha256,'Recovery bytes differ from the original backup.');
  }
}

export async function validateRecovery(reader,plan,progress=()=>{},signal){
  await checkPlan(plan);
  const hash=await createSHA256();hash.init();let changed=0;
  for(let at=0;at<FLASH_BYTES;at+=BLOCK){
    cancelled(signal);const bytes=await readChunk(reader,at,BLOCK,signal);hash.update(bytes);
    for(let i=0;i<bytes.length;i++)if(bytes[i]!==plan.original[at+i]){
      ensure(plan.writes.some(region=>at+i>=region.offset && at+i<region.offset+region.size),
        'Other device software changed. Recovery stopped without writing.');changed++;
    }
    progress('Checking return-to-original readiness',at+bytes.length,FLASH_BYTES);
  }
  return {schema:1,kind:'ampve-recovery-check',current_sha256:hash.digest('hex'),
    original_sha256:plan.backup_sha256,changed_bytes:changed,allowed_regions_only:true,
    already_original:changed===0,physical_restore_verified:false};
}

// Browser restoration requires explicit consent and a fresh whole-flash comparison.
export async function executeRecovery(reader,plan,review,consent,progress=()=>{},signal){
  ensure(consent?.restore_original===true && consent?.discard_ampve_settings===true && consent?.stable_usb_power===true,
    'Confirm return to original software and loss of new settings.');
  const current=await validateRecovery(reader,plan,progress,signal);
  ensure(current.current_sha256===review?.current_sha256,'The device changed after the recovery check. Check again.');
  cancelled(signal);
  if(!current.already_original){
    // Cancellation ends before the first write; preserve the critical restore sequence.
    for(const item of plan.writes){
      await reader.loader.writeFlash({fileArray:[{data:item.bytes,address:item.offset}],flashSize:'keep',flashMode:'keep',flashFreq:'keep',eraseAll:false,compress:true,
        reportProgress:(_,done,total)=>progress('Restoring '+item.name,done,total)});
      const hash=await createSHA256();hash.init();
      for(let at=0;at<item.size;at+=BLOCK)hash.update(await readChunk(reader,item.offset+at,Math.min(BLOCK,item.size-at)));
      ensure(hash.digest('hex')===item.sha256,'Recovery write verification failed. Keep the saved files and USB power.');
    }
  }
  const restored=await validateRecovery(reader,plan,progress);
  ensure(restored.current_sha256===plan.backup_sha256,'Full recovery comparison failed.');
  await resetApplication(reader);
  return {written:!current.already_original,full_backup_readback_verified:true,physical_stock_startup_verified:false};
}
