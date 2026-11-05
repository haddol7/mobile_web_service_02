import {ocrLines,suggest,uuid} from './rules.mjs?v=ocr-page-2';
import {ocrRectangle,confirmOcrLine,documentCandidates,confirmDocumentLine} from './ocr-policy.mjs?v=ocr-page-2';
import {pageRotation,pageTransform,originalQuad} from './ocr-page.mjs?v=ocr-page-2';
import {faceRegions} from './pipeline.mjs';
const vendor=new URL('../vendor/content/',import.meta.url);
export const MODEL_VERSIONS={face:'mp_blazeface_sr1_confirm_v5',label:'efficientnet_lite0_int8_1',ocr_ko:'tesseract7_fast_8741641_page2',ocr_latin:'tesseract7_fast_8741641_page2'};
let scriptPromise;
async function tesseract(){
  if(!scriptPromise)scriptPromise=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=new URL('tesseract/tesseract.min.js',vendor).href;script.onload=()=>resolve(window.Tesseract);script.onerror=()=>{scriptPromise=null;reject(Error('글자 인식 도구를 준비하지 못했어요. 연결을 확인하고 다시 시도해주세요.'));};document.head.append(script);});
  return scriptPromise;
}
export class WebVision{
  workers=new Set();closed=false;
  async task(kind,source){
    if(this.closed)throw Error('사진 분석이 종료되었습니다.');
    if(typeof Worker!=='undefined'&&typeof OffscreenCanvas!=='undefined'&&typeof createImageBitmap!=='undefined'){
      const worker=new Worker(new URL('./vision-worker.mjs?v=face-confirm-5',import.meta.url),{type:'module'});this.workers.add(worker);
      try{return await new Promise(async(resolve,reject)=>{
        const timer=setTimeout(()=>reject(Error('사진 인식 준비 시간이 초과되었어요.')),45000);
        worker.onmessage=event=>{clearTimeout(timer);event.data.error?reject(Error(event.data.error)):resolve(event.data.result);};worker.onerror=()=>{clearTimeout(timer);reject(Error('이 브라우저의 별도 인식 작업을 시작하지 못했어요.'));};
        try{const image=await createImageBitmap(source);worker.postMessage({kind,image},[image]);}catch(error){clearTimeout(timer);reject(error);}
      });}catch(error){if(this.closed)throw error;/* Safari versions without worker WebGL use the same local model on the main thread. */}
      finally{worker.terminate();this.workers.delete(worker);}
    }
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    const {visionTask}=await import('./vision-engine.mjs?v=face-confirm-5');return visionTask(kind,source);
  }
  async faces(source){return faceRegions(await this.task('faces',source),source.width,source.height);}
  async classify(source){return suggest(await this.task('classify',source));}
  async ocr(blob,width,height,onProgress=()=>{}){
    const engine=await tesseract();let worker;const token={terminate:()=>worker?.terminate()};this.workers.add(token);
    try{
      worker=await engine.createWorker(['kor','eng'],1,{workerPath:new URL('tesseract/worker.min.js',vendor).href,corePath:new URL('tesseract',vendor).href,langPath:new URL('tessdata',vendor).href,workerBlobURL:false,cacheMethod:'none',gzip:true,logger:m=>onProgress(m)});
      if(this.closed)throw Error('사진 분석이 종료되었습니다.');
      await worker.setParameters({tessedit_pageseg_mode:'11',preserve_interword_spaces:'1',user_defined_dpi:'150'});
      const bytes=new Uint8Array(await blob.arrayBuffer()),{data}=await worker.recognize(bytes,{},{blocks:true,text:true});
      const candidates=ocrLines(data.blocks,width,height),result=[];
      if(candidates.length)await worker.setParameters({tessedit_pageseg_mode:'7'});
      for(const [index,candidate] of candidates.entries()){
        if(this.closed)throw Error('사진 분석이 종료되었습니다.');
        onProgress({status:'confirming text',progress:index/candidates.length});
        const {data:confirmation}=await worker.recognize(bytes,{rectangle:ocrRectangle(candidate,width,height)},{blocks:true,text:true});
        const match=confirmOcrLine(candidate,confirmation.blocks);
        if(match)result.push({line_id:candidate.line_id,text:candidate.text,quad:candidate.quad,origin:'auto',included:match.included});
      }
      try{
        const page=await this.documentFallback(worker,blob,width,height,data,result.length,onProgress);
        const characters=lines=>lines.reduce((n,line)=>n+line.text.replace(/\s/gu,'').length,0);
        return page.length>=3&&characters(page)>Math.max(40,characters(result)*1.15)?page:result;
      }catch(error){if(this.closed)throw error;return result;}
    }finally{await worker?.terminate();this.workers.delete(token);}
  }
  async documentFallback(worker,blob,width,height,data,found,onProgress){
    const rawText=data.text||'',letters=rawText.replace(/[^\p{L}]/gu,'');if(letters.length<40)return [];
    const source=await createImageBitmap(blob),sample=document.createElement('canvas');
    try{
      const ratio=Math.min(1,600/Math.max(width,height));sample.width=Math.round(width*ratio);sample.height=Math.round(height*ratio);
      const preview=sample.getContext('2d',{willReadFrequently:true});preview.drawImage(source,0,0,sample.width,sample.height);
      const estimate=pageRotation(preview.getImageData(0,0,sample.width,sample.height).data,sample.width,sample.height);
      if(!estimate||(!estimate.angle&&found>=3))return [];
      onProgress({status:'reading document',progress:0});
      const scale=Math.min(3,2400/Math.max(width,height)),transform=pageTransform(width,height,estimate.angle,scale),page=document.createElement('canvas');
      page.width=transform.width;page.height=transform.height;const context=page.getContext('2d');context.fillStyle='#fff';context.fillRect(0,0,page.width,page.height);context.translate(page.width/2,page.height/2);context.rotate(estimate.angle*Math.PI/180);context.scale(scale,scale);context.drawImage(source,-width/2,-height/2);
      // Sparse-text mode breaks tilted paragraphs into fragments. Re-read paper
      // with page layout, using English only when Korean evidence is absent.
      if((letters.match(/[가-힣]/gu)||[]).length/letters.length<.15)await worker.reinitialize('eng');
      await worker.setParameters({tessedit_pageseg_mode:'3',preserve_interword_spaces:'1',user_defined_dpi:'300'});
      const {data:read}=await worker.recognize(page,{},{blocks:true,text:true}),candidates=documentCandidates(read.blocks,page.width,page.height),result=[];
      if(candidates.length<3)return [];
      await worker.setParameters({tessedit_pageseg_mode:'7'});
      for(const [index,candidate] of candidates.entries()){
        if(this.closed)throw Error('사진 분석이 종료되었습니다.');onProgress({status:'confirming document',progress:index/candidates.length});
        const {data:confirmation}=await worker.recognize(page,{rectangle:ocrRectangle(candidate,page.width,page.height)},{blocks:true,text:true});
        const match=confirmDocumentLine(candidate,confirmation.blocks);if(!match)continue;
        const quad=originalQuad(candidate.bbox,transform),valid=quad.every((a,i)=>{const b=quad[(i+1)%4],c=quad[(i+2)%4];return (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])>1e-12;});
        if(valid)result.push({line_id:uuid(),text:match.text,quad,origin:'auto',included:false});
      }
      return result;
    }finally{source.close();sample.width=sample.height=1;}
  }
  close(){this.closed=true;for(const worker of this.workers)worker.terminate();this.workers.clear();}
}
