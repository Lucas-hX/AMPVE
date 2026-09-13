import {ESPLoader, Transport} from 'esptool-js';
import {createSHA256, md5, sha256} from 'hash-wasm';
import {HARDWARE_PROFILE, PARTITIONS} from './profile.js';

export const FLASH_BYTES = HARDWARE_PROFILE.resources.flash_bytes;
export const BLOCK = 64 * 1024;
export const PROFILE = HARDWARE_PROFILE.installation_id;
export const STOCK = HARDWARE_PROFILE.layout.partitions.map(p=>[p.name,p.type,p.subtype,p.offset,p.size]);
export const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2,'0')).join('');
export function ensure(value, message, code) {if (!value) {const error=new Error(message);error.userMessage=message;if(code)error.code=code;throw error;}}
const words = (...values) => {
  const bytes = new Uint8Array(values.length*4), view = new DataView(bytes.buffer);
  values.forEach((value,i) => view.setUint32(i*4,value,true)); return bytes;
};
const aborted = signal => {if(signal?.aborted) throw new DOMException('Cancelled','AbortError');};

export async function parseTable(bytes, address=0x8000, capacity=FLASH_BYTES) {
  const entries=[];
  for(let cursor=0; cursor<0xc00; cursor+=32) {
    const entry=bytes.slice(cursor,cursor+32);
    ensure(entry.length===32,'Truncated partition table.');
    const view=new DataView(entry.buffer,entry.byteOffset,entry.byteLength);
    if(view.getUint16(0,true)===0xebeb) {
      ensure(entries.length && entry.slice(2,16).every(b=>b===255) &&
        await md5(bytes.slice(0,cursor))===hex(entry.slice(16)), 'Partition MD5 mismatch.');
      return entries;
    }
    ensure(view.getUint16(0,true)===0x50aa,'Missing partition MD5.');
    const raw=entry.slice(12,28), end=raw.indexOf(0);
    const name=String.fromCharCode(...raw.slice(0,end<0?16:end));
    const p={name,type:entry[2],subtype:entry[3],offset:view.getUint32(4,true),size:view.getUint32(8,true),flags:view.getUint32(28,true)};
    ensure(/^[\x20-\x7e]{1,16}$/.test(name),'Invalid partition name.');
    ensure(p.size && !(p.offset%4096) && !(p.size%4096) && p.offset>=address+4096 &&
      p.offset+p.size<=capacity && (p.type!==0 || !(p.offset%65536)), 'Partition exceeds flash or is unaligned.');
    ensure(!entries.some(q=>q.name===name || p.offset<q.offset+q.size && q.offset<p.offset+p.size),'Overlapping or duplicate partition.');
    entries.push(p);
  }
  throw new Error('Missing partition MD5.');
}

export function matchesStock(partitions) {
  return partitions.length===STOCK.length && STOCK.every(([name,type,subtype,offset,size],i)=>{
    const p=partitions[i]; return p.name===name && p.type===type && p.subtype===subtype && p.offset===offset && p.size===size && p.flags===0;
  });
}

export async function inspectImage(bytes) {
  ensure(bytes.length>=24 && bytes[0]===0xe9 && bytes[1]>0 && bytes[1]<=16,'Unknown application/bootloader image.');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  ensure(view.getUint16(12,true)===18 && bytes[23]===1,'Expected a digested ESP32-P4 image.');
  let cursor=24,checksum=0xef;
  for(let i=0;i<bytes[1];i++) {
    ensure(cursor+8<=bytes.length,'Truncated image segment header.');
    const length=view.getUint32(cursor+4,true);cursor+=8;
    ensure(length<=bytes.length-cursor,'Image segment exceeds partition.');
    for(let j=cursor;j<cursor+length;j++)checksum^=bytes[j];cursor+=length;
  }
  const checksumAt=Math.floor(cursor/16)*16+15,end=checksumAt+1;
  ensure(end+32<=bytes.length && bytes[checksumAt]===checksum,'Image checksum mismatch.');
  ensure(await sha256(bytes.slice(0,end))===hex(bytes.slice(end,end+32)),'Image SHA-256 mismatch.');
  const result={image_bytes:end+32,chip_id:18,internal_checksum_verified:true,appended_sha256_verified:true,
    min_revision:view.getUint16(15,true),max_revision:view.getUint16(17,true)};
  if(bytes.length>=288 && view.getUint32(32,true)===0xabcd5432) {
    const field=(offset,length)=>new TextDecoder().decode(bytes.slice(32+offset,32+offset+length)).split('\0')[0].replace(/[^\x20-\x7e]/g,'?');
    result.application={version:field(16,32),project:field(48,32),idf:field(112,32)};
  }
  return result;
}

export async function analyzeBackup(file, progress=()=>{}, signal) {
  ensure(file.size===FLASH_BYTES,'A complete 32 MiB backup is required.');
  const hash=await createSHA256(); hash.init();
  const tables=[];
  let erased=true;
  for(let offset=0;offset<file.size;offset+=BLOCK) {
    aborted(signal);
    const bytes=new Uint8Array(await file.slice(offset,offset+BLOCK).arrayBuffer());
    hash.update(bytes);
    for(let at=0;at<bytes.length;at+=4096) {
      if(bytes[at]===0xaa && bytes[at+1]===0x50) {
        try {tables.push({offset:offset+at,partitions:await parseTable(bytes.slice(at,at+4096),offset+at)});} catch { /* Not a valid table candidate. */ }
      }
    }
    const slot=PARTITIONS[HARDWARE_PROFILE.layout.initial_app];
    const start=Math.max(0,slot.offset-offset),end=Math.min(bytes.length,slot.offset+slot.size-offset);
    if(end>start && !bytes.slice(start,end).every(b=>b===255)) erased=false;
    progress(offset+bytes.length,file.size);
  }
  ensure(tables.length===1,'Expected one unambiguous MD5-verified partition table.');
  const table=tables[0];
  const images=[];
  // Only the reviewed table location establishes the bounded bootloader region here.
  if(table.offset===0x8000) {
    aborted(signal);
    const boot=new Uint8Array(await file.slice(0x2000,0x8000).arrayBuffer());
    images.push({name:'bootloader',offset:0x2000,region_sha256:await sha256(boot),...await inspectImage(boot)});
  }
  for(const p of table.partitions.filter(p=>p.type===0)) {
    aborted(signal);
    const bytes=new Uint8Array(await file.slice(p.offset,p.offset+p.size).arrayBuffer());
    if(bytes.every(b=>b===255)){images.push({name:p.name,erased:true});continue;}
    images.push({name:p.name,offset:p.offset,...await inspectImage(bytes)});
  }
  const table_sha256=await sha256(new Uint8Array(await file.slice(table.offset,table.offset+4096).arrayBuffer()));
  return {schema:1,sha256:hash.digest('hex'),flash_bytes:file.size,partition_table_offset:table.offset,
    partition_table_md5_verified:true,partitions:table.partitions,images,table_sha256,
    stock_layout_matches:table.offset===0x8000 && matchesStock(table.partitions),
    ota_1_erased:erased,installable:false};
}

export function decodeSecurity(bytes) {
  ensure(bytes instanceof Uint8Array && bytes.length===20,'Security state unavailable.','security_unverified');
  const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),flags=v.getUint32(0,true);
  ensure(v.getUint32(12,true)===18 && !(flags&7) && bytes[4]===0,'Unsupported chip or enabled security.','security_unsupported');
  return {flash_crypt_cnt:bytes[4],parsed_flags:{SECURE_BOOT_EN:false,SECURE_BOOT_AGGRESSIVE_REVOKE:false,SECURE_DOWNLOAD_ENABLE:false}};
}

export async function openReader(port, {Loader=ESPLoader,SerialTransport=Transport,baud=460800}={}) {
  const transport=new SerialTransport(port,false);
  const loader=new Loader({transport,baudrate:baud,debugLogging:false,terminal:{clean(){},write(){},writeLine(){}}});
  try {
    await loader.connect('default_reset',3,true);
    const revision=await loader.chip.getChipRevision(loader);
    ensure(loader.chip.CHIP_NAME===HARDWARE_PROFILE.chip.name && revision>=HARDWARE_PROFILE.chip.revision_min &&
      revision<=HARDWARE_PROFILE.chip.revision_max,'Expected ESP32-P4 revision 1.3.','chip_revision_mismatch');
    // GET_SECURITY_INFO is an Espressif ROM command; parse the pinned esptool 5.4.0 format.
    const security=decodeSecurity(await loader.checkCommand('read security',0x14,new Uint8Array(),0,20));
    // ROM SPI_ATTACH includes its reserved legacy word; no flash_begin is used to attach.
    await loader.checkCommand('attach flash',loader.ESP_SPI_ATTACH,words(0,0));
    const flashId=await loader.readFlashId();
    ensure((flashId>>>16 & 255)===25,'Expected a 32 MiB flash chip.','flash_capacity_mismatch');
    const identity=await loader.chip.readMac(loader); // Private RAM/file only, never an ownership proof.
    if(loader.chip.postConnect) await loader.chip.postConnect(loader);
    await loader.runStub();
    await loader.flashSpiAttach(0);
    if(baud!==115200) await loader.changeBaud();
    return {loader,transport,hardware:{chip:'ESP32-P4',revision:103,flash_bytes:FLASH_BYTES,security,identity,reader:'esptool-js-0.6.1',baud}};
  } catch(error) {await transport.disconnect();throw error;}
}

// The pinned esptool-js readFlash omits the terminal MD5 frame and accumulates by copying.
// Use its transport/command implementation with Espressif's documented stub READ_FLASH
// framing, bounded buffers and the digest check used by Python esptool 5.4.0.
export async function readChunk(reader, offset, size, signal, onProgress=()=>{}) {
  aborted(signal);
  ensure(size>0 && size<=BLOCK && !(size%4096),'Invalid bounded read.');
  await reader.loader.checkCommand('read flash',reader.loader.ESP_READ_FLASH,words(offset,size,4096,64));
  const output=new Uint8Array(size); let received=0;
  while(received<size) {
    aborted(signal);
    const packet=await reader.transport.read(5000);
    ensure(packet instanceof Uint8Array && packet.length===Math.min(4096,size-received),'Incomplete flash packet; retry this read.');
    output.set(packet,received); received+=packet.length;
    await reader.transport.write(words(received)); onProgress(received);
  }
  const digest=await reader.transport.read(5000);
  ensure(digest instanceof Uint8Array && digest.length===16 && hex(digest)===await md5(output),'Flash transfer MD5 mismatch.');
  return output;
}

export async function captureRead(reader, handle, signal, progress) {
  const writer=await handle.createWritable(); const hash=await createSHA256();hash.init();
  try {
    for(let offset=0;offset<FLASH_BYTES;offset+=BLOCK) {
      const bytes=await readChunk(reader,offset,BLOCK,signal,n=>progress(offset+n,FLASH_BYTES));
      await writer.write(bytes);hash.update(bytes);
    }
    aborted(signal);await writer.close();return hash.digest('hex');
  } catch(error) {await writer.abort().catch(()=>{});throw error;}
}

export async function compareBackups(first,second,progress=()=>{},signal) {
  const a=await analyzeBackup(first,(n,total)=>progress('Verifying backup A',n,total),signal);
  const b=await analyzeBackup(second,(n,total)=>progress('Verifying backup B',n,total),signal);
  ensure(a.sha256===b.sha256,'Backups differ. Keep both privately and repeat the audit.');
  return {...a,matching_files:true,independent_reads_match:false,
    evidence:'Imported files match; independent physical reads require a capture record or owner evidence.'};
}

export {sha256};
