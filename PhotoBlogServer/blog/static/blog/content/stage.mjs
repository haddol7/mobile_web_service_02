import {clamp} from './rules.mjs';
export class PhotoStage{
  constructor(element,{draft=null,onChange=()=>{},onSelect=()=>{},onZoom=()=>{}}={}){
    this.element=element;this.draft=draft;this.onChange=onChange;this.onSelect=onSelect;this.onZoom=onZoom;this.mode='pan';this.selected=-1;this.zoom=1;this.pan={x:0,y:0};this.pointers=new Map();this.highlights=[];
    element.addEventListener('pointerdown',e=>this.down(e));element.addEventListener('pointermove',e=>this.move(e));for(const type of ['pointerup','pointercancel','lostpointercapture'])element.addEventListener(type,e=>this.up(e));
    this.resize=new ResizeObserver(()=>this.draw());this.resize.observe(element);
  }
  image(value){this.source=value;this.zoom=1;this.pan={x:0,y:0};this.onZoom(this.zoom);this.draw();}
  reset(){this.zoom=1;this.pan={x:0,y:0};this.onZoom(this.zoom);this.draw();}
  setZoom(value){this.zoom=clamp(value,1,8);this.onZoom(this.zoom);this.draw();}
  point(e){const box=this.element.getBoundingClientRect();return {x:e.clientX-box.left,y:e.clientY-box.top};}
  imagePoint(point){return {x:clamp((point.x-this.tx)/(this.scale*this.source.width)),y:clamp((point.y-this.ty)/(this.scale*this.source.height))};}
  draw(){
    const box=this.element.getBoundingClientRect();if(!box.width||!box.height)return;const ratio=Math.min(window.devicePixelRatio||1,2);this.element.width=Math.round(box.width*ratio);this.element.height=Math.round(box.height*ratio);const ctx=this.element.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#e9eee7';ctx.fillRect(0,0,box.width,box.height);if(!this.source)return;
    this.scale=Math.min(box.width/this.source.width,box.height/this.source.height)*this.zoom;this.tx=(box.width-this.source.width*this.scale)/2+this.pan.x;this.ty=(box.height-this.source.height*this.scale)/2+this.pan.y;
    ctx.save();ctx.translate(this.tx,this.ty);ctx.scale(this.scale,this.scale);ctx.drawImage(this.source,0,0);
    const regions=this.draft?.regions||[];regions.forEach((r,i)=>{ctx.fillStyle=r.active?'#183c3030':'#ffffff70';ctx.strokeStyle=i===this.selected?'#d17118':r.active?'#1c7153':'#66736b';ctx.lineWidth=(i===this.selected?3:2)/this.scale;ctx.setLineDash(r.active?[]:[5/this.scale,4/this.scale]);const x=r.x*this.source.width,y=r.y*this.source.height,w=r.w*this.source.width,h=r.h*this.source.height;ctx.fillRect(x,y,w,h);ctx.strokeRect(x,y,w,h);if(i===this.selected){ctx.fillStyle='#d17118';const side=16/this.scale;ctx.fillRect(x+w-side/2,y+h-side/2,side,side);}});
    ctx.setLineDash([]);for(const q of this.highlights){ctx.strokeStyle='#d17118';ctx.fillStyle='#ffc76535';ctx.lineWidth=3/this.scale;ctx.beginPath();q.forEach(([x,y],i)=>i?ctx.lineTo(x*this.source.width,y*this.source.height):ctx.moveTo(x*this.source.width,y*this.source.height));ctx.closePath();ctx.fill();ctx.stroke();}ctx.restore();
  }
  focus(quad){const points=quad.map(([x,y])=>({x:x*this.source.width,y:y*this.source.height})),left=Math.min(...points.map(p=>p.x)),right=Math.max(...points.map(p=>p.x)),top=Math.min(...points.map(p=>p.y)),bottom=Math.max(...points.map(p=>p.y)),box=this.element.getBoundingClientRect(),fit=Math.min(box.width/this.source.width,box.height/this.source.height);this.zoom=clamp(Math.min(box.width/(right-left+40),box.height/(bottom-top+40))/fit,1,8);this.pan={x:(this.source.width/2-(left+right)/2)*fit*this.zoom,y:(this.source.height/2-(top+bottom)/2)*fit*this.zoom};this.highlights=[quad];this.draw();}
  down(e){if(!this.source||this.disabled)return;e.preventDefault();this.element.setPointerCapture(e.pointerId);const p=this.point(e);this.pointers.set(e.pointerId,p);
    if(this.pointers.size===2){const [a,b]=[...this.pointers.values()];this.pinch={distance:Math.hypot(a.x-b.x,a.y-b.y),zoom:this.zoom};this.gesture=null;return;}
    const q=this.imagePoint(p);this.gesture={point:p,q,pan:{...this.pan}};
    if(this.mode==='pan'||!this.draft)return;
    const selected=[...this.draft.regions].map((r,i)=>({r,i})).reverse().find(({r})=>q.x>=r.x&&q.x<=r.x+r.w&&q.y>=r.y&&q.y<=r.y+r.h);
    if(this.mode==='add'){this.gesture.add=true;return;}
    this.selected=selected?.i??-1;this.onSelect(this.selected);if(selected){this.draft.remember();this.gesture.region={...selected.r};this.gesture.resize=Math.abs(p.x-(this.tx+(selected.r.x+selected.r.w)*this.source.width*this.scale))<26&&Math.abs(p.y-(this.ty+(selected.r.y+selected.r.h)*this.source.height*this.scale))<26;}this.draw();
  }
  move(e){if(this.disabled||!this.pointers.has(e.pointerId)||!this.source)return;e.preventDefault();const p=this.point(e);this.pointers.set(e.pointerId,p);if(this.pointers.size===2&&this.pinch){const [a,b]=[...this.pointers.values()];this.zoom=clamp(this.pinch.zoom*Math.hypot(a.x-b.x,a.y-b.y)/Math.max(1,this.pinch.distance),1,8);this.onZoom(this.zoom);this.draw();return;}if(!this.gesture)return;const g=this.gesture,q=this.imagePoint(p);
    if(this.mode==='pan'||!this.draft){this.pan={x:g.pan.x+p.x-g.point.x,y:g.pan.y+p.y-g.point.y};this.draw();}
    else if(g.region){const r=g.region,patch=g.resize?{w:clamp(q.x-r.x,.008,1-r.x),h:clamp(q.y-r.y,.008,1-r.y)}:{x:clamp(r.x+q.x-g.q.x,0,1-r.w),y:clamp(r.y+q.y-g.q.y,0,1-r.h)};this.draft.update(this.selected,patch,false);this.onChange(false);this.draw();}
    else if(g.add){g.end=q;this.highlights=[[[Math.min(q.x,g.q.x),Math.min(q.y,g.q.y)],[Math.max(q.x,g.q.x),Math.min(q.y,g.q.y)],[Math.max(q.x,g.q.x),Math.max(q.y,g.q.y)],[Math.min(q.x,g.q.x),Math.max(q.y,g.q.y)]]];this.draw();}
  }
  up(e){if(!this.pointers.has(e.pointerId))return;this.pointers.delete(e.pointerId);const g=this.gesture;if(g?.add&&g.end){const q=g.end;this.draft.add(Math.min(q.x,g.q.x),Math.min(q.y,g.q.y),Math.abs(q.x-g.q.x),Math.abs(q.y-g.q.y));this.selected=this.draft.regions.length-1;this.highlights=[];this.onSelect(this.selected);this.onChange(true);}else if(g?.region)this.onChange(true);this.gesture=null;this.pinch=null;this.draw();}
  close(){this.resize.disconnect();}
}
