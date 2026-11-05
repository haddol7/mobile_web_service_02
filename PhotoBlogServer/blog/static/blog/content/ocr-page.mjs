// Estimate only text-line rotation on paper-like images. Coordinates are mapped
// back to the unchanged published image; this never rotates the saved photo.
export function pageRotation(pixels,width,height){
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<20||height<20||pixels.length!==width*height*4)return null;
  const points=[];let paper=0,total=0;
  const lum=(x,y)=>{const i=(y*width+x)*4;return (pixels[i]*3+pixels[i+1]*6+pixels[i+2])/10;};
  for(let y=4;y<height-4;y+=2)for(let x=4;x<width-4;x+=2){
    const i=(y*width+x)*4,r=pixels[i],g=pixels[i+1],b=pixels[i+2],light=(r*3+g*6+b)/10,chroma=Math.max(r,g,b)-Math.min(r,g,b);total++;
    if(light>140&&chroma<45)paper++;
    if(light<125&&chroma<60&&Math.max(lum(x-3,y),lum(x+3,y),lum(x,y-3),lum(x,y+3))>155)points.push([x-width/2,y-height/2]);
  }
  if(!total||paper/total<.35||points.length<100)return null;
  const score=angle=>{const a=angle*Math.PI/180,s=Math.sin(a),c=Math.cos(a),bins=new Map();for(const [x,y] of points){const bin=Math.round((s*x+c*y)/2);bins.set(bin,(bins.get(bin)||0)+1);}return [...bins.values()].reduce((n,v)=>n+v*v,0);};
  const initial=score(0);let best=initial,angle=0;
  for(let candidate=-20;candidate<=20;candidate++){const value=score(candidate);if(value>best){best=value;angle=candidate;}}
  return {angle:best>initial*1.15?angle:0,paperRatio:paper/total,gain:best/initial,points:points.length};
}

export function pageTransform(width,height,angle,scale){
  const radians=angle*Math.PI/180,c=Math.cos(radians),s=Math.sin(radians);
  const outputWidth=Math.ceil(scale*(Math.abs(width*c)+Math.abs(height*s))),outputHeight=Math.ceil(scale*(Math.abs(width*s)+Math.abs(height*c)));
  return {width:outputWidth,height:outputHeight,angle,scale,sourceWidth:width,sourceHeight:height};
}

export function originalQuad(bbox,transform){
  const {width,height,sourceWidth,sourceHeight,angle,scale}=transform,a=angle*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
  return [[bbox.x0,bbox.y0],[bbox.x1,bbox.y0],[bbox.x1,bbox.y1],[bbox.x0,bbox.y1]].map(([x,y])=>{
    const dx=(x-width/2)/scale,dy=(y-height/2)/scale;
    return [Math.max(0,Math.min(1,(c*dx+s*dy+sourceWidth/2)/sourceWidth)),Math.max(0,Math.min(1,(-s*dx+c*dy+sourceHeight/2)/sourceHeight))];
  });
}
