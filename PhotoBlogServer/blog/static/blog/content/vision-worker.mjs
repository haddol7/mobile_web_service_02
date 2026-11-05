import {visionTask} from './vision-engine.mjs?v=face-confirm-5';
self.onmessage=async event=>{const {kind,image}=event.data;try{const result=await visionTask(kind,image);self.postMessage({result});}catch(error){self.postMessage({error:String(error?.message||error)});}finally{image.close();}};
