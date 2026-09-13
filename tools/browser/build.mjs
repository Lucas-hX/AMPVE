import {build} from 'esbuild';
import {appendFileSync, readFileSync} from 'node:fs';
const outfile='../../apps/platform/static/workspace/inspect.bundle.js';
await build({entryPoints:['inspect.js'],bundle:true,format:'esm',minify:true,legalComments:'linked',outfile});
for (const file of ['ESPTOOL-LICENSE','PAKO-LICENSE','ZLIB-NOTICE']) {
  appendFileSync(outfile+'.LEGAL.txt', '\n'+file+'\n'+readFileSync(file,'utf8'));
}
