import {inspectPreparedInstallation} from './installation-preflight.js';
import {resetApplication} from './reset.js';
// AMPVE's guarded integration uses ESP Web Tools manifest conventions and its
// pinned esptool-js writer. Its generic install dialog cannot keep our audited
// connection or verify the app before switching boot selection; do not expose it.
import crc32 from 'pako/lib/zlib/crc32.js';
import {createSHA256} from 'hash-wasm';
import {ensure,sha256,inspectImage,readChunk,readTransferDiagnostics,FLASH_BYTES,BLOCK,PROFILE} from './audit.js';
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
  const fields=['schema','key_id','sequence','channel','purpose','installable','profile','compatibility','chip_revision',
    'flash_bytes','expires_at','repository_commit','firmware_version','app','bootloader_sha256','table_sha256',
    'bootloader_review','c6_review','recovery_review','provenance'];
  if(Object.hasOwn(policy,'commissioning')||Object.hasOwn(policy,'usb_review')){
    ensure(policy.commissioning==='usb-assisted-v1' && typeof policy.usb_review==='string' && policy.usb_review.trim() && policy.usb_review.length<=1000 && !policy.usb_review.includes('REPLACE'),'USB commissioning review is missing.');
    fields.push('commissioning','usb_review');
  }
  ensure(Object.keys(policy).length===fields.length && fields.every(key=>Object.hasOwn(policy,key)) && policy.schema===2 &&
    policy.purpose==='initial-install' && policy.channel==='development','This is not an approved USB installation policy.');
  ensure(typeof policy.key_id==='string' && /^[a-z0-9][a-z0-9-]{0,63}$/.test(policy.key_id) &&
    Number.isInteger(policy.sequence) && policy.sequence>=1 && policy.sequence<=2147483647 &&
    Number.isInteger(data.minimum_sequence) && data.minimum_sequence>=1 && policy.sequence>=data.minimum_sequence,'Release sequence or trusted floor is invalid.');
  ensure(await sha256(raw)===data.release_id,'Release identity does not match its signed bytes.');
  ensure(/^[a-f0-9]{40}$/.test(policy.repository_commit||'') && /^[A-Za-z0-9._+-]{1,31}$/.test(policy.firmware_version||''),'Release source/version missing.');
  const hashes=['review_manifest_sha256','archive_sha256','sdkconfig_sha256','dependency_lock_sha256'];
  ensure(policy.provenance && Object.keys(policy.provenance).length===6 && hashes.every(key=>/^[a-f0-9]{64}$/.test(policy.provenance[key]||'')) &&
    ['xiaozhi_commit','esp_idf_commit'].every(key=>/^[a-f0-9]{40}$/.test(policy.provenance[key]||'')),'Release provenance is incomplete.');
  ensure(matchesContract(policy.compatibility),'This release targets a different board, layout, version or firmware lineage.','profile_contract_mismatch');
  ensure(policy.installable===true && policy.profile===PROFILE && policy.chip_revision===103 && policy.flash_bytes===FLASH_BYTES,'Incompatible release profile.');
  ensure(typeof policy.expires_at==='string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(policy.expires_at) && Number.isFinite(Date.parse(policy.expires_at)) && Date.parse(policy.expires_at)>now,'Release approval expired.');
  ensure(['bootloader_review','c6_review','recovery_review'].every(key=>typeof policy[key]==='string' && policy[key].trim() && policy[key].length<=1000 && !policy[key].includes('REPLACE')),'Compatibility/recovery review is missing.');
  for(const value of [policy.bootloader_sha256,policy.table_sha256,policy.app?.sha256]) ensure(/^[a-f0-9]{64}$/.test(value||''),'Missing release fingerprints.');
  ensure(Object.keys(policy.app).length===3 && Number.isInteger(policy.app.size) && policy.app.size>=24 && policy.app.size<=SLOT.size && policy.app.offset===SLOT.offset,'App exceeds the stock target slot.');
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
    bootloader_sha256:policy.bootloader_sha256,table_sha256:policy.table_sha256,current_selection:selection.current,
    writes:[{name:'AMPVE application',offset:SLOT.offset,bytes:appPadded,sha256:await sha256(appPadded)},
      {name:'Boot selection (one sector)',offset:selection.offset,bytes:selection.bytes,sha256:await sha256(selection.bytes)}],
    recovery:[{name:'restore-otadata.bin',offset:OTA.offset,bytes:otadata},
      {name:'restore-nvs-after-boot.bin',offset:PARTITIONS.nvs.offset,bytes:new Uint8Array(await file.slice(PARTITIONS.nvs.offset,OTA.offset).arrayBuffer())},
      {name:'restore-ota1-touched-sectors.bin',offset:SLOT.offset,bytes:new Uint8Array(await file.slice(SLOT.offset,SLOT.offset+appPadded.length).arrayBuffer())}]};
}

// Preparation from authenticated candidate bytes is deliberately not write authority.
export async function makeReviewPlan(file, report, candidate, app) {
  ensure(candidate.status==='development-review' && candidate.installable===false && candidate.profile===PROFILE,
    'No matching review candidate is available.');
  ensure(candidate.app?.offset===SLOT.offset && Number.isInteger(candidate.app.size) && candidate.app.size>=24 && candidate.app.size<=SLOT.size,
    'Invalid candidate application region.');
  const boot=report.images?.find(image=>image.name==='bootloader');
  const fingerprints=[boot?.region_sha256,report.table_sha256,candidate.app.sha256];
  ensure(fingerprints.every(value=>/^[a-f0-9]{64}$/.test(value||'')),'Verified backup fingerprints are required.');
  const plan=await makePlan(file,report,{compatibility:CONTRACT,app:candidate.app,
    bootloader_sha256:boot.region_sha256,table_sha256:report.table_sha256},app);
  return {...plan,review_only:true};
}

export function planReviewSummary(plan) {
  ensure(plan?.writes?.length===2,'Prepare the exact plan first.');
  return {schema:1,kind:'ampve-browser-plan-review',installable:false,compatibility:CONTRACT,
    backup_sha256:plan.backup_sha256,bootloader_sha256:plan.bootloader_sha256,
    table_sha256:plan.table_sha256,candidate_sha256:plan.app_sha256,
    current_physical_state_verified:false,
    current_selection:plan.current_selection?{sequence:plan.current_selection.seq,state:plan.current_selection.state,index:plan.current_selection.index}:null,
    proposed_regions:plan.writes.map(({offset,bytes,sha256})=>({offset,size:bytes.length,sha256})),
    recovery_files_saved:plan.recovery_saved===true,
    remaining:['Review exact stock bootloader and C6 compatibility','Publisher approval and current-unit comparison','Owner approval of exact physical writes']};
}

async function executePlanRun(reader, plan, policy, consent, progress, signal, revalidate, trace) {
  ensure(plan?.review_only!==true,'An unsigned review plan cannot write hardware.');
  ensure(consent?.exact_plan===true && consent?.separate_copy===true && consent?.rom_recovery===true,'Explicit plan and recovery confirmation required.');
  ensure(matchesContract(policy?.compatibility),'Prepare a matching versioned release.','profile_contract_mismatch');
  ensure(plan.profile===PROFILE && policy?.installable===true && Date.parse(policy.expires_at)>Date.now() && plan.app_sha256===policy.app.sha256,'Invalid or expired plan.');
  ensure(plan.writes.length===2 && plan.writes[0].offset===SLOT.offset && plan.writes[0].bytes.length<=SLOT.size &&
    [OTA.offset,(OTA.offset+4096)].includes(plan.writes[1].offset) && plan.writes[1].bytes.length===4096,'Unexpected write regions.');
  trace.phase='preflight';
  if(!await inspectPreparedInstallation(reader,plan,policy,progress,signal)){
    const hash=await createSHA256();hash.init();
    for(let at=0;at<FLASH_BYTES;at+=BLOCK){
      hash.update(await readChunk(reader,at,BLOCK,signal,n=>progress('Final device/backup comparison',at+n,FLASH_BYTES)));
      progress('Final device/backup comparison',at+BLOCK,FLASH_BYTES);
    }
    ensure(hash.digest('hex')===plan.backup_sha256,'The connected flash changed. Make new backups before installing.');
  }
  for(const item of plan.writes) ensure(await sha256(item.bytes)===item.sha256,'Plan bytes changed.');
  // Recheck revocation/trust after a potentially long full-flash comparison.
  trace.phase='release_revalidation';
  await revalidate();
  if(signal?.aborted) throw new DOMException('Cancelled','AbortError');
  ensure(Date.parse(policy.expires_at)>Date.now(),'Release approval expired during preflight. Prepare a new approved plan.');
  // After this point do not cancel/disconnect automatically. App first, readback,
  // then one boot-selection sector. No full erase, bootloader/table or C6 writes.
  for(const item of plan.writes) {
    trace.phase=item.offset===SLOT.offset?'app_write':'selection_write';trace.write_attempted=true;
    progress('Writing '+item.name,0,item.bytes.length);
    await reader.loader.writeFlash({fileArray:[{data:item.bytes,address:item.offset}],flashSize:'keep',flashMode:'keep',flashFreq:'keep',eraseAll:false,compress:true,
      reportProgress:(_,written,total)=>progress('Writing '+item.name,written,total)});
    trace.phase=item.offset===SLOT.offset?'app_readback':'selection_readback';
    const verify=await createSHA256();verify.init();
    for(let at=0;at<item.bytes.length;at+=BLOCK) {
      const size=Math.min(BLOCK,item.bytes.length-at);
      verify.update(await readChunk(reader,item.offset+at,size));progress('Verifying '+item.name,at+size,item.bytes.length);
    }
    ensure(verify.digest('hex')===item.sha256,'Write verification failed. Keep power stable and use the saved recovery plan.');
    trace[item.offset===SLOT.offset?'app_readback_verified':'selection_readback_verified']=true;
  }
  trace.phase='restart';
  await resetApplication(reader);
  trace.reset_completed=true;trace.phase='complete';
  return {written_and_read_back:true,physical_startup_verified:false};
}

// Only signed policy metadata can defer the pre-install C6 query.
export function allowsUsbCommissioning(policy){return policy?.purpose==='initial-install' && policy.commissioning==='usb-assisted-v1';}

export async function executePlan(reader,plan,policy,consent,progress=()=>{},signal,revalidate=async()=>{}){
  const started=performance.now();
  const trace={schema:1,kind:'ampve-installation-result',expected_version:policy?.firmware_version,
    expected_app_sha256:policy?.app?.sha256,phase:'validation',preflight_bytes:0,write_attempted:false,
    app_readback_verified:false,selection_readback_verified:false,reset_completed:false,physical_startup_verified:false};
  try{
    const result=await executePlanRun(reader,plan,policy,consent,(phase,done,total)=>{
      if(trace.phase==='preflight')trace.preflight_bytes=done;
      progress(phase,done,total);
    },signal,revalidate,trace);
    return {...result,installation_summary:{...trace,...readTransferDiagnostics(reader),outcome:'written_and_verified',elapsed_ms:Math.round(performance.now()-started)}};
  }catch(error){
    const category=error.readFailure?.code||(['AbortError','TimeoutError','TypeError'].includes(error.name)?error.name:'operation_failed');
    error.installationSummary={...trace,...(trace.phase==='validation'?{}:readTransferDiagnostics(reader)),...(error.readFailure?{read_failure:error.readFailure}:{}),outcome:'failed',error_category:category,elapsed_ms:Math.round(performance.now()-started)};
    if(trace.app_readback_verified&&trace.selection_readback_verified){
      error.userMessage='AMPVE and its startup selection were written and verified. The automatic restart did not complete. Reconnect USB and check AMPVE startup.';
    }else if(!error.userMessage){
      error.userMessage=`Installation stopped during ${trace.phase.replaceAll('_',' ')}. ${trace.write_attempted?'The write may be incomplete.':'No flash write was attempted.'}`;
    }
    throw error;
  }
}
