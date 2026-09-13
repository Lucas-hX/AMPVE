import {readFile} from 'node:fs/promises';
// Narrow, checked build-time fixes for the pinned 2.8.0 SDK. Keep upstream source
// and license intact; fail if an upgrade changes these exact integration points.
export const improvFixes={name:'ampve-improv-lifecycle',setup(build){
 build.onLoad({filter:/improv-wifi-serial-sdk\/dist\/serial\.js$/},async args=>{
  let source=await readFile(args.path,'utf8');
  const replace=(before,after)=>{if(source.split(before).length!==2)throw new Error('Improv SDK contract changed');source=source.replace(before,after);};
  replace('await this.requestCurrentState();\n                resolve(undefined);','this.requestCurrentState().then(resolve, reject);');
  replace('await new Promise(async (resolve, reject) => {','await new Promise((resolve, reject) => {');
  // Serial write rejection must settle the RPC instead of becoming an unhandled promise.
  replace('            ...data,\n        ]);\n    }\n    /**\n     * Run an RPC', '            ...data,\n        ]).catch(() => this._setError(255));\n    }\n    /**\n     * Run an RPC');
  replace('        await writer.write(payload);\n        try {\n            writer.releaseLock();\n        }\n        catch (err) {\n            console.error("Ignoring release lock error", err);\n        }',
    '        try { await writer.write(payload); } finally { writer.releaseLock(); }');
  // Reject an in-flight RPC on disconnect so initialization cannot queue work on a closed port.
  replace('        this.dispatchEvent(new Event("disconnect"));','        this._setError(255);\n        this.dispatchEvent(new Event("disconnect"));');
  return {contents:source,loader:'js'};
 });
}};
