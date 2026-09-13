import {CustomReset,Transport} from 'esptool-js';
import {APPLICATION_RESET_SEQUENCE} from './reset.js';
import {ensure} from './audit.js';
const fields=['kind','schema','nonce','phase','firmware_version','app_sha256','core_confirmed','wifi_initialized','display_ready','touch_ready'];
export function runtimeStatus(line,nonce,expected){
  ensure(line.length<=768,'Oversized USB status.');const data=JSON.parse(line);
  ensure(JSON.stringify(data)===line && Object.keys(data).length===fields.length && fields.every(k=>Object.hasOwn(data,k)) &&
    data.kind==='ampve-usb-status' && data.schema===1 && data.nonce===nonce && /^[a-f0-9]{32}$/.test(nonce),'Invalid USB status.');
  ensure(['starting','checking_profile','opening_storage','checking_boot_counter','starting_core','starting_peripherals','network_starting','network_initialized','network_unavailable'].includes(data.phase),'Unknown startup phase.');
  ensure(['core_confirmed','wifi_initialized','display_ready','touch_ready'].every(k=>typeof data[k]==='boolean') &&
    data.firmware_version===expected.version && (data.app_sha256==='' || data.app_sha256===expected.sha256) &&
    (!data.core_confirmed || /^[a-f0-9]{64}$/.test(data.app_sha256)),'USB runtime does not match the installed application.');
  const {nonce:_,...summary}=data;return summary;
}

// One reader owns the application UART. ROM flashing and Improv run in separate phases.
export async function checkRuntime(port,expected,onReport=()=>{},signal,timeout=90000,restart=false){
  ensure(/^[a-f0-9]{64}$/.test(expected.sha256),'Missing installed application identity.');
  let reader,writer,timer,retry,opened=false,cancel,stopped=false,sendError;let expired=false;
  let observedBytes=0,lastStatus=null;const observations=new Set();
  try{
    if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
    if(restart){const info=port.getInfo?.();ensure(info?.usbVendorId===0x1a86 && info?.usbProductId===0x55d3,'Select the 7B USB TO UART port for automatic restart.');}
    await port.open({baudRate:115200});opened=true;
    reader=port.readable.getReader();writer=port.writable.getWriter();
    cancel=()=>reader.cancel().catch(()=>{});signal?.addEventListener('abort',cancel,{once:true});
    timer=setTimeout(()=>{expired=true;cancel();},timeout);
    // No transport.connect/readLoop: this adapter only drives the reset pins.
    if(restart)await new CustomReset(new Transport(port),APPLICATION_RESET_SEQUENCE).reset();
    const nonce=Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
    const request=new TextEncoder().encode('AMPVE_STATUS '+nonce+'\n');
    const send=async()=>{
      if(stopped||expired||signal?.aborted)return;
      try{await writer.write(request);}catch(error){sendError=error;cancel();return;}
      if(!stopped&&!expired&&!signal?.aborted)retry=setTimeout(send,1000);
    };
    await send();let buffer='';
    while(true){
      if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
      const {value,done}=await reader.read();
      if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
      ensure(!done&&!expired&&!sendError,'AMPVE startup was not confirmed. Download the startup result or use original-backup recovery.');
      observedBytes+=value.length;ensure(observedBytes<=65536,'USB diagnostic output exceeded its bound.');
      buffer+=new TextDecoder().decode(value);
      const lines=buffer.split('\n');buffer=lines.pop();if(buffer.length>768)buffer='';
      for(const raw of lines){
        const line=raw.trim();
        if(line.startsWith('{"kind":"ampve-usb-status"')){
          const report=runtimeStatus(line,nonce,expected);lastStatus=report;onReport(report);
          if(report.core_confirmed)return report;
        }else for(const observation of bootObservations(line))observations.add(observation);
      }
    }
  }catch(error){
    // Fixed categories only. Never include raw UART logs, credentials or device identity.
    error.startupSummary={schema:1,kind:'ampve-usb-startup-failure',expected_version:expected.version,
      expected_app_sha256:expected.sha256,serial_opened:opened,received_bytes:observedBytes,
      timed_out:expired,cancelled:signal?.aborted===true,observations:[...observations].sort(),
      last_status:lastStatus,physical_startup_verified:false};
    throw error;
  }finally{
    stopped=true;clearTimeout(timer);clearTimeout(retry);if(cancel)signal?.removeEventListener('abort',cancel);
    if(reader){await reader.cancel().catch(()=>{});reader.releaseLock();}
    if(writer)writer.releaseLock();
    if(opened)await port.close().catch(()=>{});
  }
}

export function bootObservations(line){
  if(line.length>768)return [];
  const categories=[
    ['download_mode',/waiting for download|DOWNLOAD\([^)]*\)/i],
    ['invalid_image',/invalid header:|image at .* has invalid magic|No bootable app partitions|invalid segment length/i],
    ['panic',/Guru Meditation Error|abort\(\) was called|assert failed:/i],
    ['watchdog',/watchdog got triggered|Task watchdog|TG[01]WDT_SYS_RST|RTCWDT_RTC_RST/i],
    ['memory_initialization',/PSRAM ID read error|PSRAM init failed|Failed to allocate/i],
  ];
  return categories.filter(([,pattern])=>pattern.test(line)).map(([name])=>name);
}
