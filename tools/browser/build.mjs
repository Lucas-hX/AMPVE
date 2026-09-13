import {build} from 'esbuild';
import {appendFileSync, readFileSync} from 'node:fs';
const outfile='../../apps/platform/static/workspace/inspect.bundle.js';
await build({entryPoints:['inspect.js'],bundle:true,format:'esm',minify:true,legalComments:'linked',outfile});
for (const file of ['ESPTOOL-LICENSE','PAKO-LICENSE','ZLIB-NOTICE']) {
  appendFileSync(outfile+'.LEGAL.txt', '\n'+file+'\n'+readFileSync(file,'utf8'));
}
const onboarding='../../apps/platform/static/workspace/onboarding.bundle.js';
await build({entryPoints:['onboarding.js'],bundle:true,format:'esm',minify:true,legalComments:'linked',outfile:onboarding});
for (const file of ['ESPTOOL-LICENSE','PAKO-LICENSE','ZLIB-NOTICE']) {
  appendFileSync(onboarding+'.LEGAL.txt', '\n'+file+'\n'+readFileSync(file,'utf8'));
}
appendFileSync(onboarding+'.LEGAL.txt','\nhash-wasm\n'+readFileSync('node_modules/hash-wasm/LICENSE','utf8'));
