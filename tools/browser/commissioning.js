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
export async function checkRuntime(port,expected,onReport=()=>{},signal,timeout=90000){
  ensure(/^[a-f0-9]{64}$/.test(expected.sha256),'Missing installed application identity.');
  let reader,writer,timer,opened=false,cancel;let expired=false;
  try{
    if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
    await port.open({baudRate:115200});opened=true;
    reader=port.readable.getReader();writer=port.writable.getWriter();
    cancel=()=>reader.cancel().catch(()=>{});signal?.addEventListener('abort',cancel,{once:true});
    timer=setTimeout(()=>{expired=true;cancel();},timeout);
    let buffer='',total=0;
    while(true){
      if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
      ensure(!expired,'AMPVE startup confirmation timed out. Use USB recovery if setup cannot continue.');
      const nonce=Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
      await writer.write(new TextEncoder().encode('AMPVE_STATUS '+nonce+'\n'));
      let report;
      while(!report){
        const {value,done}=await reader.read();
        if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
        ensure(!done && !expired,'AMPVE stopped responding during USB setup.');
        total+=value.length;ensure(total<=65536,'USB diagnostic output exceeded its bound.');
        buffer+=new TextDecoder().decode(value);
        const lines=buffer.split('\n');buffer=lines.pop();if(buffer.length>768)buffer='';
        for(const raw of lines){const line=raw.trim();if(line.startsWith('{"kind":"ampve-usb-status"'))report=runtimeStatus(line,nonce,expected);}
      }
      onReport(report);
      if(report.core_confirmed)return report;
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
  }finally{
    clearTimeout(timer);if(cancel)signal?.removeEventListener('abort',cancel);
    if(reader){await reader.cancel().catch(()=>{});reader.releaseLock();}
    if(writer)writer.releaseLock();
    if(opened)await port.close().catch(()=>{});
  }
}
