import {FilesetResolver,FaceDetector,ImageClassifier} from '../vendor/content/mediapipe/vision_bundle.mjs';
import {faceScans,projectFace,mergeFaces,refinementScans,confirmationScan,confirmFace} from './face-scans.mjs?v=face-confirm-5';
const vendor=new URL('../vendor/content/',import.meta.url);
export async function visionTask(kind,image,diagnostics=null){
  const files=await FilesetResolver.forVisionTasks(new URL('mediapipe/wasm',vendor).href);
  let task;
  try{
    if(kind==='faces'){
      task=await FaceDetector.createFromOptions(files,{baseOptions:{modelAssetPath:new URL('models/face-short-range.tflite',vendor).href,delegate:'CPU'},runningMode:'IMAGE',minDetectionConfidence:.5});
      const width=image.width,height=image.height,scans=faceScans(width,height),initialScans=scans.length,found=[];
      const tile=typeof OffscreenCanvas!=='undefined'?new OffscreenCanvas(1,1):document.createElement('canvas');
      try{
        for(let index=0;index<scans.length;index++){
          const scan=scans[index];let input=image;
          if(index){tile.width=scan.width;tile.height=scan.height;tile.getContext('2d').drawImage(image,scan.x,scan.y,scan.width,scan.height,0,0,scan.width,scan.height);input=tile;}
          const raw=task.detect(input).detections;
          diagnostics?.({scan,raw});
          for(const face of raw)found.push(projectFace(face,scan,width,height));
          if(index===initialScans-1)scans.push(...refinementScans(found.filter(Boolean),width,height,40-scans.length));
          if(index%4===3)await new Promise(resolve=>setTimeout(resolve,0));
        }
        const accepted=[],candidates=mergeFaces(found,.5,true);
        for(let index=0;index<candidates.length;index++){
          const proposal=candidates[index];
          for(const scale of [2,3]){
            const scan=confirmationScan(proposal,width,height,scale);
            tile.width=scan.width;tile.height=scan.height;
            tile.getContext('2d').drawImage(image,scan.x,scan.y,scan.width,scan.height,0,0,scan.width,scan.height);
            const raw=task.detect(tile).detections;
            diagnostics?.({scan,raw,stage:'confirmation'});
            const confirmed=confirmFace(proposal,raw,scan,width,height);
            if(confirmed){accepted.push(confirmed);break;}
          }
          if(index%4===3)await new Promise(resolve=>setTimeout(resolve,0));
        }
        return mergeFaces(accepted);
      }finally{tile.width=tile.height=1;}
    }
    task=await ImageClassifier.createFromOptions(files,{baseOptions:{modelAssetPath:new URL('models/efficientnet-lite0-int8.tflite',vendor).href,delegate:'CPU'},runningMode:'IMAGE',maxResults:-1,scoreThreshold:0});
    return task.classify(image).classifications[0]?.categories.map(c=>({index:c.index,categoryName:c.categoryName,score:c.score}))||[];
  }finally{task?.close();}
}
