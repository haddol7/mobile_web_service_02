// Photo OCR is allowed to abstain: sparse-text recognition also sees texture as
// glyphs. Confidence is a heuristic score, never a probability of correctness.
const textOf=value=>(typeof value==='string'?value:'').replace(/\p{C}/gu,' ').trim().replace(/\s+/gu,' ');
const key=value=>textOf(value).normalize('NFKC').toLocaleLowerCase('en').replace(/[^\p{L}\p{N}]/gu,'');
const linesOf=blocks=>(blocks||[]).flatMap(b=>(b.paragraphs||[]).flatMap(p=>p.lines||[]));
const finiteScore=n=>Number.isFinite(n)&&n>=0&&n<=100;
function evidence(line){
  const text=textOf(line.text),letters=[...key(text)].length,length=[...text.replace(/\s/gu,'')].length;
  if(!letters||letters/length<.6||[...text].length>200||/[\u1100-\u11ff\u3130-\u318f]/u.test(text)||!finiteScore(line.confidence))return null;
  const threshold=letters===1?95:letters===2?85:70;
  if(line.confidence<threshold)return null;
  const words=(line.words||[]).filter(w=>key(w.text));
  if(words.length){
    let total=0,reliable=0;
    for(const word of words){if(!finiteScore(word.confidence))return null;const size=[...key(word.text)].length;total+=size;if(word.confidence>=60)reliable+=size;}
    if(reliable/total<.8)return null;
  }
  return {text,confidence:line.confidence};
}
export function ocrCandidates(blocks,width,height){
  if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)return [];
  const result=[];
  for(const line of linesOf(blocks)){
    const value=evidence(line),b=line.bbox;if(!value||!b||![b.x0,b.y0,b.x1,b.y1].every(Number.isFinite))continue;
    const x=Math.max(0,b.x0),y=Math.max(0,b.y0),right=Math.min(width,b.x1),bottom=Math.min(height,b.y1);
    if(right-x<2||bottom-y<4)continue;
    result.push({...value,bbox:{x0:x,y0:y,x1:right,y1:bottom},quad:[[x/width,y/height],[right/width,y/height],[right/width,bottom/height],[x/width,bottom/height]],order:result.length});
  }
  // Bound the number of expensive confirmations; choose the strongest evidence
  // first, then restore reading order. Never auto-select the first 100 guesses.
  return result.sort((a,b)=>b.confidence-a.confidence).slice(0,100).sort((a,b)=>a.order-b.order);
}
export function ocrRectangle(candidate,width,height){
  const b=candidate.bbox,pad=Math.max(4,Math.round((b.y1-b.y0)*.15)),left=Math.max(0,Math.floor(b.x0-pad)),top=Math.max(0,Math.floor(b.y0-pad));
  return {left,top,width:Math.min(width,Math.ceil(b.x1+pad))-left,height:Math.min(height,Math.ceil(b.y1+pad))-top};
}
function distance(a,b){
  const left=[...a],right=[...b];let row=Array.from({length:right.length+1},(_,i)=>i);
  for(let i=0;i<left.length;i++){const next=[i+1];for(let j=0;j<right.length;j++)next.push(Math.min(next[j]+1,row[j+1]+1,row[j]+(left[i]===right[j]?0:1)));row=next;}
  return row[right.length];
}
export function confirmOcrLine(candidate,blocks){
  const values=linesOf(blocks);if(values.length!==1)return null;
  const value=evidence(values[0]);if(!value)return null;
  const before=key(candidate.text),after=key(value.text),length=Math.max([...before].length,[...after].length);
  // Short signs must match exactly. Longer sentences tolerate at most 10%
  // character disagreement, without changing their first-pass display text.
  if(!before||!after||distance(before,after)>(length<10?0:Math.floor(length*.1)))return null;
  const confidence=Math.min(candidate.confidence,value.confidence);
  return {confidence,included:confidence>=85};
}

function documentEvidence(line){
  const text=textOf(line.text),letters=[...key(text)].length;
  if(letters<10||text.length>200||/[\u1100-\u11ff\u3130-\u318f]/u.test(text)||!finiteScore(line.confidence)||line.confidence<55||letters/[...text.replace(/\s/gu,'')].length<.75)return null;
  const words=(line.words||[]).filter(w=>[...key(w.text)].length>=2);
  if(words.length<2)return null;
  let total=0,reliable=0;
  for(const word of words){const size=[...key(word.text)].length;total+=size;if(finiteScore(word.confidence)&&word.confidence>=45)reliable+=size;}
  return total&&reliable/total>=.6?{text,confidence:line.confidence}:null;
}
export function documentCandidates(blocks,width,height){
  const result=[];
  for(const line of linesOf(blocks)){
    const value=documentEvidence(line),b=line.bbox;
    if(!value||!b||![b.x0,b.y0,b.x1,b.y1].every(Number.isFinite)||b.x0<0||b.y0<0||b.x1>width||b.y1>height||b.x1<=b.x0||b.y1<=b.y0)continue;
    result.push({...value,bbox:b,order:result.length});
  }
  return result.sort((a,b)=>b.confidence-a.confidence).slice(0,40).sort((a,b)=>a.order-b.order);
}
export function confirmDocumentLine(candidate,blocks){
  const lines=linesOf(blocks);if(lines.length!==1)return null;
  const value=documentEvidence(lines[0]);if(!value)return null;
  const before=key(candidate.text),after=key(value.text),length=Math.max([...before].length,[...after].length);
  if(distance(before,after)>Math.floor(length*.22))return null;
  // Handwriting remains review-only even when two recognition passes agree.
  return {text:value.confidence>candidate.confidence?value.text:candidate.text,included:false};
}
