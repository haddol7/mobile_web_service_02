import {LABELS} from './labels.mjs';
import {ocrCandidates} from './ocr-policy.mjs?v=ocr-page-2';
export const THEMES={food:'음식',animal:'동물',nature:'자연·풍경',people:'인물',space:'건축·공간',object:'사물',other:'기타'};
export const MAPPING_VERSION='web_imagenet_v2';
export const clamp=(n,low=0,high=1)=>Math.min(high,Math.max(low,n));
export function normalize(s){return s.normalize('NFKC').toLowerCase().replace(/ß/g,'ss').replace(/ς/g,'σ').trim().replace(/\s+/gu,' ');}
export function cleanText(s,max=200){if(typeof s!=='string'||/\p{C}/u.test(s)||[...s.trim().replace(/\s+/gu,' ')].length>max)throw Error(`문구는 제어문자 없이 ${max}자 이하로 입력해주세요.`);return s.trim().replace(/\s+/gu,' ');}
export function parseTags(s){const tags=[],seen=new Set();for(const raw of s.split(',')){if(!raw.trim())continue;const value=cleanText(raw,30),key=normalize(value);if(!seen.has(key)){seen.add(key);tags.push(value);}}if(tags.length>10)throw Error('태그는 최대 10개입니다.');return tags;}
export function uuid(){const b=crypto.getRandomValues(new Uint8Array(16));b[6]=b[6]&15|64;b[8]=b[8]&63|128;const s=[...b].map(v=>v.toString(16).padStart(2,'0')).join('');return `${s.slice(0,8)}-${s.slice(8,12)}-${s.slice(12,16)}-${s.slice(16,20)}-${s.slice(20)}`;}
const spaces=new Set(['bakery','bookshop','boathouse','barn','castle','church','cinema','dome','greenhouse','library','monastery','mosque','palace','patio','prison','restaurant','stupa','yurt','lighthouse','steel arch bridge','suspension bridge']);
const objects=new Map([['book jacket','책'],['comic book','책'],['menu','메뉴판'],['street sign','간판'],['cellular telephone','휴대폰'],['desktop computer','컴퓨터'],['laptop','컴퓨터'],['notebook','컴퓨터'],['computer keyboard','키보드'],['analog clock','시계'],['digital clock','시계'],['bicycle-built-for-two','자전거'],['mountain bike','자전거'],['sofa','소파'],['studio couch','소파'],['dining table','식탁'],['desk','책상'],['coffee mug','컵'],['cup','컵'],['flowerpot','화분']]);
export function labelRule(category){
  const name=category.categoryName||LABELS[category.index];const index=LABELS.indexOf(name);
  if(index>=1&&index<=398)return {theme:'animal',tag:index>=152&&index<=269?'강아지':index>=282&&index<=286?'고양이':index>=8&&index<=25?'새':'동물'};
  if((index>=925&&index<=958)||(index>=960&&index<=968)||index===970)return {theme:'food',tag:({929:'아이스크림',934:'햄버거',935:'핫도그',960:'파스타',964:'피자',968:'커피'})[index]||'음식'};
  if((index>=971&&index<=981)||(index>=985&&index<=998))return {theme:'nature',tag:index===979?'해변':index===976?'호수':index>=985?'식물':'자연'};
  if(index>=982&&index<=984)return {theme:'people',tag:'인물'};
  if(spaces.has(name))return {theme:'space',tag:'건축·공간'};
  if(objects.has(name))return {theme:'object',tag:objects.get(name)};
  return null;
}
export function suggest(categories){
  // EfficientNet is a single softmax over mutually exclusive ImageNet classes.
  // Sum disjoint breed/class mass into its parent theme, unlike ML Kit's
  // independent labels on Android. Never sum repeated classes or rescale the
  // remaining supported classes to hide probability assigned to unknown ones.
  const scores=new Map(),tagScores=new Map(),seen=new Set();let topScore=0,totalMass=0;
  for(const label of categories){if(!Number.isFinite(label.score)||label.score<0||label.score>1)continue;const name=label.categoryName||LABELS[label.index];if(seen.has(name))continue;seen.add(name);totalMass+=label.score;topScore=Math.max(topScore,label.score);const rule=labelRule(label);if(!rule)continue;scores.set(rule.theme,(scores.get(rule.theme)||0)+label.score);tagScores.set(rule.tag,(tagScores.get(rule.tag)||0)+label.score);}
  const alternatives=[...scores].sort((a,b)=>b[1]-a[1]).map(([theme,score])=>({theme,score}));
  const valid=totalMass<=1.2&&topScore>=.1;
  return {theme:valid&&alternatives.length&&alternatives[0].score>=.65&&(!alternatives[1]||alternatives[0].score-alternatives[1].score>=.12)?alternatives[0].theme:null,tags:valid?[...tagScores].filter(([,score])=>score>=.5).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([tag])=>tag):[],alternatives:alternatives.slice(0,3),evidence:{topScore,totalMass}};
}
export class GenerationGate{value=0;advance(){return ++this.value;}accepts(ticket){return ticket===this.value;}}
export class MosaicDraft{
  regions=[];history=[];initial=[];
  snapshot(){return this.regions.map(r=>({...r}));}
  remember(){this.history.push(this.snapshot());if(this.history.length>40)this.history.shift();}
  checkpoint(){this.initial=this.snapshot();this.history=[];}
  replace(regions){if(regions.length>100)throw Error('가림 영역은 최대 100개입니다.');for(const r of regions)if(![r.x,r.y,r.w,r.h].every(Number.isFinite)||r.x<0||r.y<0||r.w<=0||r.h<=0||r.x+r.w>1.000001||r.y+r.h>1.000001||![1,2,3].includes(r.strength))throw Error('가림 영역의 위치와 크기를 확인해주세요.');this.regions=regions.map(r=>({...r}));}
  add(x,y,w,h){if(w<.004||h<.004)return;this.remember();this.replace([...this.regions,{id:uuid(),x,y,w,h,active:true,automatic:false,strength:2}]);}
  detected(found){this.remember();this.replace([...this.regions.filter(r=>!r.automatic),...found].slice(0,100));}
  update(index,patch,remember=true){if(!this.regions[index])return;if(remember)this.remember();this.replace(this.regions.map((r,i)=>i===index?{...r,...patch}:r));}
  remove(index){this.remember();this.regions=this.regions.filter((_,i)=>i!==index);}
  undo(){if(this.history.length)this.regions=this.history.pop();}
  reset(){this.remember();this.regions=this.initial.map(r=>({...r}));}
}
export function makePacket(state){
  const theme=state.theme||null,tags=parseTags(state.tags),lines=state.ocrStatus==='ready'?state.lines.filter(l=>l.included).map(l=>({line_id:l.line_id,text:cleanText(l.text),quad:l.quad,origin:l.origin})):[];
  if(lines.some(l=>!l.text))throw Error('빈 문구는 검색에서 제외해주세요.');
  if(lines.length>100||lines.reduce((n,l)=>n+[...l.text].length,0)>8192)throw Error('검색 문구는 최대 100줄·전체 8192자입니다. 포함할 문구를 줄여주세요.');
  const packet={schema_version:1,image_sha256:state.sha,width:state.width,height:state.height,model_versions:state.modelVersions||{},mapping_version:state.mappingVersion||MAPPING_VERSION,theme_status:theme?'classified':state.analyzed?'unclassified':'not_analyzed',theme,theme_origin:theme?(state.themeEdited?'user':'auto'):'unclassified',tags:tags.map(display=>({display,origin:state.tagsEdited?'user':'auto'})),ocr_status:state.ocrStatus,lines};
  if(state.postId)packet.expected_revision=state.revision;
  if(new TextEncoder().encode(JSON.stringify(packet)).length>64*1024)throw Error('분석 결과가 너무 큽니다. 검색 문구를 줄여주세요.');
  return packet;
}
export function ocrLines(blocks,width,height){
  return ocrCandidates(blocks,width,height).map(candidate=>({...candidate,line_id:uuid(),origin:'auto',included:false}));
}

