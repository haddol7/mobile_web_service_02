import {clamp} from './rules.mjs';
export function canvas(width,height){const c=document.createElement('canvas');c.width=width;c.height=height;return c;}
export async function decode(blob,max=2048){
  if(blob.size>40*1024*1024)throw Error('선택한 사진이 너무 큽니다. 40MB 이하 사진을 선택해주세요.');
  const url=URL.createObjectURL(blob),image=new Image();
  try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('이 브라우저가 읽을 수 없는 사진입니다. JPEG·PNG·WebP 사진을 선택해주세요.'));image.src=url;});
    const ratio=Math.min(1,max/Math.max(image.naturalWidth,image.naturalHeight));if(!image.naturalWidth||image.naturalWidth*image.naturalHeight>100_000_000)throw Error('사진 크기를 줄여서 다시 선택해주세요.');
    const output=canvas(Math.max(1,Math.round(image.naturalWidth*ratio)),Math.max(1,Math.round(image.naturalHeight*ratio))),ctx=output.getContext('2d');output.originalWidth=image.naturalWidth;output.originalHeight=image.naturalHeight;ctx.fillStyle='#fff';ctx.fillRect(0,0,output.width,output.height);ctx.drawImage(image,0,0,output.width,output.height);return output;
  }finally{URL.revokeObjectURL(url);image.src='';}
}
export function render(source,regions,reusable=null){
  const output=reusable||canvas(source.width,source.height);if(output.width!==source.width||output.height!==source.height){output.width=source.width;output.height=source.height;}const ctx=output.getContext('2d');ctx.drawImage(source,0,0);
  for(const region of regions){if(!region.active)continue;const x=Math.floor(region.x*source.width),y=Math.floor(region.y*source.height),w=Math.max(1,Math.ceil(region.w*source.width)),h=Math.max(1,Math.ceil(region.h*source.height));
    const block=Math.max(8,Math.round(Math.min(w,h)/({1:16,2:10,3:6}[region.strength]))),small=canvas(Math.max(1,Math.ceil(w/block)),Math.max(1,Math.ceil(h/block))),sample=small.getContext('2d');sample.drawImage(output,x,y,w,h,0,0,small.width,small.height);ctx.imageSmoothingEnabled=false;ctx.drawImage(small,0,0,small.width,small.height,x,y,w,h);ctx.imageSmoothingEnabled=true;small.width=small.height=1;
  }return output;
}
export async function digest(blob){if(!crypto.subtle)throw Error('안전한 HTTPS 주소에서 사진 처리를 사용해주세요.');return [...new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()))].map(n=>n.toString(16).padStart(2,'0')).join('');}
export async function encode(source){
  let current=source;
  for(let attempt=0;attempt<4;attempt++){
    for(const quality of [.9,.8,.7]){const blob=await new Promise(resolve=>current.toBlob(resolve,'image/jpeg',quality));if(blob&&blob.size<=5*1024*1024)return {blob,bitmap:await decode(blob,8192),sha:await digest(blob)};}
    const smaller=canvas(Math.max(1,Math.round(current.width*.8)),Math.max(1,Math.round(current.height*.8)));smaller.getContext('2d').drawImage(current,0,0,smaller.width,smaller.height);current=smaller;
  }throw Error('사진을 5MiB 이하로 만들지 못했습니다. 더 작은 사진을 선택해주세요.');
}
export function faceRegions(detections,width,height){return detections.map(d=>{const b=d.boundingBox,x=clamp((b.originX-b.width*.15)/width),y=clamp((b.originY-b.height*.15)/height),right=clamp((b.originX+b.width*1.15)/width),bottom=clamp((b.originY+b.height*1.15)/height);return {id:crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`,x,y,w:right-x,h:bottom-y,active:true,automatic:true,strength:2};}).filter(r=>r.w>0&&r.h>0).slice(0,100);}
