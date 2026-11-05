// Pixel-space geometry only; no image data or inference leaves the browser.
function offsets(length,size){const count=Math.ceil((length-size)/(size*.65));return count>0?Array.from({length:count+1},(_,i)=>Math.round(i*(length-size)/count)):[0];}
export function faceScans(width,height){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<1||height<1)throw Error('Invalid image dimensions');
  const scans=[{x:0,y:0,width,height}],short=Math.min(width,height);
  if(short<256)return scans;
  for(const ratio of [.75,.4]){
    const size=Math.max(160,Math.round(short*ratio)),xs=offsets(width,size),ys=offsets(height,size);
    if(scans.length+xs.length*ys.length>40)continue;
    for(const y of ys)for(const x of xs)scans.push({x,y,width:size,height:size});
  }
  return scans;
}
export function projectFace(detection,scan,width,height){
  const b=detection.boundingBox,score=detection.categories?.[0]?.score??detection.score??0;
  if(!b||![b.originX,b.originY,b.width,b.height,score].every(Number.isFinite)||b.width<=0||b.height<=0)return null;
  const x=Math.max(0,scan.x+b.originX),y=Math.max(0,scan.y+b.originY);
  const right=Math.min(width,scan.x+b.originX+b.width),bottom=Math.min(height,scan.y+b.originY+b.height);
  if(right<=x||bottom<=y)return null;
  return {score,boundingBox:{originX:x,originY:y,width:right-x,height:bottom-y}};
}
export function refinementScans(faces,width,height,budget){
  if(!faces.length||budget<1)return [];
  const boxes=faces.map(face=>face.boundingBox),largest=Math.max(...boxes.map(b=>Math.max(b.width,b.height))),short=Math.min(width,height);
  if(short/largest<5)return [];
  const pad=largest*1.2,left=Math.max(0,Math.floor(Math.min(...boxes.map(b=>b.originX))-pad)),top=Math.max(0,Math.floor(Math.min(...boxes.map(b=>b.originY))-pad));
  const right=Math.min(width,Math.ceil(Math.max(...boxes.map(b=>b.originX+b.width))+pad)),bottom=Math.min(height,Math.ceil(Math.max(...boxes.map(b=>b.originY+b.height))+pad));
  let size=Math.min(short,Math.max(160,Math.round(largest*4)));
  while(size<=short){
    const xs=offsets(right-left,Math.min(size,right-left)),ys=offsets(bottom-top,Math.min(size,bottom-top));
    if(xs.length*ys.length<=budget)return ys.flatMap(y=>xs.map(x=>({x:left+x,y:top+y,width:Math.min(size,right-left),height:Math.min(size,bottom-top)})));
    size=Math.ceil(size*1.25);
  }
  return [];
}
// Retain the strongest localized box. Unioning noisy scales can swallow adjacent faces.
export function mergeFaces(detections,threshold=.5,tight=false){
  const kept=[];
  for(const face of detections.filter(Boolean).filter(d=>d.score>=threshold).sort((a,b)=>b.score-a.score)){
    const a=face.boundingBox;
    const duplicate=kept.find(other=>{
      const b=other.boundingBox,intersection=Math.max(0,Math.min(a.originX+a.width,b.originX+b.width)-Math.max(a.originX,b.originX))*Math.max(0,Math.min(a.originY+a.height,b.originY+b.height)-Math.max(a.originY,b.originY));
      const overlap=intersection/(a.width*a.height+b.width*b.height-intersection);
      const close=Math.abs(a.originX+a.width/2-b.originX-b.width/2)<Math.max(a.width,b.width)*.3&&Math.abs(a.originY+a.height/2-b.originY-b.height/2)<Math.max(a.height,b.height)*.3;
      return tight?overlap>.65:(overlap>.35||(close&&intersection/Math.min(a.width*a.height,b.width*b.height)>.8));
    });
    if(!duplicate)kept.push({...face,boundingBox:{...a}});
  }
  return kept.slice(0,100);
}

export function confirmationScan(face,width,height,scale=2){
  const b=face.boundingBox,size=Math.max(32,Math.max(b.width,b.height)*scale),cx=b.originX+b.width/2,cy=b.originY+b.height/2;
  const x=Math.max(0,Math.floor(cx-size/2)),y=Math.max(0,Math.floor(cy-size/2));
  return {x,y,width:Math.min(width,Math.ceil(cx+size/2))-x,height:Math.min(height,Math.ceil(cy+size/2))-y};
}

export function confirmFace(proposal,detections,scan,width,height){
  const a=proposal.boundingBox;
  return detections.map(d=>projectFace(d,scan,width,height)).filter(Boolean).filter(d=>{
    if(d.score<.8)return false;
    const b=d.boundingBox,intersection=Math.max(0,Math.min(a.originX+a.width,b.originX+b.width)-Math.max(a.originX,b.originX))*Math.max(0,Math.min(a.originY+a.height,b.originY+b.height)-Math.max(a.originY,b.originY));
    const overlap=intersection/(a.width*a.height+b.width*b.height-intersection);
    return overlap>=.2&&Math.abs(a.originX+a.width/2-b.originX-b.width/2)<=Math.max(a.width,b.width)*.5&&Math.abs(a.originY+a.height/2-b.originY-b.height/2)<=Math.max(a.height,b.height)*.5;
  }).sort((a,b)=>b.score-a.score)[0]||null;
}
