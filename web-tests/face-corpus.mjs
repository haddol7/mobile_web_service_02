import {WebVision, MODEL_VERSIONS} from '../PhotoBlogServer/blog/static/blog/content/vision.mjs?v=face-confirm-5';
import {decode, render, digest} from '../PhotoBlogServer/blog/static/blog/content/pipeline.mjs';

const root = new URL('../evidence/mobile-web/public-face-corpus/', import.meta.url);
const button = document.querySelector('#run'), status = document.querySelector('#status');
function overlap(a,b) {
  const intersection=Math.max(0,Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x))*Math.max(0,Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y));
  return {iou:intersection/(a.w*a.h+b.w*b.h-intersection),coverage:intersection/(a.w*a.h)};
}
function compare(truth, predicted) {
  if(truth===null)return null;
  const edges=truth.map(t=>predicted.map((p,index)=>({index,...overlap(t,p)})).filter(p=>p.iou>=.3).sort((a,b)=>b.iou-a.iou));
  const owner=new Map();
  function assign(index,seen) {
    for(const candidate of edges[index]) {
      if(seen.has(candidate.index))continue; seen.add(candidate.index);
      if(!owner.has(candidate.index)||assign(owner.get(candidate.index),seen)){owner.set(candidate.index,index);return true;}
    }
    return false;
  }
  truth.forEach((_,i)=>assign(i,new Set()));
  const matched=new Set(owner.values());
  return {true_positive:owner.size,false_negative:truth.length-owner.size,false_positive:predicted.length-owner.size,
    missed_indices:truth.map((_,i)=>i).filter(i=>!matched.has(i)),
    covered_at_least_80_percent:truth.map(t=>predicted.some(p=>overlap(t,p).coverage>=.8)),
    matching:'one-to-one maximum matching, IoU >= 0.3; padded mosaic boxes, not raw detector boxes'};
}
button.onclick=async()=>{
  button.disabled=true;
  const results=[],started=new Date().toISOString();
  document.querySelector('#cards').replaceChildren();
  try {
    const corpus=await(await fetch(new URL('cases.json',root))).json();
    for(const item of corpus.cases) {
      status.textContent=`검사 중 ${results.length+1}/${corpus.cases.length} · ${item.filename}`;
      const engine=new WebVision(),t=performance.now(); let result;
      try {
        const response=await fetch(new URL(item.filename,root));if(!response.ok)throw Error(`HTTP ${response.status}`);
        const blob=await response.blob();if(await digest(blob)!==item.sha256)throw Error('fixture SHA256 mismatch');
        const source=await decode(blob),ctx=source.getContext('2d'),original=ctx.getImageData(0,0,source.width,source.height).data;
        const regions=await engine.faces(source),masked=render(source,regions),pixels=masked.getContext('2d').getImageData(0,0,source.width,source.height).data;
        const pixelBoxes=regions.map(r=>({x:r.x*source.width,y:r.y*source.height,w:r.w*source.width,h:r.h*source.height}));
        // Decode may resize large photos. Scale original annotation coordinates to the actual decoded dimensions.
        const truth=item.ground_truth?.map(b=>({x:b.x*source.width/item.width,y:b.y*source.height/item.height,w:b.w*source.width/item.width,h:b.h*source.height/item.height}))??null;
        const changed=pixelBoxes.map(b=>{
          for(let y=Math.max(0,Math.floor(b.y));y<Math.min(source.height,b.y+b.h);y+=3)
            for(let x=Math.max(0,Math.floor(b.x));x<Math.min(source.width,b.x+b.w);x+=3){const p=(y*source.width+x)*4;if(original[p]!==pixels[p]||original[p+1]!==pixels[p+1]||original[p+2]!==pixels[p+2])return true;}
          return false;
        });
        const after=ctx.getImageData(0,0,source.width,source.height).data;
        result={id:item.id,filename:item.filename,faces:regions.length,expected_faces:item.expected_faces,
          width:source.width,height:source.height,regions,comparison:compare(truth,pixelBoxes),
          masked_regions_changed:changed,source_pixels_unchanged:original.every((v,i)=>v===after[i]),
          elapsed_ms:Math.round(performance.now()-t),sha256:item.sha256,uploaded:false};
        const article=document.createElement('article'),title=document.createElement('h2');
        title.textContent=`${item.filename} · 탐지 ${regions.length} / 주석·육안 개수 ${item.expected_faces??'미정'}`;
        const detail=document.createElement('pre');detail.textContent=JSON.stringify(result.comparison??{count_only:true,needs_visual_review:true},null,2);
        const canvas=document.createElement('canvas');canvas.width=source.width;canvas.height=source.height;
        const paint=canvas.getContext('2d');paint.drawImage(masked,0,0);paint.strokeStyle='#f00';paint.lineWidth=2;
        truth?.forEach(b=>paint.strokeRect(b.x,b.y,b.w,b.h));
        article.append(title,detail,canvas);document.querySelector('#cards').append(article);
      }catch(error){result={id:item.id,filename:item.filename,error:error.message};}
      finally{engine.close();}
      results.push(result);
      document.querySelector('#record').textContent=JSON.stringify({status:'running',started,model:MODEL_VERSIONS.face,environment:navigator.userAgent,results},null,2);
    }
    const total=results.filter(r=>r.comparison).reduce((a,r)=>({tp:a.tp+r.comparison.true_positive,fn:a.fn+r.comparison.false_negative,fp:a.fp+r.comparison.false_positive}),{tp:0,fn:0,fp:0});
    const record={status:'executed',started,finished:new Date().toISOString(),model:MODEL_VERSIONS.face,environment:navigator.userAgent,
      photos:results.length,errors:results.filter(r=>r.error).length,annotated_totals:total,
      note:'Local browser sample evaluation, not physical iPhone or production composer verification. All cases retained including failures.',results};
    document.querySelector('#record').textContent=JSON.stringify(record,null,2);status.textContent=`검사 완료 · ${results.length}장 · 오류 ${record.errors}건`;
  }catch(error){status.textContent=`검사 중단 · ${error.message}`;}
  finally{button.disabled=false;}
};
