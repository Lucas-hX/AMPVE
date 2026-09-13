import {openReader,readChunk,captureRead,compareBackups,parseTable,matchesStock,ensure,sha256,FLASH_BYTES} from './audit.js';
import {verifyRelease,makePlan,makeReviewPlan,planReviewSummary,executePlan,allowsUsbCommissioning} from './install.js';
import {prepareReinstall,executeInstallOrReinstall} from './reinstall.js';
import {openWifi,validCredentials} from './wifi.js';
import {CONTRACT} from './profile.js';
import {reviewSummary} from './review.js';
import {recognizeBaseline} from './baselines.js';
import {checkRuntime} from './commissioning.js';
import {runProbe} from './c6-probe.js';
import {prepareRecovery,validateRecovery,executeRecovery} from './recovery.js';

const root=document.querySelector('#firmware-setup');
if(root) {
  const get=id=>document.getElementById(id),status=get('setup-status'),meter=get('setup-progress'),detail=get('setup-progress-detail');
  let reinstallReference;
  let wifi,c6Observation,recoveryPlan,installedRuntime,recoveryMode=false,currentFlashChanged=false;
  const downloadUrls=new Map();
  function downloadLink(id,summary){
    const old=downloadUrls.get(id);if(old)URL.revokeObjectURL(old);
    const url=URL.createObjectURL(new Blob([JSON.stringify(summary,null,2)+"\n"],{type:"application/json"}));
    downloadUrls.set(id,url);get(id).href=url;get(id).hidden=false;
  }
  function show(id){get(id).hidden=false;}
  function continueTo(id){show(id);get(id).scrollIntoView({behavior:"smooth",block:"start"});}
  get("wifi-step").hidden=true;
  get("pairing-step").hidden=!get("pairing-step").querySelector(".errorlist");
  let reportSource;
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
    get('export-review').hidden=!report||!downloadUrls.has('export-review');
    get('export-plan-review').hidden=!plan||!downloadUrls.has('export-plan-review');
    get('export-review').setAttribute('aria-disabled',String(busy||!report));
    get('check-recovery').disabled=busy||!plan||!port;
    get('restore-original').disabled=busy||!recoveryPlan||!navigator.serial;
    get('check-c6').disabled=busy||!port||!get('board-confirm').checked;
    get('save-recovery').disabled=busy||!plan||!window.showDirectoryPicker;
    get('export-plan-review').setAttribute('aria-disabled',String(busy||!plan));
    get('approve-plan').disabled=busy||!policy||plan?.review_only===true;
    get('install-ampve').disabled=busy||((recoveryMode||currentFlashChanged)&&!reinstallReference)||!policy||plan?.review_only===true||!plan?.recovery_saved||!navigator.serial||
      (!allowsUsbCommissioning(policy)&&(!c6Observation?.version_matches||!c6Observation.unit_identity||c6Observation.unit_identity!==report?.hardware?.identity))||
      !get('approve-plan').checked||!get('separate-copy').checked||!get('rom-recovery').checked;
    get('cancel-setup').disabled=!busy||writing||!controller;
    get('import-backups').disabled=busy;
    get('connect-wifi').disabled=busy||!navigator.serial;
    get('send-wifi').disabled=busy||wifi?.state!==2;
    get('close-wifi').disabled=busy||!wifi;
    get('wifi-password').disabled=busy;
    get('wifi-ssid').disabled=busy;
  }
  async function close(){if(wifi){const active=wifi;wifi=null;await active.close().catch(()=>{});}if(reader){await reader.transport.disconnect().catch(()=>{});reader=null;}}
  async function run(task,cancellable=true) {
    if(busy)return;busy=true;writing=false;controller=cancellable?new AbortController():null;lastPhase='';sync();
    try{await task(controller?.signal);}catch(error){
      // Never display raw transport data or exception messages from serial libraries.
      status.textContent=error.name==='AbortError'?'Stopped. Incomplete reads are not valid backups.':
        error.userMessage||'Setup stopped. Check the cable, programming port and current operation. No installation is approved by a failed check.';
      if(error.startupSummary){downloadLink('export-runtime-review',error.startupSummary);recoveryMode=true;installedRuntime=null;show('device-confirmation');show('backup-step');show('existing-backups');get('wifi-step').hidden=true;status.textContent='AMPVE did not start. Select your original backup files below to prepare installation of the latest version.';}
      detail.textContent=writing?'A write may be incomplete. Keep your recovery files; use the reviewed USB recovery procedure.':
        'If AMPVE did not start, use Repair or reinstall AMPVE. Keep the original backups. Use the USB TO UART port; an accessible RESET button is not required for the first automatic reconnect attempt.';
      if(error.installationSummary){
        downloadLink('export-install-result',error.installationSummary);
        detail.textContent=error.installationSummary.app_readback_verified&&error.installationSummary.selection_readback_verified?
          'Flash verification completed. The remaining step is USB startup checking.':
          `Installation result: ${error.installationSummary.phase.replaceAll('_',' ')}. Use Download installation result below; the backup summary describes only your saved files.`;
      }
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
  async function showReport() {
    const compatible=report.stock_layout_matches&&report.ota_1_erased;
    get('backup-result').textContent='Your saved copies match and have been checked. They stay on your computer.';
    get('installation-choice').textContent=compatible?'Available for review: add AMPVE while keeping your previous software.':'No compatible installation is available for this device’s current software. Your device has not been changed.';
    downloadLink('export-review',reviewSummary(report,reportSource));
    get('stock-baseline').textContent=recognizeBaseline(report)?'The original software base matches a verified vendor artifact. This identifies the base; it does not approve a release.':'The original software base is not recognized in the current catalog.';
    continueTo('installation-step');
    await prepareInstallation();
  }
  async function inspect(signal){
    ensure(port,'Connect your device first.');get('read-consent').checked=true;
    status.textContent='Checking your device. Its software will not be changed…';
    await freshReader();
    const table=await parseTable(await readChunk(reader,0x8000,4096,signal));
    ensure(matchesStock(table),'This device does not have a supported installation layout. Nothing was changed.');
    get('usb-status').textContent='Device check complete.';
    get('model-evidence').textContent='The chip and saved software match this supported model. Confirm the printed name on your board.';
    show('device-confirmation');status.textContent='Confirm your board to continue.';
    detail.textContent='The check does not test the screen, audio or Wi-Fi.';
    await close();
  }
  get('select-usb').onclick=()=>run(async signal=>{
    await close();port=await navigator.serial.requestPort();plan=null;recoveryPlan=null;
    get('board-confirm').checked=false;get('device-confirmation').hidden=true;
    await inspect(signal);
  });
  get('inspect-chip').onclick=()=>run(inspect);
  get('resume-backups').onclick=()=>{
    show('device-confirmation');
    get('model-evidence').textContent='Resuming from saved files does not check the connected device. Confirm the printed name; AMPVE will check the board again before installation.';
  };
  async function checkC6(signal){
    ensure(get('board-confirm').checked&&port,'Confirm and connect the 7B board first.');
    c6Observation=null;
    get('c6-status').textContent='Checking the connected Wi-Fi hardware…';
    get('export-c6-review').hidden=true;
    const response=await fetch(root.dataset.probe,{cache:'no-store'});
    if(!response.ok){get('c6-status').textContent='The temporary Wi-Fi check is not available yet.';return;}
    const manifest=await response.json();
    const artifact=await fetch(root.dataset.probe+'?artifact=1',{cache:'no-store'});
    ensure(artifact.ok,'Temporary Wi-Fi check unavailable.');await close();
    status.textContent='Checking the Wi-Fi hardware without installing software…';
    const result=await runProbe(port,new Uint8Array(await artifact.arrayBuffer()),manifest,progress,signal);
    c6Observation=result;
    downloadLink('export-c6-review',{schema:1,kind:'ampve-c6-diagnostic-summary',profile:CONTRACT,
      diagnostic_sha256:manifest.sha256,status:result.status,version:result.version,version_matches:result.version_matches,error_code:result.error_code,
      wifi_function_verified:false,physical_recovery_verified:false,installable:false});
    get('c6-status').textContent=result.version_matches?'Wi-Fi hardware check passed: ESP32-C6, firmware '+result.version.join('.')+'. Network setup is checked after AMPVE starts.':
      ({version_query_failed:'The Wi-Fi firmware version query failed.',connection_failed:'The Wi-Fi connection could not be initialized.',host_init_failed:'The temporary Wi-Fi checker could not initialize.',task_start_failed:'The temporary Wi-Fi checker has insufficient memory.',event_loop_failed:'The temporary Wi-Fi checker could not start.',timeout:'The Wi-Fi hardware did not respond in time.'}[result.status]||'Wi-Fi compatibility could not be confirmed.')+' This result does not confirm Wi-Fi operation. An approved USB setup release can check networking after installation.';
    detail.textContent='This check does not prove a working Wi-Fi session or successful recovery. The next step reconnects the board automatically.';
  }
  get('confirm-device').onclick=()=>run(async signal=>{
    ensure(get('board-confirm').checked,'Confirm the board name first.');
    if(recoveryMode){continueTo('backup-step');show('existing-backups');return;}
    const available=await (await fetch(root.dataset.release,{cache:'no-store'})).json();
    const defer=available.status==='development-review'?available.commissioning==='usb-assisted-v1':available.status==='reviewed-development-release'&&allowsUsbCommissioning(await verifyRelease(available));
    if(defer)get('c6-status').textContent='Wi-Fi will be checked after AMPVE starts. Keep USB connected throughout setup.';
    if(port&&!defer)try{await checkC6(signal);}catch(error){
      if(error.name==='AbortError')throw error;
      get('c6-status').textContent='The Wi-Fi check could not finish. You can still prepare your backups; installation remains unavailable.';
    }
    continueTo('backup-step');
  });
  get('check-c6').onclick=()=>run(checkC6);
  get('check-recovery').onclick=()=>run(checkRecovery);
  async function checkRecovery(signal){
    boardConsent();ensure(plan&&port,'Prepare the installation and connect this board first.');
    const recovery=await prepareRecovery(backup,report,plan);recoveryPlan=recovery;await freshReader();
    const result=await validateRecovery(reader,recovery,progress,signal);
    currentFlashChanged=!result.already_original;
    show('restore-panel');
    get('recovery-status').textContent=result.already_original?'The connected flash matches your original backup. No restoration was needed or performed.':
      'Differences are limited to the expected installation/settings areas. No restoration was performed.';
    status.textContent='Recovery comparison complete. The device was not changed.';
  }
  get('recover-device').onclick=()=>{
    recoveryMode=true;installedRuntime=null;plan=null;show('device-confirmation');get('wifi-step').hidden=true;
    get('model-evidence').textContent='Confirm the board name, then select your original backups. Setup will check whether AMPVE can be reinstalled directly over USB.';
    status.textContent='Recovery mode. Use your backups from before AMPVE was installed.';
    get('device-confirmation').scrollIntoView({behavior:'smooth'});sync();
  };
  get('use-existing').onclick=()=>{show('existing-backups');get('import-backups').focus();};
  get('already-installed').onclick=()=>{show('wifi-step');continueTo('pairing-step');};
  get('capture-backup').onclick=()=>run(async signal=>{
    boardConsent();report=null;plan=null;recoveryPlan=null;get('backup-result').textContent='No completed backup in this session.';
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
    reportSource='live-browser-capture';
    await save(directory,'audit-private.json',JSON.stringify(report,null,2)+'\n');
    await save(directory,'SHA256SUMS.txt',`${report.sha256}  backup-a.bin\n${report.sha256}  backup-b.bin\n`);
    status.textContent='Backup complete and verified. Nothing installed.';await showReport();
    // Keep the second connection in ROM; no application boot between backup and installation.
  });
  get('import-backups').onchange=event=>run(async signal=>{
    report=null;plan=null;recoveryPlan=null;
    const files=[...event.target.files],bins=files.filter(f=>f.name.endsWith('.bin')),records=files.filter(f=>f.name.endsWith('.json'));
    ensure(bins.length===2&&records.length===1&&records[0].size<100000,'Select two backups and their completed audit JSON.');
    ensure(bins[0]!==bins[1],'Select two backup files.');
    const record=JSON.parse(await records[0].text());
    const result=await compareBackups(bins[0],bins[1],progress,signal);
    ensure(record.independent_reads_match===true && record.sha256===result.sha256 && record.hardware?.chip==='ESP32-P4' && record.hardware.revision===103,'Completed independent capture evidence is required.');
    report={...result,independent_reads_match:true,hardware:record.hardware,evidence:'Owner-supplied capture record; files rehashed locally.'};backup=bins[0];
    reportSource='imported-capture-record';
    status.textContent='Local files verified. Checking the available installation automatically…';await showReport();
  });
  for(const id of ['export-review','export-plan-review','export-install-result'])get(id).onclick=event=>{
    if(busy||!downloadUrls.has(id)){event.preventDefault();return;}
    // Downloading support evidence must never replace the operation's result or error.
  };
  get('prepare-install').onclick=()=>run(prepareInstallation);
  async function prepareInstallation(){
    plan=null;policy=null;reinstallReference=null;get('release-status').textContent='Checking availability…';get('candidate-download').hidden=true;get('export-plan-review').hidden=true;get('plan-panel').hidden=true;status.textContent='Checking the curated AMPVE release…';
    const response=await fetch(root.dataset.release,{cache:'no-store'});ensure(response.ok,'Release unavailable.');
    const data=await response.json();
    const approved=data.status==='reviewed-development-release';
    if(!approved && data.status!=='development-review') {
      status.textContent='Backups are ready. Installation is waiting for a reviewed release.';
      get('release-status').textContent='No approved installation is available yet. Your device has not been changed.';
      detail.textContent=(data.remaining||['No publisher-approved package is available.']).join(' · ');
      return;
    }
    if(approved)policy=await verifyRelease(data);
    const appInfo=approved?policy.app:data.app;
    ensure(appInfo && /^[a-f0-9]{64}$/.test(appInfo.sha256),'Candidate identity missing.');
    const appResponse=await fetch(`/devices/firmware/artifacts/${appInfo.sha256}.bin`,{cache:'no-store'});
    ensure(appResponse.ok,'App unavailable.');
    ensure(get('board-confirm').checked,'Confirm the printed board model before preparing an installation.');
    const checkedReport={...report,owner_confirmed_profile:CONTRACT.profile_id};
    const app=new Uint8Array(await appResponse.arrayBuffer());
    plan=approved?await makePlan(backup,checkedReport,policy,app):await makeReviewPlan(backup,checkedReport,data,app);
    if(approved){
      const previousResponse=await fetch(root.dataset.release+'?recovery=1',{cache:'no-store'});
      ensure(previousResponse.ok,'Previous installation reference unavailable.');
      const previousPolicy=await verifyRelease(await previousResponse.json());
      const previousApp=await fetch(`/devices/firmware/artifacts/${previousPolicy.app.sha256}.bin?recovery=1`,{cache:'no-store'});
      ensure(previousApp.ok,'Previous installation reference unavailable.');
      const previousPlan=await makePlan(backup,checkedReport,previousPolicy,new Uint8Array(await previousApp.arrayBuffer()));
      const prepared=await prepareReinstall(backup,report,plan,policy,previousPlan,previousPolicy);
      plan=prepared.plan;recoveryPlan=prepared.recovery;reinstallReference=previousPolicy;
    }
    get('candidate-info').textContent=`Stock-preserving candidate · ${(appInfo.size/1048576).toFixed(2)} MiB · SHA-256 ${appInfo.sha256}`;
    const link=get('candidate-download');link.href='/devices/firmware/review-bundle/';link.hidden=approved;
    const list=get('write-regions');list.replaceChildren();
    for(const item of plan.writes) {const li=document.createElement('li');li.textContent=`${item.name}: 0x${item.offset.toString(16)} · ${item.bytes.length} bytes · SHA-256 ${item.sha256}`;list.append(li);}
    get('plan-panel').hidden=false;get('approve-plan').checked=false;
    downloadLink('export-plan-review',planReviewSummary(plan));
    recoveryPlan=await prepareRecovery(backup,report,plan);show('restore-panel');
    // Physical preflight runs once, at installation time, on the connection used to write.
    if((recoveryMode||currentFlashChanged)&&!reinstallReference){
      get('release-status').textContent='Use USB startup checking or restore your original software. A changed device cannot be treated as a new installation.';
      status.textContent='Original-backup recovery prepared. No software has been changed.';
      show('wifi-step');return;
    }
    get('installation-method').textContent=(approved?allowsUsbCommissioning(policy):data.commissioning==='usb-assisted-v1')?'Keep original software · install AMPVE, then finish setup over USB. Wi-Fi and peripherals are checked after installation.':'Keep original software · verify Wi-Fi compatibility before installation.';
    get('release-status').textContent=approved?'Ready to install after you save your return-to-original files.':'This board’s first AMPVE release is still being validated. Installation is not available yet. Your device has not been changed.';
    status.textContent=approved?'Installation prepared. Save your return-to-original files to continue.':'Candidate compared with your backups. The installation option is prepared for review.';
    if(reinstallReference){get('installation-method').textContent=`Install AMPVE ${policy.firmware_version} · automatically replace a recognized AMPVE installation if present. Original software and saved settings are kept. No successful startup or return to original software is required first.`;get('install-ampve').textContent='Install AMPVE';}
    detail.textContent=approved?'': 'You do not need to run commands or interpret technical details. The development review must finish before installation becomes available.';
  }
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
    plan.recovery_saved=true;downloadLink('export-plan-review',planReviewSummary(plan));status.textContent='Recovery files saved and checked on your computer.';
  });
  get('install-ampve').onclick=()=>run(async signal=>{
    if(!port)port=await navigator.serial.requestPort();get('read-consent').checked=true;boardConsent();ensure(!(recoveryMode||currentFlashChanged)||reinstallReference,'Prepare the known installation reference first.');ensure(policy&&plan?.review_only!==true,'A reviewed signed release is required before installation.');ensure(plan?.recovery_saved&&port,'Save recovery files and select the same board first.');
    const consent={exact_plan:get('approve-plan').checked,separate_copy:get('separate-copy').checked,rom_recovery:get('rom-recovery').checked};
    ensure(Object.values(consent).every(Boolean),'Confirm the exact write/recovery plan first.');
    // Revalidate approval/signature at click time, then hold the same transport through all writes.
    const response=await fetch(root.dataset.release,{cache:'no-store'});ensure(response.ok,'Release unavailable.');
    const current=await verifyRelease(await response.json());
    ensure(JSON.stringify(current)===JSON.stringify(policy),'Release changed; prepare a new plan.');
    if(!reader)await freshReader();
    ensure(allowsUsbCommissioning(policy) || (c6Observation?.version_matches && c6Observation.unit_identity &&
      c6Observation.unit_identity===reader.hardware.identity),'Complete the Wi-Fi hardware check on this unit before installing.');
    recoveryPlan=await prepareRecovery(backup,report,plan);show('restore-panel');
    const installed=await (reinstallReference?executeInstallOrReinstall:executePlan)(reader,plan,policy,consent,progress,signal,async()=>{
      const response=await fetch(root.dataset.release,{cache:'no-store'});ensure(response.ok,'Release unavailable.');
      const latest=await verifyRelease(await response.json());
      ensure(JSON.stringify(latest)===JSON.stringify(policy),'Release or publisher trust changed; prepare a new plan.');
      if(reinstallReference){const previous=await fetch(root.dataset.release+'?recovery=1',{cache:'no-store'});ensure(previous.ok && JSON.stringify(await verifyRelease(await previous.json()))===JSON.stringify(reinstallReference),'Previous release or publisher trust changed; prepare again.');}
    });downloadLink('export-install-result',installed.installation_summary);await close();
    writing=false;recoveryMode=false;currentFlashChanged=false;get('cancel-setup').disabled=false;
    const expectedVersion=policy.firmware_version;
    const usbAssisted=allowsUsbCommissioning(policy);plan=null;
    if(usbAssisted){
      show('wifi-step');status.textContent='AMPVE written and verified. Checking its startup over USB…';
      await new Promise(resolve=>setTimeout(resolve,3000));
      installedRuntime={version:expectedVersion,sha256:policy.app.sha256};
      const runtime=await checkRuntime(port,installedRuntime,report=>{
        get('runtime-status').textContent='AMPVE is responding over USB. Checking its core before continuing…';
      },signal);
      downloadLink('export-runtime-review',runtime);
      get('runtime-status').textContent=runtime.wifi_initialized?'AMPVE core confirmed over USB. Continue with Wi-Fi setup.':'AMPVE core confirmed over USB. Wi-Fi still needs configuration or compatibility work.';
      status.textContent='AMPVE responds over USB. Continue setup while the device stays connected.';
      detail.textContent='USB startup is confirmed. Wi-Fi, display and other features are checked separately during setup.';
      show('wifi-step');show('pairing-step');return;
    }
    status.textContent='AMPVE was installed and checked. Confirm that its home screen appears on your board, then connect Wi-Fi below.';
    detail.textContent='Open Wi-Fi on the board and use USB Wi-Fi setup below or its temporary protected network. Then enter the AMPVE pairing code. USB write success does not prove physical startup or pairing.';
    show('wifi-step');show('pairing-step');get('wifi-step').scrollIntoView({behavior:'smooth'});
  });
  get('check-startup').onclick=()=>run(async signal=>{
    if(!port)port=await navigator.serial.requestPort();
    // Release the ROM reader; the startup checker pulses reset after opening its sole reader.
    await close();
    if(!installedRuntime){
      const response=await fetch(root.dataset.release+(recoveryMode?'?recovery=1':''),{cache:'no-store'});ensure(response.ok,'Release unavailable.');
      const expected=await verifyRelease(await response.json());
      ensure(allowsUsbCommissioning(expected),'This release does not support USB startup checks.');
      installedRuntime={version:expected.firmware_version,sha256:expected.app.sha256};
    }
    const result=await checkRuntime(port,installedRuntime,()=>{get('runtime-status').textContent='AMPVE responds. Waiting for its core check…';},signal,90000,true);
    downloadLink('export-runtime-review',result);
    get('runtime-status').textContent=result.wifi_initialized?'AMPVE core confirmed. Wi-Fi initialization completed; check connection below.':'AMPVE core confirmed. Wi-Fi remains pending.';
    status.textContent='USB startup checked. Network connection and dashboard pairing are separate steps.';
  });
  get('restore-original').onclick=()=>{
    if(!window.confirm('Return to your original software? This restores your saved original settings and removes AMPVE settings from this installation. Keep USB power connected until finished.'))return;
    run(async signal=>{
      ensure(recoveryPlan&&get('board-confirm').checked,'Confirm the board and select its original backups first.');
      if(!port)port=await navigator.serial.requestPort();
      get('read-consent').checked=true;
      await freshReader();
      const review=await validateRecovery(reader,recoveryPlan,progress,signal);
      // The full read is cancellable. Lock cancellation before any restore write.
      writing=true;get('cancel-setup').disabled=true;
      await executeRecovery(reader,recoveryPlan,review,{restore_original:true,discard_ampve_settings:true,stable_usb_power:true},progress);
      await close();recoveryPlan=null;installedRuntime=null;plan=null;policy=null;currentFlashChanged=false;recoveryMode=false;
      show('recovered-next');status.textContent='Original flash restored and verified. Confirm that the original application starts on the board, then use the link to start AMPVE installation again.';
    });
  };
  function wifiState(state){
    const labels={1:'Open Wi-Fi on the board to allow setup for five minutes.',2:'The board allows Wi-Fi setup. Enter your 2.4 GHz network.',3:'Checking and saving Wi-Fi. Keep the board connected.',4:'The board reports a Wi-Fi connection. Continue with its AMPVE pairing code.'};
    get('wifi-status').textContent=labels[state]||'USB Wi-Fi disconnected. Reconnect to check the board.';
    sync();
  }
  get('connect-wifi').onclick=()=>run(async()=>{
    const selected=await navigator.serial.requestPort();
    await close();port=selected;plan=null;
    get('wifi-status').textContent='Connecting to the running AMPVE firmware…';
    // Select before awaiting transport work. No reset/download-mode commands are sent.
    wifi=await openWifi(port,wifiState);wifiState(wifi.state);
  },false);
  get('send-wifi').onclick=()=>run(async()=>{
    const ssid=get('wifi-ssid').value,password=get('wifi-password').value;
    get('wifi-password').value='';
    ensure(wifi?.state===2&&validCredentials(ssid,password),'Open Wi-Fi on the board and check the network name/password lengths.');
    get('wifi-status').textContent='Waiting for the board to save and reconnect…';
    try{await wifi.provision(ssid,password);wifiState(wifi.state);}
    catch(error){get('wifi-status').textContent='Wi-Fi was not confirmed. Check the board and reopen local setup before retrying.';throw error;}
  },false);
  get('close-wifi').onclick=()=>run(async()=>{get('wifi-password').value='';await close();wifiState(undefined);},false);
  get('cancel-setup').onclick=()=>{if(!writing)controller?.abort();};
  for(const id of ['approve-plan','separate-copy','rom-recovery'])get(id).addEventListener('change',sync);
  navigator.serial?.addEventListener('disconnect',event=>{if(event.target===port&&!busy){port=null;plan=null;close();status.textContent='Selected board disconnected. Reconnect before continuing.';sync();}});
  window.addEventListener('beforeunload',event=>{if(busy){event.preventDefault();event.returnValue='';}});
  if(!navigator.serial){get('select-usb').hidden=true;get('usb-status').textContent='Use desktop Chrome or Edge for Web Serial. You can still inspect existing backup files locally.';}
  if(!window.showDirectoryPicker)get('storage-support').textContent='Direct backup storage requires desktop Chrome or Edge with File System Access. No backup will be uploaded to AMPVE.';
  sync();
}
