import {WebVision} from './vision.mjs?v=face-confirm-5';
import {decode,render,encode,digest,canvas} from './pipeline.mjs';
const button=document.querySelector('#run-vision-check'),status=document.querySelector('#probe-status'),results=document.querySelector('#probe-results');
button.onclick=async()=>{
  button.disabled=true;results.replaceChildren();const record={environment:navigator.userAgent,recognition_design:'self-hosted browser models; no external recognition service',checks:[],started:new Date().toISOString()},engine=new WebVision();
  function check(name,ok,detail=null){const li=document.createElement('li');li.textContent=`${ok?'PASS':'FAIL'} · ${name}`;results.append(li);record.checks.push({name,pass:!!ok,detail});if(!ok)throw Error(name);}
  try{
    status.textContent='실제 얼굴 모델 준비 중';const original=await(await fetch(new URL('./fixtures/portrait.jpg',import.meta.url))).blob(),originalHash=await digest(original),source=await decode(original),before=source.getContext('2d').getImageData(0,0,source.width,source.height).data.slice();
    const faces=await engine.faces(source);check('실제 사진 얼굴 탐지',faces.length>0,{faces:faces.length});const edited=render(source,faces),after=edited.getContext('2d').getImageData(0,0,edited.width,edited.height).data;let changes=0;for(let i=0;i<before.length;i+=12)if(before[i]!==after[i])changes++;check('실제 모자이크 픽셀 변화',changes>100,{changes});
    const unchanged=source.getContext('2d').getImageData(0,0,source.width,source.height).data;check('원본 파일과 작업 픽셀 보존',originalHash===await digest(original)&&before.every((n,i)=>n===unchanged[i]));
    const encoded=await encode(edited);check('게시 사본 digest와 크기',encoded.sha===await digest(encoded.blob)&&encoded.blob.size<=5*1024*1024,{bytes:encoded.blob.size,sha256:encoded.sha});
    const photo=document.querySelector('#probe-photo');photo.width=encoded.bitmap.width;photo.height=encoded.bitmap.height;photo.getContext('2d').drawImage(encoded.bitmap,0,0);
    status.textContent='실제 사진 자동 분류 중';const dog=await decode(await(await fetch(new URL('./fixtures/dog.jpg',import.meta.url))).blob()),suggestion=await engine.classify(dog);check('실제 강아지 사진 자동 동물 테마',suggestion.theme==='animal',suggestion);check('자동 한국어 태그',suggestion.tags.includes('강아지'));
    status.textContent='실제 한영 OCR 준비 중';const text=canvas(1600,1000),ctx=text.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,text.width,text.height);ctx.fillStyle='#000';ctx.font='bold 120px sans-serif';ctx.fillText('바다라멘',120,250);ctx.fillText('CAFE MENU 100',120,500);const publicText=await encode(text),lines=await engine.ocr(publicText.blob,publicText.bitmap.width,publicText.bitmap.height,m=>{if(m.status==='recognizing text')status.textContent=`한영 OCR ${Math.round(m.progress*100)}%`;});const all=lines.map(l=>l.text.replace(/\s/g,'')).join(' ');check('실제 한글 OCR',all.includes('바다라멘'),lines);check('실제 영문 OCR',all.includes('CAFE'));check('실제 정규화 글자 좌표',lines.length>0&&lines.every(l=>l.quad.length===4&&l.quad.flat().every(n=>Number.isFinite(n)&&n>=0&&n<=1)));
    record.pass=true;status.textContent='PASS · 실제 인식·파일·픽셀 검사 완료';
  }catch(error){record.pass=false;record.error=String(error.message||error);status.textContent='FAIL · '+record.error;}finally{engine.close();record.finished=new Date().toISOString();document.querySelector('#probe-record').textContent=JSON.stringify(record,null,2);button.disabled=false;}
};
