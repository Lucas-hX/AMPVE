import {openReader,readChunk,captureRead,compareBackups,parseTable,matchesStock,ensure,sha256,FLASH_BYTES} from './audit.js';
import {verifyRelease,makePlan,executePlan} from './install.js';
import {CONTRACT} from './profile.js';

const root=document.querySelector('#firmware-setup');
if(root) {
  const get=id=>document.getElementById(id),status=get('setup-status'),meter=get('setup-progress'),detail=get('setup-progress-detail');
  let port,reader,report,backup,plan,policy,busy=false,controller,writing=false,phaseStart=0,lastPhase='',lastPaint=0;
  const actions=[...root.querySelectorAll('button[data-action]')];
  function progress(phase,done,total) {
    if(phase===lastPhase && done<total && performance.now()-lastPaint<250)return;
    lastPaint=performance.now();
    if(phase!==lastPhase){lastPhase=phase;phaseStart=performance.now();}
    const seconds=(performance.now()-phaseStart)/1000,rate=done/Math.max(seconds,0.1);
    meter.hidden=false;meter.max=total;meter.value=done;
    status.textContent=phase;
    const eta=seconds<3?'Estimating time…':`About ${Math.ceil((total-done)/rate/60)} min remaining in this phase`;
    detail.textContent=`${(done/1048576).toFixed(2)} / ${(total/1048576).toFixed(2)} MiB · ${Math.floor(done/total*100)}% · ${(rate/1024).toFixed(1)} KiB/s · ${eta}`;
    if(phase.startsWith('Writing ')){writing=true;get('cancel-setup').disabled=true;}
  }
  function sync() {
    actions.forEach(b=>b.disabled=busy);
    get('inspect-chip').disabled=busy||!port;
    get('capture-backup').disabled=busy||!port||!window.showDirectoryPicker;
    get('prepare-install').disabled=busy||!report;
    get('install-ampve').disabled=busy||!plan?.recovery_saved||!port||
      !get('approve-plan').checked||!get('separate-copy').checked||!get('rom-recovery').checked;
    get('cancel-setup').disabled=!busy||writing;
    get('import-backups').disabled=busy;
  }
  async function close(){if(reader){await reader.transport.disconnect().catch(()=>{});reader=null;}}
  async function run(task) {
    if(busy)return;busy=true;writing=false;controller=new AbortController();lastPhase='';sync();
    try{await task(controller.signal);}catch(error){
      // Never display raw transport data or exception messages from serial libraries.
      status.textContent=error.name==='AbortError'?'Stopped. Incomplete reads are not valid backups.':
        error.userMessage||'Setup stopped. Check the cable, programming port and current operation. No installation is approved by a failed check.';
      detail.textContent=writing?'A write may be incomplete. Keep your recovery files; use the reviewed USB recovery procedure.':
        'If the board remains in download mode, press RESET to return to its current application. Retry at 115200 baud if transfers repeatedly fail.';
      await close();plan=null;
    }finally{busy=false;writing=false;sync();}
  }
  function boardConsent(){ensure(get('board-confirm').checked&&get('read-consent').checked,'Confirm the board and temporary RAM reader first.');}
  function options(){return {baud:Number(get('read-baud').value)};}
  async function freshReader(){await close();reader=await openReader(port,options());return reader;}
  async function save(directory,name,data) {
    const handle=await directory.getFileHandle(name,{create:true}),writer=await handle.createWritable();
    try {await writer.write(data);await writer.close();}catch(error){await writer.abort().catch(()=>{});throw error;}
    const saved=await handle.getFile();
    ensure(await sha256(new Uint8Array(await saved.arrayBuffer()))===await sha256(typeof data==='string'?new TextEncoder().encode(data):data),'Saved file verification failed.');
    return handle;
  }
  async function folder(){
    const parent=await window.showDirectoryPicker({mode:'readwrite'});
    const name='ampve-'+new Date().toISOString().replace(/[:.]/g,'-')+'-'+crypto.randomUUID().slice(0,8);
    return parent.getDirectoryHandle(name,{create:true});
  }
  function showReport() {
    get('backup-result').textContent=`Two matching 32 MiB files · SHA-256 ${report.sha256}. `+
      (report.stock_layout_matches?'Stock partition profile matches. ':'Partition profile differs; installation blocked. ')+
      (report.ota_1_erased?'Target OTA slot is empty. ':'Target OTA slot is not empty; installation blocked. ')+
      'Backups remain local. Copy this folder to separate private storage.';
  }
  get('select-usb').onclick=()=>run(async()=>{
    await close();port=await navigator.serial.requestPort();plan=null;
    const info=port.getInfo();get('usb-status').textContent=`Port selected · USB vendor ${info.usbVendorId?.toString(16)||'unknown'}, product ${info.usbProductId?.toString(16)||'unknown'}. Confirm the printed 7B label.`;
    status.textContent='Port selected. Ready for a read-only audit.';
  });
  get('inspect-chip').onclick=()=>run(async signal=>{
    boardConsent();status.textContent='Checking chip, security and flash capacity…';
    await freshReader();
    status.textContent='Reading and verifying the partition table…';
    const table=await parseTable(await readChunk(reader,0x8000,4096,signal));
    status.textContent='ESP32-P4 revision 1.3 · 32 MiB flash · Secure Boot and encryption disabled. '+
      (matchesStock(table)?'Stock partition profile matches.':'Different partition profile; stop for review.');
    detail.textContent='Display, touch, audio, PSRAM and C6 compatibility are not proven by this audit. Nothing flashed or paired.';
    await close();
  });
  get('capture-backup').onclick=()=>run(async signal=>{
    boardConsent();report=null;plan=null;get('backup-result').textContent='No completed backup in this session.';
    // Choose storage before any long operation, while the click grants user activation.
    const directory=await folder(),handles=[],hardware=[],hashes=[];
    for(let i=0;i<2;i++) {
      status.textContent=`Connecting for independent read ${i+1} of 2…`;
      await freshReader();hardware.push(reader.hardware);
      if(i)ensure(hardware[0].identity===hardware[1].identity,'The selected chip changed.');
      const handle=await directory.getFileHandle(`backup-${i?'b':'a'}.bin`,{create:true});handles.push(handle);
      hashes.push(await captureRead(reader,handle,signal,(done,total)=>progress(`Reading backup ${i?'B':'A'} · ${i+1} of 2`,done,total)));
    }
    ensure(hashes[0]===hashes[1],'Independent reads differ.');
    backup=await handles[0].getFile();
    report=await compareBackups(backup,await handles[1].getFile(),progress,signal);
    ensure(report.sha256===hashes[0],'Saved files differ from the physical transfer.');
    report={...report,independent_reads_match:true,hardware:hardware[0],connections:hardware,captured_at:new Date().toISOString(),
      evidence:'Two full physical reads in separate ROM connections; both saved files rehashed.'};
    await save(directory,'audit-private.json',JSON.stringify(report,null,2)+'\n');
    await save(directory,'SHA256SUMS.txt',`${report.sha256}  backup-a.bin\n${report.sha256}  backup-b.bin\n`);
    status.textContent='Backup complete and verified. Nothing installed.';showReport();
    // Keep the second connection in ROM; no application boot between backup and installation.
  });
  get('import-backups').onchange=event=>run(async signal=>{
    report=null;plan=null;
    const files=[...event.target.files],bins=files.filter(f=>f.name.endsWith('.bin')),records=files.filter(f=>f.name.endsWith('.json'));
    ensure(bins.length===2&&records.length===1&&records[0].size<100000,'Select two backups and their completed audit JSON.');
    ensure(bins[0]!==bins[1],'Select two backup files.');
    const record=JSON.parse(await records[0].text());
    const result=await compareBackups(bins[0],bins[1],progress,signal);
    ensure(record.independent_reads_match===true && record.sha256===result.sha256 && record.hardware?.chip==='ESP32-P4' && record.hardware.revision===103,'Completed independent capture evidence is required.');
    report={...result,independent_reads_match:true,hardware:record.hardware,evidence:'Owner-supplied capture record; files rehashed locally.'};backup=bins[0];
    showReport();status.textContent='Local files verified. A live comparison is still required before installation.';
  });
  get('prepare-install').onclick=()=>run(async()=>{
    plan=null;status.textContent='Checking the curated AMPVE release…';
    const response=await fetch(root.dataset.release,{cache:'no-store'});ensure(response.ok,'Release unavailable.');
    const data=await response.json();
    if(data.status!=='reviewed-development-release') {
      status.textContent='Backups are ready. Installation is waiting for a reviewed release.';
      detail.textContent=(data.remaining||['No publisher-approved package is available.']).join(' · ');
      if(data.app){
        get('candidate-info').textContent=`Stock-preserving candidate · ${(data.app.size/1048576).toFixed(2)} MiB · SHA-256 ${data.app.sha256}`;
        const link=get('candidate-download');link.href='/devices/firmware/review-bundle/';link.hidden=false;
      }
      return;
    }
    policy=await verifyRelease(data);
    const appResponse=await fetch(`/devices/firmware/artifacts/${policy.app.sha256}.bin`,{cache:'no-store'});
    ensure(appResponse.ok,'App unavailable.');
    ensure(get('board-confirm').checked,'Confirm the printed board model before preparing an installation.');
    plan=await makePlan(backup,{...report,owner_confirmed_profile:CONTRACT.profile_id},policy,new Uint8Array(await appResponse.arrayBuffer()));
    const list=get('write-regions');list.replaceChildren();
    for(const item of plan.writes) {const li=document.createElement('li');li.textContent=`${item.name}: 0x${item.offset.toString(16)} · ${item.bytes.length} bytes · SHA-256 ${item.sha256}`;list.append(li);}
    get('plan-panel').hidden=false;get('approve-plan').checked=false;
    status.textContent='Exact write plan prepared. Save its private recovery files before installing.';
  });
  get('save-recovery').onclick=()=>run(async()=>{
    ensure(plan,'Prepare a plan first.');const directory=await folder();
    for(const item of plan.recovery)await save(directory,item.name,item.bytes);
    const summary={profile:plan.profile,backup_sha256:plan.backup_sha256,installable:false,
      writes:plan.writes.map(({name,offset,bytes,sha256})=>({name,offset,size:bytes.length,sha256})),
      recovery:await Promise.all(plan.recovery.map(async({name,offset,bytes})=>({file:name,offset,size:bytes.length,sha256:await sha256(bytes)}))),
      notes:['Preserve bootloader, table, factory and ota_0. No full-chip erase.',
        'Restore original otadata to return to stock selection; after AMPVE boot NVS may also need restoration.',
        'Restoring original NVS discards new Wi-Fi/AMPVE identity. Review every recovery write separately.']};
    await save(directory,'recovery-plan-private.json',JSON.stringify(summary,null,2)+'\n');
    plan.recovery_saved=true;status.textContent='Recovery files saved and rehashed locally. Review the exact write plan.';
  });
  get('install-ampve').onclick=()=>run(async signal=>{
    boardConsent();ensure(plan?.recovery_saved&&port,'Save recovery files and select the same board first.');
    const consent={exact_plan:get('approve-plan').checked,separate_copy:get('separate-copy').checked,rom_recovery:get('rom-recovery').checked};
    ensure(Object.values(consent).every(Boolean),'Confirm the exact write/recovery plan first.');
    // Revalidate approval/signature at click time, then hold the same transport through all writes.
    const response=await fetch(root.dataset.release,{cache:'no-store'});ensure(response.ok,'Release unavailable.');
    const current=await verifyRelease(await response.json());
    ensure(JSON.stringify(current)===JSON.stringify(policy),'Release changed; prepare a new plan.');
    if(!reader)await freshReader();
    await executePlan(reader,plan,policy,consent,progress,signal,async()=>{
      const response=await fetch(root.dataset.release,{cache:'no-store'});ensure(response.ok,'Release unavailable.');
      const latest=await verifyRelease(await response.json());
      ensure(JSON.stringify(latest)===JSON.stringify(policy),'Release or publisher trust changed; prepare a new plan.');
    });await close();plan=null;
    status.textContent='Firmware written and read back. Check the board screen to confirm startup.';
    detail.textContent='Open Wi-Fi on the board, join its temporary protected network, then return here and enter the AMPVE pairing code. USB write success does not prove physical startup or pairing.';
    get('pairing-step').scrollIntoView({behavior:'smooth'});
  });
  get('cancel-setup').onclick=()=>{if(!writing)controller?.abort();};
  for(const id of ['approve-plan','separate-copy','rom-recovery'])get(id).addEventListener('change',sync);
  navigator.serial?.addEventListener('disconnect',event=>{if(event.target===port&&!busy){port=null;plan=null;close();status.textContent='Selected board disconnected. Reconnect before continuing.';sync();}});
  window.addEventListener('beforeunload',event=>{if(busy){event.preventDefault();event.returnValue='';}});
  if(!navigator.serial){get('select-usb').hidden=true;get('usb-status').textContent='Use desktop Chrome or Edge for Web Serial. You can still inspect existing backup files locally.';}
  if(!window.showDirectoryPicker)get('storage-support').textContent='Direct backup storage requires desktop Chrome or Edge with File System Access. No backup will be uploaded to AMPVE.';
  sync();
}
