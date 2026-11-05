import {clamp} from './rules.mjs';

// Safari's visible area changes when its browser bars or keyboard move.
export function editorViewport(viewport,fallbackHeight){
  const use=viewport&&Math.abs((viewport.scale??1)-1)<.01&&Number.isFinite(viewport.height)&&viewport.height>0;
  const fallback=Number.isFinite(fallbackHeight)&&fallbackHeight>0?fallbackHeight:1;
  return {height:Math.max(1,Math.floor(use?viewport.height:fallback)),top:use&&Number.isFinite(viewport.offsetTop)?Math.max(0,viewport.offsetTop):0};
}

export function coordinatePatch(region,key,text){
  if(!region||!['x','y','w','h'].includes(key)||String(text).trim()==='')return null;
  const value=Number(text)/100;if(!Number.isFinite(value))return null;
  return {[key]:key==='x'?clamp(value,0,1-region.w):key==='y'?clamp(value,0,1-region.h):clamp(value,.008,1-region[key==='w'?'x':'y'])};
}
