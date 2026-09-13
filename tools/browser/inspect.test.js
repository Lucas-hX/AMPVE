import test from 'node:test';
import assert from 'node:assert/strict';
globalThis.document = {querySelector: () => null};
const {inspectPort} = await import('../../apps/platform/static/workspace/inspect.bundle.js');

test('ROM inspection reads P4 identity, resets and releases the port without flash methods', async () => {
  const calls = [];
  class Transport {async disconnect(){calls.push('disconnect');}}
  class Loader {
    constructor(){this.chip={CHIP_NAME:'ESP32-P4',getChipDescription:async()=>{calls.push('read-description');return 'ESP32-P4 (revision v1.3)';}};}
    async connect(mode, attempts){calls.push([mode,attempts]);}
    async after(mode){calls.push(mode);}
  }
  assert.deepEqual(await inspectPort({},Loader,Transport),{chip:'ESP32-P4',description:'ESP32-P4 (revision v1.3)'});
  assert.deepEqual(calls,[['default_reset',3],'read-description','hard_reset','disconnect']);
});

test('failed ROM connection still releases the port', async () => {
  let disconnected = false;
  class Transport {async disconnect(){disconnected=true;}}
  class Loader {async connect(){throw new Error('fixture disconnected');}}
  await assert.rejects(inspectPort({},Loader,Transport));
  assert.equal(disconnected,true);
});
