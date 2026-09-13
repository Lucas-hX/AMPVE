import startupSymbols from './startup-symbols.json';
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
  let reader,writer,timer,retry,panicTimer,opened=false,cancel,stopped=false,sendError;let expired=false,panicCaptured=false;
  let observedBytes=0,lastStatus=null;const observations=new Set(),details=new Set(),programCounters=new Set(),elfPrefixes=new Set(),initFailures=new Map(),assertions=new Map(),heapReports=new Map();
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
      ensure(!panicCaptured,'The device reported a startup panic. Download the startup result; do not repeat installation.');
      ensure(!done&&!expired&&!sendError,'AMPVE startup was not confirmed. Download the startup result or use original-backup recovery.');
      observedBytes+=value.length;ensure(observedBytes<=65536,'USB diagnostic output exceeded its bound.');
      buffer+=new TextDecoder().decode(value);
      const lines=buffer.split('\n');buffer=lines.pop();if(buffer.length>768)buffer='';
      for(const raw of lines){
        const line=raw.trim();
        if(line.startsWith('{"kind":"ampve-usb-status"')){
          const report=runtimeStatus(line,nonce,expected);lastStatus=report;onReport(report);
          if(report.core_confirmed)return report;
        }else {
          for(const observation of bootObservations(line))observations.add(observation);
          const evidence=bootFailureDetails(line);
          const heap=startupHeap(line);
          if(heap)heapReports.set(heap.phase,heap);
          const assertion=startupAssertion(line);
          if(assertion&&assertions.size<4)assertions.set(JSON.stringify(assertion),assertion);
          for(const detail of evidence.details)details.add(detail);
          for(const pc of evidence.program_counters)if(programCounters.size<8)programCounters.add(pc);
          for(const prefix of evidence.elf_prefixes)if(elfPrefixes.size<4)elfPrefixes.add(prefix);
          for(const failure of evidence.init_failures)if(initFailures.size<4)initFailures.set(failure.function_address,failure);
          // Preserve a bounded tail for the panic PC/register line, then stop repeated boots.
          if(observations.has('panic')&&!panicTimer)panicTimer=setTimeout(()=>{panicCaptured=true;cancel();},1000);
        }
      }
    }
  }catch(error){
    // Fixed categories only. Never include raw UART logs, credentials or device identity.
    error.startupSummary={schema:1,kind:'ampve-usb-startup-failure',expected_version:expected.version,
      expected_app_sha256:expected.sha256,serial_opened:opened,received_bytes:observedBytes,
      timed_out:expired,cancelled:signal?.aborted===true,observations:[...observations].sort(),
      capture_stop:signal?.aborted?'cancelled':panicCaptured?'panic_captured':expired?'timeout':observedBytes>65536?'output_limit':'serial_or_validation_error',
      failure_details:[...details].sort(),panic_program_counters:[...programCounters],observed_elf_sha256_prefixes:[...elfPrefixes],startup_initializer_failures:resolveStartupInitializers(expected,[...elfPrefixes],[...initFailures.values()]),
      assertion_locations:[...assertions.values()],startup_heap:[...heapReports.values()],last_status:lastStatus,physical_startup_verified:false};
    throw error;
  }finally{
    stopped=true;clearTimeout(timer);clearTimeout(retry);clearTimeout(panicTimer);if(cancel)signal?.removeEventListener('abort',cancel);
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

// Exact fixed tokens and instruction addresses only: no raw line, paths, task names,
// stack contents, arbitrary register values, Wi-Fi credentials or NVS data.
export function bootFailureDetails(raw){
  const result={details:[],program_counters:[],elf_prefixes:[],init_failures:[]};if(raw.length>768)return result;
  const line=raw.replace(/\x1b\[[0-9;]*m/g,'');
  const patterns=[
    ['psram_id_read_error',/PSRAM ID read error/i],
    ['psram_init_failed',/PSRAM init failed|SPI RAM enabled but initialization failed/i],
    ['psram_memory_test_failed',/SPI SRAM memory test fail|PSRAM memory test fail/i],
    ['psram_memory_barrier_allocation',/Failed to allocate dummy cacheline for PSRAM memory barrier/i],
    ['psram_interrupt_allocation',/Failed to allocate MSPI psram interrupt/i],
    ['lvgl_psram_pool_allocation',/LvglPsramPool.*Failed to allocate [0-9]+ bytes in PSRAM/i],
    ['allocation_failed',/Failed to allocate/i],
    ['sha_aligned_input_allocation',/esp-sha.*Failed to allocate aligned SPIRAM memory/i],
    ['sha_aligned_buffer_allocation',/esp-sha.*Failed to allocate aligned internal memory/i],
    ['hosted_thread_allocation',/Failed to allocate thread handle/i],
    ['hosted_serial_allocation',/Failed to allocate serial data/i],
    ['error_check_failed',/ESP_ERROR_CHECK failed:/i],
    ['assertion_failed',/assert failed:/i],
    ['runtime_task_allocation_failed',/^AMPVE runtime task allocation failed$/],
    ['abort_called',/abort\(\) was called/i],
    ['load_access_fault',/Guru Meditation Error.*Load access fault/i],
    ['store_access_fault',/Guru Meditation Error.*Store access fault/i],
    ['illegal_instruction',/Guru Meditation Error.*Illegal instruction/i],
    ['stack_overflow',/stack overflow|Stack protection fault|Stack canary watchpoint triggered/i],
  ];
  result.details=patterns.filter(([,pattern])=>pattern.test(line)).map(([name])=>name);
  const match=line.match(/(?:abort\(\) was called at PC |ESP_ERROR_CHECK failed:.*? at |\bMEPC\s*:\s*)(0x[0-9a-f]{8})\b/i);
  if(match){const pc=Number.parseInt(match[1],16);
    if((pc>=0x48000000&&pc<0x4c000000)||(pc>=0x4ff00000&&pc<0x4ffa0000)||(pc>=0x30100000&&pc<0x30102000))result.program_counters.push('0x'+pc.toString(16));
  }
  const init=line.match(/\binit function (0x[0-9a-f]{8}) has failed \((0x[0-9a-f]{1,8})\), aborting\s*$/i);
  if(init){const pc=Number.parseInt(init[1],16);
    if((pc>=0x48000000&&pc<0x4c000000)||(pc>=0x4ff00000&&pc<0x4ffa0000)||(pc>=0x30100000&&pc<0x30102000)){
      result.init_failures.push({function_address:'0x'+pc.toString(16),error_code:'0x'+Number.parseInt(init[2],16).toString(16)});
      result.details.push('system_initializer_failed');
    }
  }
  const elf=line.match(/\bELF file SHA256:\s*([a-f0-9]{8,64})(?:\.\.\.)?\s*$/i);
  if(elf)result.elf_prefixes.push(elf[1].toLowerCase());
  return result;
}

// Read-only symbol labels never authorize installation or replace the live identity check.
export function resolveStartupInitializers(expected,prefixes,failures){
  const symbols=startupSymbols.find(build=>build.app_sha256===expected.sha256);
  const matches=symbols&&prefixes.length===1&&
    /^[a-f0-9]{8,64}$/.test(prefixes[0])&&symbols.elf_sha256.startsWith(prefixes[0]);
  return failures.map(failure=>({...failure,...(matches&&Object.hasOwn(symbols.functions,failure.function_address)?
    {matched_build_function:symbols.functions[failure.function_address]}:{})}));
}

// Retain source coordinates only, never the assertion expression or absolute build path.
export function startupAssertion(raw){
  if(raw.length>768)return null;
  const line=raw.replace(/\x1b\[[0-9;]*m/g,'');
  const match=line.match(/^assert failed: ([A-Za-z_][A-Za-z0-9_:~]{0,127}) ((?:[A-Za-z0-9_.\/-]+\/)?([A-Za-z0-9_-]{1,96}\.(?:c|cc|cpp|h|hpp))):([0-9]{1,6}) \([^\r\n]*\)\s*$/);
  if(!match||Number(match[4])===0)return null;
  return {function:match[1],file:match[3],line:Number(match[4])};
}

// Firmware-owned checkpoints, bounded numeric counts; no serial text is exported.
export function startupHeap(line){
  const match=line.match(/^AMPVE_BOOT_HEAP (scheduler_pending|runtime_pending) ([0-9]{1,7}) ([0-9]{1,7})$/);
  if(!match)return null;
  const free=Number(match[2]),largest=Number(match[3]);
  if(free>1048576||largest>free)return null;
  return {phase:match[1],internal_free_bytes:free,internal_largest_block_bytes:largest};
}
