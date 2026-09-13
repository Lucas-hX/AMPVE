import {ensure,sha256,openReader} from './audit.js';
// P4 rev1 IDF memory.ld: exclude the ROM/bootloader gap and the 128 KiB cache.
const RANGE=[[0x30100000,0x30102000],[0x4ff00000,0x4ff2bbd0],[0x4ff40000,0x4ffa0000]];

export async function ramSegments(bytes,manifest){
  ensure(manifest?.kind==='ampve-c6-ram-probe' && manifest.schema===1 && manifest.chip_revision===103 &&
    manifest.flash_writes===false && bytes.length===manifest.size && bytes.length<=768*1024 &&
    await sha256(bytes)===manifest.sha256,'Diagnostic package integrity failed.');
  ensure(bytes.length>=24 && bytes[0]===0xe9 && bytes[1]>0 && bytes[1]<=16,'Invalid diagnostic image.');
  const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  ensure(v.getUint16(12,true)===18 && v.getUint16(15,true)<=103 && v.getUint16(17,true)>=103,'Diagnostic targets another chip.');
  let cursor=24;const segments=[];
  for(let i=0;i<bytes[1];i++){
    ensure(cursor+8<=bytes.length,'Truncated RAM image.');
    const address=v.getUint32(cursor,true),size=v.getUint32(cursor+4,true);cursor+=8;
    ensure(size>0 && size%4===0 && address%4===0 && cursor+size<=bytes.length &&
      RANGE.some(([low,high])=>address>=low && address+size<=high) &&
      !segments.some(s=>address<s.address+s.bytes.length && s.address<address+size),'Diagnostic region is not allowed RAM.');
    segments.push({address,bytes:bytes.slice(cursor,cursor+size)});cursor+=size;
  }
  const entry=v.getUint32(4,true);
  ensure(entry>=0x4ff00000 && entry<0x4ff2bbd0 && segments.some(s=>entry>=s.address && entry<s.address+s.bytes.length),'Invalid diagnostic entrypoint.');
  return {segments,entry};
}

export function probeResult(line,nonce){
  ensure(typeof line==='string' && line.length<=512 && /^[a-f0-9]{32}$/.test(nonce),'Invalid diagnostic response.');
  ensure(/^\{"kind":"ampve-c6-probe","schema":1,"nonce":"[a-f0-9]{32}","status":"[a-z_]+","version":\[[0-9]+,[0-9]+,[0-9]+\]\}$/.test(line),'Malformed diagnostic frame.');
  const data=JSON.parse(line);
  ensure(Object.keys(data).sort().join(',')==='kind,nonce,schema,status,version' && data.kind==='ampve-c6-probe' &&
    data.schema===1 && data.nonce===nonce && ['observed','unavailable','invalid_version','identity_unavailable','timeout'].includes(data.status) &&
    Array.isArray(data.version) && data.version.length===3 && data.version.every(x=>Number.isInteger(x)&&x>=0&&x<=255),'Diagnostic response does not match this check.');
  return {status:data.status,version:data.version,
    version_matches:data.status==='observed' && data.version.join('.')==='2.12.13',
    wifi_function_verified:false,physical_recovery_verified:false};
}

export async function runProbe(port,bytes,manifest,progress=()=>{},signal,connect=openReader){
  if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
  const image=await ramSegments(bytes,manifest);
  const connection=await connect(port,{baud:115200,stub:false});
  const nonce=Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
  let closed=false,timer,onAbort;
  try{
    for(const segment of image.segments){
      const block=1024;
      await connection.loader.memBegin(segment.bytes.length,Math.ceil(segment.bytes.length/block),block,segment.address);
      for(let at=0;at<segment.bytes.length;at+=block){
        if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
        await connection.loader.memBlock(segment.bytes.slice(at,at+block),at/block);
        progress('Loading temporary Wi-Fi check',at+Math.min(block,segment.bytes.length-at),segment.bytes.length);
      }
    }
    await connection.loader.memFinish(image.entry);
    connection.transport.slipReaderEnabled=false;
    let buffer='',total=0;
    const result=new Promise((resolve,reject)=>{
      onAbort=()=>{closed=true;reject(new DOMException('Cancelled','AbortError'));};
      signal?.addEventListener('abort',onAbort,{once:true});
      if(signal?.aborted){onAbort();return;}
      timer=setTimeout(()=>{closed=true;reject(new Error('Wi-Fi diagnostic timed out'));},30000);
      connection.transport.rawRead(chunk=>{
        total+=chunk.length;
        if(total>16384){closed=true;reject(new Error('Diagnostic output exceeded its bound'));return;}
        buffer+=new TextDecoder().decode(chunk);
        const lines=buffer.split('\n');buffer=lines.pop();
        if(buffer.length>512)buffer='';
        for(const line of lines)if(line.startsWith('{"kind":"ampve-c6-probe"')){
          try{const parsed=probeResult(line.trim(),nonce);closed=true;resolve(parsed);}catch(error){closed=true;reject(error);}
        }
        if(signal?.aborted){closed=true;reject(new DOMException('Cancelled','AbortError'));}
      },()=>closed).catch(reject);
    });
    result.catch(()=>{}); // Preserve the error for await without an early unhandled rejection.
    // The ROM transfer ended. Allow app_main to install its bounded UART receiver.
    await new Promise(resolve=>setTimeout(resolve,1000));
    if(signal?.aborted)throw new DOMException('Cancelled','AbortError');
    const writer=port.writable.getWriter();
    try{await writer.write(new TextEncoder().encode(nonce+'\n'));}finally{writer.releaseLock();}
    try{return {...await result,unit_identity:connection.hardware?.identity};}finally{closed=true;clearTimeout(timer);}
  }finally{
    closed=true;clearTimeout(timer);
    if(onAbort)signal?.removeEventListener('abort',onAbort);
    // Leave no serial reader/task owned by the browser. The next audit resets to ROM.
    await connection.transport.disconnect().catch(()=>{});
  }
}
