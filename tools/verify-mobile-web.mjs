import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const common=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const evidence=path.join(common,'evidence/mobile-web');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
async function snapshot(){
  const result={};
  for(const directory of ['web-tests','PhotoBlogServer/blog/static/blog/content','PhotoBlogServer/blog/static/blog/vendor/content']){
    async function walk(location){for(const entry of await fs.readdir(location,{withFileTypes:true})){
      const full=path.join(location,entry.name);if(entry.isDirectory())await walk(full);
      else result[path.relative(common,full).replaceAll('\\','/')]=hash(await fs.readFile(full));
    }}
    await walk(path.join(common,directory));
  }
  return result;
}
await fs.mkdir(evidence,{recursive:true});
const before=await snapshot(),started=new Date().toISOString();
const run=spawnSync(process.execPath,['--test','--test-reporter=tap',path.join(common,'web-tests/content-rules.test.mjs')],{encoding:'utf8'});
await fs.writeFile(path.join(evidence,'unit-tests.txt'),run.stdout+run.stderr);
const after=await snapshot(),stable=JSON.stringify(before)===JSON.stringify(after);
const tests=Number(run.stdout.match(/^# tests (\d+)$/m)?.[1]||0);
const record={environment:'Windows bundled Node',started_utc:started,finished_utc:new Date().toISOString(),
  command:[process.execPath,'--test','web-tests/content-rules.test.mjs'],exit_code:run.status,source_stable:stable,
  source_sha256:before,tests,pass:run.status===0&&stable&&tests>0};
await fs.writeFile(path.join(evidence,'unit-verification.json'),JSON.stringify(record,null,2)+'\n');
console.log(JSON.stringify({tests,pass:record.pass,stable}));
if(!record.pass){console.log(run.stdout+run.stderr);process.exitCode=1;}
