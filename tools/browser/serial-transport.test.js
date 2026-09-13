import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {md5} from 'hash-wasm';
await build({stdin:{contents:'export * from "./serial-transport.js"; export {readChunk,readTransferDiagnostics} from "./audit.js";',resolveDir:process.cwd()},bundle:true,platform:'node',format:'esm',outfile:'build/serial-api.mjs'});
const {BufferedTransport,readChunk,readTransferDiagnostics}=await import('./build/serial-api.mjs');
const encode=data=>{const bytes=[192];for(const b of data)bytes.push(...(b===192?[219,220]:b===219?[219,221]:[b]));bytes.push(192);return Uint8Array.from(bytes);};
const concat=(...parts)=>{const bytes=new Uint8Array(parts.reduce((sum,p)=>sum+p.length,0));let at=0;for(const p of parts){bytes.set(p,at);at+=p.length;}return bytes;};

test('linear decoder preserves split escapes, empty separators and multiple frames',async()=>{
  const source=Uint8Array.from({length:4096},(_,i)=>i%256),frame=encode(source);
  for(const boundary of [1,2,193,194,221,1024,frame.length-1]){
    const transport=new BufferedTransport({});
    transport.buffer=frame.slice(0,boundary);
    const pending=transport.read(1000);
    transport.buffer=concat(transport.buffer,frame.slice(boundary),new Uint8Array([192,192]),encode(new Uint8Array([7,8])));
    assert.deepEqual(await pending,source);
    assert.deepEqual(await transport.read(1000),new Uint8Array([7,8]));
  }
});
test('decoder rejects malformed escapes, heads, oversized frames and partial-frame timeout',async()=>{
  for(const [bytes,code] of [[new Uint8Array([1]),'serial_packet_head'],[new Uint8Array([192,219,1]),'serial_packet_escape'],
    [concat(new Uint8Array([192]),new Uint8Array(8193).fill(1)),'serial_packet_limit'],[new Uint8Array([192,1]),'serial_packet_timeout']]){
    const transport=new BufferedTransport({});transport.buffer=bytes;
    await assert.rejects(transport.read(10),error=>error.code===code&&!error.message.includes('private'));
  }
});
test('32 MiB framed transfer stays exact without per-byte append allocations',async()=>{
  const source=Uint8Array.from({length:4096},(_,i)=>i%256),frame=encode(source),transport=new BufferedTransport({});
  transport.appendArray=()=>{throw new Error('Decoder must not append/reallocate per byte');};
  for(let i=0;i<8192;i++){transport.buffer=frame;assert.deepEqual(await transport.read(1000),source);}
});
test('receiver uses a 64 KiB browser buffer, one stream reader and releases it on disconnect',async()=>{
  let input,opens=0;
  const port={async open(options){assert.equal(options.bufferSize,65536);opens++;this.readable=new ReadableStream({start:c=>input=c});},async close(){assert.equal(this.readable.locked,false);this.readable=null;}};
  const transport=new BufferedTransport(port);await transport.connect(460800);
  const receive=transport.readLoop();assert.equal(transport.readLoop(),receive);
  input.enqueue(encode(new Uint8Array([1,192,219,3])));
  assert.deepEqual(await transport.read(1000),new Uint8Array([1,192,219,3]));
  await transport.disconnect();await receive;
  await transport.connect(115200);transport.readLoop();assert.equal(transport.receiveError,null);
  input.enqueue(encode(new Uint8Array([4])));assert.deepEqual(await transport.read(1000),new Uint8Array([4]));
  await transport.disconnect();assert.equal(opens,2);
});
test('serial overrun and bounded queue exhaustion fail closed instead of silently dropping bytes',async()=>{
  for(const mode of ['overrun','queue']){
    let input;const port={async open(){this.readable=new ReadableStream({start:c=>input=c});},async close(){this.readable=null;}};
    const transport=new BufferedTransport(port);await transport.connect();const receive=transport.readLoop();
    if(mode==='overrun')input.error(new DOMException('PRIVATE SERIAL DETAILS','BufferOverrunError'));
    else input.enqueue(new Uint8Array(262145));
    await receive;
    await assert.rejects(transport.read(1000),error=>error.code===(mode==='overrun'?'serial_buffer_overrun':'serial_queue_limit')&&!error.message.includes('PRIVATE'));
    assert.equal(port.readable.locked,false);await transport.disconnect();
  }
});

test('real buffered receiver feeds fragmented flash packets, acknowledgements and the terminal MD5',async()=>{
  let input;const sent=[];
  const port={async open(){this.readable=new ReadableStream({start:c=>input=c});this.writable=new WritableStream({write:bytes=>sent.push(bytes)});},async close(){assert.equal(this.readable.locked,false);assert.equal(this.writable.locked,false);this.readable=null;this.writable=null;}};
  const transport=new BufferedTransport(port);await transport.connect(460800);transport.readLoop();
  const bytes=Uint8Array.from({length:65536},(_,i)=>i%256),frames=[];
  for(let at=0;at<bytes.length;at+=4096)frames.push(encode(bytes.slice(at,at+4096)));
  frames.push(encode(Uint8Array.from((await md5(bytes)).match(/../g),s=>parseInt(s,16))));
  const wire=concat(...frames);
  const reader={transport,loader:{ESP_READ_FLASH:0xd2,checkCommand:async()=>{
    for(let at=0;at<wire.length;at+=997)input.enqueue(wire.slice(at,at+997));
  }}};
  assert.deepEqual(await readChunk(reader,0,65536),bytes);
  assert.equal(readTransferDiagnostics(reader).transport_revision,'buffered-slip-v1');
  assert.equal(sent.length,16);
  assert.deepEqual(sent.at(-1),encode(new Uint8Array([0,0,1,0])));
  assert.equal(transport.buffer.length,0);
  await transport.disconnect();
});
