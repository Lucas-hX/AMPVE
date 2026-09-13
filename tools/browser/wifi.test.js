import {improvFixes} from './improv-build.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
if(!globalThis.CustomEvent)globalThis.CustomEvent=class extends Event{constructor(type,options){super(type);this.detail=options?.detail;}};
await build({plugins:[improvFixes],entryPoints:['wifi.js'],bundle:true,platform:'node',format:'esm',outfile:'build/wifi-test.mjs'});
const {openWifi,validCredentials}=await import('./build/wifi-test.mjs');
function frame(type,data){const out=[73,77,80,82,79,86,1,type,data.length,...data];out.push(out.reduce((a,b)=>a+b,0)&255);return new Uint8Array([10,...out,10]);}
function rpc(command,strings){const data=strings.flatMap(s=>{const b=[...new TextEncoder().encode(s)];return [b.length,...b];});return frame(4,[command,data.length,...data]);}
class FakePort{
 state=1;firmware='AMPVE';closed=0;writes=[];fail=false;initError=false;writeError=false;disconnect=false;
 async open(options){assert.equal(options.baudRate,115200);this.readable=new ReadableStream({start:c=>this.input=c});this.writable=new WritableStream({write:bytes=>{
  assert.equal(bytes[7],3);this.writes.push(bytes[9]);const command=bytes[9];
  if(this.writeError)throw new Error('Simulated transport failure');
  if(this.initError){this.input.enqueue(frame(2,[255]));return;}
  if(this.disconnect){this.input.close();return;}
  if(command===2){this.input.enqueue(frame(1,[this.state]));if(this.state===4)this.input.enqueue(rpc(2,['https://untrusted.invalid/']));}
  if(command===3)this.input.enqueue(rpc(3,[this.firmware,'fixture','waveshare-p4-7b','Fixture']));
  if(command===1){if(this.fail){this.input.enqueue(frame(2,[3]));return;}this.state=4;this.input.enqueue(frame(1,[4]));this.input.enqueue(rpc(1,['https://untrusted.invalid/']));}
 }});}
 async close(){assert.equal(this.readable.locked,false);assert.equal(this.writable.locked,false);this.closed++;}
}
test('byte limits reject malformed credentials',()=>{
 assert.ok(validCredentials('Fixture',''));assert.ok(validCredentials('é'.repeat(16),'x'.repeat(64)));
 for(const pair of [['','x'],['é'.repeat(17),'x'],['a','x'.repeat(65)],['a\0b','x'],['a','b\0c']])assert.equal(validCredentials(...pair),false);
});
test('SDK refuses writes without physical authorization',async()=>{
 const port=new FakePort();const wifi=await openWifi(port);assert.equal(wifi.state,1);await assert.rejects(wifi.provision('Fixture','fixture-password'));assert.deepEqual(port.writes,[2,3]);await wifi.close();assert.equal(port.closed,1);
});
test('SDK receives connected state and ignores supplied URL',async()=>{
 const port=new FakePort();port.state=2;const wifi=await openWifi(port);await wifi.provision('Fixture','fixture-password');assert.equal(wifi.state,4);assert.equal(wifi.nextUrl,undefined);await wifi.close();
});
test('unsupported firmware closes before credential writes',async()=>{
 const port=new FakePort();port.firmware='Other';await assert.rejects(openWifi(port));assert.deepEqual(port.writes,[2,3]);assert.equal(port.closed,1);
});
test('connection error rejects and releases reader',async()=>{
 const port=new FakePort();port.state=2;port.fail=true;const wifi=await openWifi(port);await assert.rejects(wifi.provision('Fixture','fixture-password'));await wifi.close();assert.equal(port.closed,1);
});

for(const mode of ['initError','writeError','disconnect'])test(`initial ${mode} settles and releases the port`,async()=>{
 const port=new FakePort();port[mode]=true;await assert.rejects(openWifi(port));assert.equal(port.closed,1);
});

test('failed open does not close a port owned by another consumer',async()=>{
 const port={async open(){throw new Error('Occupied');},async close(){assert.fail('Not our port');}};
 await assert.rejects(openWifi(port));
});
test('idle disconnect removes authorization from browser controls',async()=>{
 const port=new FakePort();port.state=2;const wifi=await openWifi(port);port.input.close();await new Promise(resolve=>setTimeout(resolve,0));assert.equal(wifi.state,undefined);await assert.rejects(wifi.provision('Fixture','fixture-password'));await wifi.close();
});
