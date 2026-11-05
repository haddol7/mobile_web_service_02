import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {MosaicDraft,GenerationGate,normalize,parseTags,suggest,makePacket,ocrLines,uuid} from '../PhotoBlogServer/blog/static/blog/content/rules.mjs';
import {faceRegions} from '../PhotoBlogServer/blog/static/blog/content/pipeline.mjs';
import {faceScans,projectFace,mergeFaces,refinementScans,confirmationScan,confirmFace} from '../PhotoBlogServer/blog/static/blog/content/face-scans.mjs';
import {editorViewport,coordinatePatch} from '../PhotoBlogServer/blog/static/blog/content/editor-controls.mjs';
import {addTags,toggleTag,tagChoices,withOcrInclusion} from '../PhotoBlogServer/blog/static/blog/content/review-controls.mjs';
import {ocrCandidates,ocrRectangle,confirmOcrLine} from '../PhotoBlogServer/blog/static/blog/content/ocr-policy.mjs';
import {documentCandidates,confirmDocumentLine} from '../PhotoBlogServer/blog/static/blog/content/ocr-policy.mjs';
import {pageRotation,pageTransform,originalQuad} from '../PhotoBlogServer/blog/static/blog/content/ocr-page.mjs';
const state=()=>({sha:'a'.repeat(64),width:1600,height:1000,tags:'',theme:null,analyzed:false,ocrStatus:'not_analyzed',lines:[]});
const ocrBlocks=lines=>[{paragraphs:[{lines:lines.map(line=>({bbox:{x0:10,y0:20,x1:90,y1:40},confidence:95,...line}))}]}];

test('paper rotation abstains on blank and colored texture images',()=>{
  const white=new Uint8ClampedArray(100*100*4).fill(255);assert.equal(pageRotation(white,100,100),null);
  for(let i=0;i<white.length;i+=4){white[i]=30;white[i+1]=170;white[i+2]=30;}
  assert.equal(pageRotation(white,100,100),null);assert.equal(pageRotation(white,NaN,100),null);
});
test('text-line projection estimates slope without knowing the written words',()=>{
  const width=260,height=220,pixels=new Uint8ClampedArray(width*height*4).fill(255);
  for(const row of [70,110,150,190])for(let x=30;x<230;x+=8)for(let dx=0;dx<3;dx++)for(let dy=0;dy<7;dy++){
    const y=Math.round(row-.18*(x-30))+dy,i=(y*width+x+dx)*4;pixels[i]=pixels[i+1]=pixels[i+2]=20;
  }
  const result=pageRotation(pixels,width,height);assert.ok(result&&result.angle>=9&&result.angle<=12);
});
test('document rectangles map to unchanged original photo coordinates',()=>{
  const transform=pageTransform(100,200,0,2);
  assert.deepEqual(originalQuad({x0:20,y0:40,x1:100,y1:80},transform),[[.1,.1],[.5,.1],[.5,.2],[.1,.2]]);
  const rotated=pageTransform(100,200,14,2),quad=originalQuad({x0:rotated.width/2-20,y0:rotated.height/2-10,x1:rotated.width/2+20,y1:rotated.height/2+10},rotated);
  assert.ok(Math.abs(quad.reduce((n,p)=>n+p[0],0)/4-.5)<1e-10);assert.ok(Math.abs(quad.reduce((n,p)=>n+p[1],0)/4-.5)<1e-10);
});
test('document fallback keeps supported long handwriting for review rather than auto search',()=>{
  const line={text:'We started with a fresh cup of coffee',confidence:64,words:[{text:'We',confidence:70},{text:'started',confidence:62},{text:'coffee',confidence:75}]};
  assert.equal(ocrCandidates(ocrBlocks([line]),100,100).length,0);
  const candidate=documentCandidates(ocrBlocks([line]),100,100)[0];assert.ok(candidate);
  const match=confirmDocumentLine(candidate,ocrBlocks([{...line,text:'We started with a fresh cup of coffee.',confidence:70}]));assert.ok(match);assert.equal(match.included,false);
  assert.equal(makePacket({...state(),ocrStatus:'ready',lines:[{...candidate,...match,line_id:uuid(),quad:[[0,0],[1,0],[1,1],[0,1]],origin:'auto'}]}).lines.length,0);
});
test('document fallback rejects fragments and disagreement despite paper detection',()=>{
  assert.equal(documentCandidates(ocrBlocks([{text:'ys bod a',confidence:99,words:[]}]),100,100).length,0);
  const line={text:'We started with a fresh cup of coffee',confidence:70,words:[{text:'started',confidence:80},{text:'coffee',confidence:80}]};
  const candidate=documentCandidates(ocrBlocks([line]),100,100)[0];
  assert.equal(confirmDocumentLine(candidate,ocrBlocks([{...line,text:'A completely different set of words'}])),null);
  assert.equal(confirmDocumentLine(candidate,ocrBlocks([line,line])),null);
});

test('OCR rejects texture fragments, symbol-only guesses and nonfinite scores',()=>{
  const blocks=ocrBlocks([{text:'ys',confidence:44},{text:'bod',confidence:49},{text:'a',confidence:55},{text:'—',confidence:98},{text:'4',confidence:84},{text:'가',confidence:NaN},{text:'OPEN',confidence:Infinity}]);
  assert.deepEqual(ocrCandidates(blocks,100,100),[]);
  assert.deepEqual(ocrCandidates(ocrBlocks([{text:'OPEN'}]),0,100),[]);
});
test('OCR does not trust a good line average that hides mostly weak words',()=>{
  assert.deepEqual(ocrCandidates(ocrBlocks([{text:'CAFE garbage',confidence:90,words:[{text:'CAFE',confidence:95},{text:'garbage',confidence:20}]}]),100,100),[]);
});
test('unconfirmed OCR candidates cannot enter search automatically',()=>{
  const lines=ocrLines(ocrBlocks([{text:'입구'},{text:'24'},{text:'OPEN'},{text:'A',confidence:98}]),100,100);
  assert.equal(lines.length,4);assert.ok(lines.every(l=>!l.included));
  assert.deepEqual(makePacket({...state(),ocrStatus:'ready',lines}).lines,[]);
});
test('short Korean signs, Latin signs and numbers survive matching second recognition',()=>{
  for(const text of ['입구','OPEN','24','A']){
    const candidate=ocrCandidates(ocrBlocks([{text}]),100,100)[0];
    assert.deepEqual(confirmOcrLine(candidate,ocrBlocks([{text,confidence:96}])),{confidence:95,included:true});
  }
});
test('OCR confirmation ignores formatting but rejects unstable and merged text',()=>{
  const candidate=ocrCandidates(ocrBlocks([{text:'CAFE MENU 100'}]),100,100)[0];
  assert.ok(confirmOcrLine(candidate,ocrBlocks([{text:'cafe menu 100\n'}])));
  assert.equal(confirmOcrLine(candidate,ocrBlocks([{text:'CAFE NOISE 123'}])),null);
  assert.equal(confirmOcrLine(candidate,ocrBlocks([{text:'CAFE'},{text:'MENU 100'}])),null);
  assert.equal(confirmOcrLine(candidate,null),null);
  const short=ocrCandidates(ocrBlocks([{text:'OPEN'}]),100,100)[0];
  assert.equal(confirmOcrLine(short,ocrBlocks([{text:'OPFN'}])),null);
});
test('plausible but less certain matching OCR stays unchecked and out of the packet',()=>{
  const candidate=ocrCandidates(ocrBlocks([{text:'CAFE',confidence:78}]),100,100)[0];
  const match=confirmOcrLine(candidate,ocrBlocks([{text:'CAFE',confidence:82}]));
  assert.deepEqual(match,{confidence:78,included:false});
  assert.deepEqual(makePacket({...state(),ocrStatus:'ready',lines:[{...candidate,...match,line_id:uuid(),origin:'auto'}]}).lines,[]);
});
test('OCR confirmation crop padding stays inside the public photo',()=>{
  const candidate=ocrCandidates(ocrBlocks([{text:'OPEN',bbox:{x0:-2,y0:0,x1:100,y1:20}}]),100,100)[0];
  assert.deepEqual(ocrRectangle(candidate,100,100),{left:0,top:0,width:100,height:24});
  assert.ok(candidate.quad.flat().every(n=>n>=0&&n<=1));
});
test('OCR bounds expensive confirmation by confidence without losing reading order',()=>{
  const lines=Array.from({length:105},(_,i)=>({text:`MENU ${i}`,confidence:i===104?99:75}));
  const candidates=ocrCandidates(ocrBlocks(lines),100,100);
  assert.equal(candidates.length,100);assert.equal(candidates.at(-1).text,'MENU 104');
  assert.ok(candidates.every((c,i)=>!i||c.order>candidates[i-1].order));
});
test('captured Android grass false positives fail independent crop confirmation',()=>{
  const fixture=JSON.parse(fs.readFileSync(new URL('./fixtures/ocr-texture-confirmations.json',import.meta.url)));
  const values=fixture.cases.flatMap(c=>c.confirmations);assert.equal(values.length,5);
  for(const value of values)assert.equal(confirmOcrLine(value.candidate,value.blocks),null,value.candidate.text);
});
test('official Labrador class produces animal and Korean dog tag',()=>{const value=suggest([{index:209,categoryName:'Labrador retriever',score:.95}]);assert.equal(value.theme,'animal');assert.deepEqual(value.tags,['강아지']);});
test('food label selects food without inferring a trip or emotion',()=>assert.equal(suggest([{index:964,score:.91}]).theme,'food'));
test('unknown labels and weak evidence abstain',()=>{assert.equal(suggest([{index:0,score:1}]).theme,null);assert.equal(suggest([{index:964,score:.64}]).theme,null);});
test('close competing themes abstain and retain alternatives',()=>{const r=suggest([{index:209,score:.45},{index:964,score:.4}]);assert.equal(r.theme,null);assert.equal(r.alternatives.length,2);});
test('disjoint dog breeds combine as animal while duplicated classes never inflate mass',()=>{assert.equal(suggest([{index:209,score:.4},{index:208,score:.4}]).theme,'animal');assert.equal(suggest([{index:209,score:.4},{index:209,score:.4}]).theme,null);});
test('invalid model scores cannot create a recommendation',()=>assert.equal(suggest([{index:209,score:NaN},{index:964,score:Infinity},{index:209,score:-1}]).theme,null));
test('normalized Unicode tags deduplicate and preserve display',()=>assert.deepEqual(parseTags(' ＣＡＦＥ,cafe,후기,후기 '),['ＣＡＦＥ','후기']));
test('tag code point boundary includes emoji and rejects excessive count',()=>{assert.equal(parseTags('😀'.repeat(30)).length,1);assert.throws(()=>parseTags('😀'.repeat(31)));assert.throws(()=>parseTags(Array.from({length:11},(_,i)=>String(i)).join(',')));});
test('normalization matches server common casefold and whitespace examples',()=>{assert.equal(normalize(' ＣＡＦＥ  바다  라멘 '),'cafe 바다 라멘');assert.equal(normalize('Straße'),'strasse');});
test('manual regions can be undone and cannot escape normalized bounds',()=>{const d=new MosaicDraft();d.add(.1,.1,.3,.3);assert.equal(d.regions[0].active,true);d.undo();assert.equal(d.regions.length,0);assert.throws(()=>d.replace([{x:.9,y:0,w:.2,h:.2,strength:2}]));});
test('face re-detection preserves manual masks',()=>{const d=new MosaicDraft();d.add(.1,.1,.2,.2);d.detected([{id:'face',x:.4,y:.4,w:.2,h:.2,strength:2,automatic:true,active:true}]);d.detected([]);assert.equal(d.regions.length,1);assert.equal(d.regions[0].automatic,false);});
test('toggle and strength edits can be undone without changing old snapshots',()=>{const d=new MosaicDraft();d.add(.1,.1,.2,.2);const old=d.snapshot();d.update(0,{active:false,strength:3});d.undo();assert.deepEqual(d.regions,old);assert.equal(old[0].active,true);});
test('checkpoint reset restores entry masks and itself can be undone',()=>{const d=new MosaicDraft();d.add(.1,.1,.2,.2);d.checkpoint();d.remove(0);d.reset();assert.equal(d.regions.length,1);d.undo();assert.equal(d.regions.length,0);});
test('excess masks and nonfinite rectangles are rejected',()=>{const d=new MosaicDraft();assert.throws(()=>d.replace(Array.from({length:101},()=>({x:0,y:0,w:.1,h:.1,strength:2}))));assert.throws(()=>d.replace([{x:NaN,y:0,w:.1,h:.1,strength:2}]));});
test('new image or search generation rejects late callbacks',()=>{const g=new GenerationGate(),old=g.advance();g.advance();assert.equal(g.accepts(old),false);assert.equal(g.accepts(g.value),true);});
test('packet excludes unchecked OCR completely',()=>{const s=state();s.ocrStatus='ready';s.lines=[{line_id:uuid(),text:'공개 문구',quad:[[0,0],[1,0],[1,1],[0,1]],origin:'auto',included:true},{line_id:uuid(),text:'검색 제외 비밀',quad:[[0,0],[1,0],[1,1],[0,1]],origin:'user',included:false}];const p=makePacket(s);assert.equal(p.lines.length,1);assert.ok(!JSON.stringify(p).includes('검색 제외 비밀'));});
test('skipped OCR sends no lines and unclassified stays different from other',()=>{const s=state();s.ocrStatus='skipped';s.lines=[{included:true,text:'보내지 않음'}];assert.deepEqual(makePacket(s).lines,[]);assert.equal(makePacket(s).theme,null);s.theme='other';s.themeEdited=true;assert.equal(makePacket(s).theme_origin,'user');});
test('owner correction retains expected revision while create omits it',()=>{const s=state();assert.ok(!('expected_revision'in makePacket(s)));s.postId=12;s.revision=4;assert.equal(makePacket(s).expected_revision,4);});
test('empty or excessive selected OCR is rejected instead of silently truncated',()=>{const s=state();s.ocrStatus='ready';s.lines=[{included:true,text:' ',line_id:uuid(),quad:[],origin:'auto'}];assert.throws(()=>makePacket(s));s.lines=Array.from({length:101},()=>({included:true,text:'a',line_id:uuid(),quad:[],origin:'auto'}));assert.throws(()=>makePacket(s));});
test('OCR output drops invalid boxes and retains finite clockwise coordinates',()=>{const r=ocrLines([{paragraphs:[{lines:[{text:'바다라멘\n',confidence:90,bbox:{x0:10,y0:20,x1:50,y1:40}},{text:'bad',confidence:99,bbox:{x0:NaN,y0:0,x1:4,y1:4}}]}]}],100,100);assert.equal(r.length,1);assert.equal(r[0].text,'바다라멘');assert.deepEqual(r[0].quad,[[.1,.2],[.5,.2],[.5,.4],[.1,.4]]);});
test('detected masks pad and clamp at all photo edges',()=>{const r=faceRegions([{boundingBox:{originX:0,originY:0,width:100,height:100}}],100,100)[0];assert.deepEqual([r.x,r.y,r.w,r.h],[0,0,1,1]);});

const face=(x,y,w=60,h=60,score=.9)=>({score,boundingBox:{originX:x,originY:y,width:w,height:h}});
test('multi-scale scans cover every photo edge with a bounded inference budget',()=>{for(const [width,height] of [[960,1280],[2048,1536],[2048,300],[300,2048]]){const scans=faceScans(width,height);assert.ok(scans.length<=40);assert.ok(scans.slice(1).some(s=>s.x===0));assert.ok(scans.slice(1).some(s=>s.x+s.width===width));assert.ok(scans.slice(1).some(s=>s.y+s.height===height));assert.ok(scans.every(s=>s.x>=0&&s.y>=0&&s.x+s.width<=width&&s.y+s.height<=height));}});
test('overlap gives a face on a tile boundary an uncropped second view',()=>{assert.ok(faceScans(960,1280).some(s=>s.width<960&&s.x<360&&s.x+s.width>420&&s.y<500&&s.y+s.height>580));});
test('invalid scan dimensions are rejected and tiny photos need only one pass',()=>{assert.throws(()=>faceScans(NaN,100));assert.throws(()=>faceScans(0,100));assert.equal(faceScans(80,120).length,1);});
test('crop detection projects back to the original photo before normalization',()=>{const result=projectFace({boundingBox:{originX:10,originY:20,width:40,height:50},categories:[{score:.8}]},{x:300,y:400},960,1280);assert.deepEqual(result,face(310,420,40,50,.8));});
test('projected detections clamp image edges and reject invalid boxes',()=>{assert.deepEqual(projectFace(face(-5,-10,30,40),{x:0,y:0},100,100),face(0,0,25,30));assert.equal(projectFace(face(10,10,-3,10),{x:0,y:0},100,100),null);assert.equal(projectFace(face(10,10,10,10,NaN),{x:0,y:0},100,100),null);});
test('duplicate suppression keeps the strongest localized box without expanding into its surroundings',()=>{const input=[face(100,100),face(95,95,75,75,.7)],copy=structuredClone(input),result=mergeFaces(input);assert.equal(result.length,1);assert.deepEqual(result[0].boundingBox,{originX:100,originY:100,width:60,height:60});assert.deepEqual(input,copy);});
test('nearby different faces remain separate even when rectangles touch',()=>assert.equal(mergeFaces([face(0,0,100,100),face(50,0,100,100)]).length,2));
test('low confidence cannot add a face and the region limit remains bounded',()=>{assert.equal(mergeFaces([face(0,0,10,10,.49)]).length,0);assert.equal(mergeFaces(Array.from({length:120},(_,i)=>face(i*20,0,10,10))).length,100);});
test('small-face clusters get a bounded, in-bounds refinement pass',()=>{const found=[face(220,550),face(740,750)],passes=refinementScans(found,960,1280,13);assert.ok(passes.length>0&&passes.length<=13);assert.ok(passes.every(s=>s.x>=0&&s.y>=0&&s.x+s.width<=960&&s.y+s.height<=1280));});
test('empty detections and close-up faces do not trigger unnecessary refinement',()=>{assert.deepEqual(refinementScans([],960,1280,10),[]);assert.deepEqual(refinementScans([face(100,100,300,300)],512,512,10),[]);assert.deepEqual(refinementScans([face(100,100)],960,1280,0),[]);});

test('a smaller duplicate inside the same face is suppressed',()=>assert.equal(mergeFaces([face(100,100,100,100,.95),face(130,130,30,30,.85)]).length,1));

test('proposal suppression retains alternate scales until confirmation',()=>{const input=[face(100,100,100,100),face(110,110,70,70,.8)];assert.equal(mergeFaces(input,.5,true).length,2);assert.equal(mergeFaces(input).length,1);});

test('confirmation crops use two context sizes and remain inside image boundaries',()=>{const f=face(0,0,40,40);assert.deepEqual(confirmationScan(f,100,100,2),{x:0,y:0,width:60,height:60});assert.deepEqual(confirmationScan(f,100,100,3),{x:0,y:0,width:80,height:80});const s=confirmationScan(face(80,80,20,20),100,100,3);assert.equal(s.x+s.width,100);assert.equal(s.y+s.height,100);});

test('tiny confirmation crops retain sufficient context',()=>{const s=confirmationScan(face(40,40,2,2),100,100);assert.equal(s.width,32);assert.equal(s.height,32);});

test('weak repeated background evidence cannot confirm a face',()=>{const p=face(100,100,40,40,.6),s={x:80,y:80,width:80,height:80};assert.equal(confirmFace(p,[face(20,20,40,40,.79)],s,300,300),null);});

test('confirmation projects the refined location instead of retaining the inflated proposal',()=>{const p=face(100,100,60,60),s={x:70,y:70,width:120,height:120};const d=confirmFace(p,[face(35,35,45,45,.91)],s,300,300);assert.deepEqual(d,face(105,105,45,45,.91));});

test('a confident neighboring face cannot confirm an unrelated proposal',()=>{const p=face(100,100,40,40),s={x:80,y:80,width:120,height:120};assert.equal(confirmFace(p,[face(80,20,40,40,.99)],s,300,300),null);});

test('confirmation ignores invalid boxes and selects the strongest matching evidence',()=>{const p=face(100,100,40,40),s={x:80,y:80,width:80,height:80};assert.equal(confirmFace(p,[face(20,20,-1,40,.99),face(20,20,40,40,.81),face(20,20,40,40,.95)],s,300,300).score,.95);});

test('editor follows the visible Safari viewport without fractional overflow',()=>assert.deepEqual(editorViewport({height:673.75,offsetTop:12,scale:1},844),{height:673,top:12}));

test('page magnification does not shrink the editor to a tiny zoomed viewport',()=>assert.deepEqual(editorViewport({height:300,offsetTop:80,scale:2},700),{height:700,top:0}));

test('missing or invalid visual viewport values fall back safely',()=>{assert.deepEqual(editorViewport(null,600),{height:600,top:0});assert.deepEqual(editorViewport({height:NaN,scale:1},600),{height:600,top:0});assert.deepEqual(editorViewport({height:400,offsetTop:-20,scale:1},600),{height:400,top:0});});

test('empty or invalid coordinate entry does not silently move a mask to zero',()=>{for(const value of ['', ' ', 'abc','Infinity'])assert.equal(coordinatePatch({x:.2,y:.3,w:.4,h:.2},'x',value),null);assert.equal(coordinatePatch(null,'x','10'),null);assert.equal(coordinatePatch({x:0,y:0,w:.1,h:.1},'z','10'),null);});

test('position entry respects the existing mask size at both image edges',()=>{const r={x:.2,y:.3,w:.4,h:.2};assert.deepEqual(coordinatePatch(r,'x','100'),{x:.6});assert.deepEqual(coordinatePatch(r,'y','-10'),{y:0});assert.deepEqual(coordinatePatch(r,'y','100'),{y:.8});});

test('size entry cannot create an empty mask or extend beyond the photo',()=>{const r={x:.2,y:.3,w:.4,h:.2};assert.deepEqual(coordinatePatch(r,'w','0'),{w:.008});assert.deepEqual(coordinatePatch(r,'h','100'),{h:.7});});

test('decimal percentage editing retains subpixel-normalized placement without mutating a mask',()=>{const r={x:.2,y:.3,w:.4,h:.2},old={...r};assert.deepEqual(coordinatePatch(r,'x','25.5'),{x:.255});assert.deepEqual(r,old);});

test('adding custom tags merges normalized duplicates without losing selected display',()=>assert.equal(addTags('ＣＡＦＥ, 후기','cafe, 바다, 바다'),'ＣＡＦＥ, 후기, 바다'));
test('a selected recommended tag can be removed and selected again',()=>{const removed=toggleTag('강아지, 후기','강아지');assert.equal(removed,'후기');assert.deepEqual(tagChoices(removed,['강아지']),[{tag:'후기',selected:true},{tag:'강아지',selected:false}]);assert.equal(toggleTag(removed,'강아지'),'후기, 강아지');});
test('adding an eleventh tag or malformed tag fails without discarding previous selections',()=>{const old=Array.from({length:10},(_,i)=>`태그${i}`).join(', ');assert.throws(()=>addTags(old,'새 태그'));assert.throws(()=>addTags('후기','가'.repeat(31)));assert.throws(()=>toggleTag('후기','음식, 동물'));assert.equal(addTags(old,'태그0'),old);});
test('recommended choices deduplicate against custom tags without selecting new recommendations',()=>assert.deepEqual(tagChoices('ＣＡＦＥ, 후기',['cafe','바다','바다']),[{tag:'ＣＡＦＥ',selected:true},{tag:'후기',selected:true},{tag:'바다',selected:false}]));
test('bulk OCR exclusion keeps corrections, identity, and source coordinates for restoration',()=>{const original=[{line_id:uuid(),text:'교정한 문구',origin:'user',quad:[[.1,.1],[.5,.1],[.5,.2],[.1,.2]],included:true}];const excluded=withOcrInclusion(original,false);assert.equal(original[0].included,true);assert.equal(excluded[0].included,false);assert.deepEqual(withOcrInclusion(excluded,true),original);});
test('bulk inclusion caps at 100 while retaining overflow lines to choose later',()=>{const rows=Array.from({length:105},(_,i)=>({line_id:uuid(),text:String(i),included:false}));const selected=withOcrInclusion(rows,true);assert.equal(selected.length,105);assert.equal(selected.filter(l=>l.included).length,100);assert.equal(selected[100].included,false);assert.ok(rows.every(l=>!l.included));});
test('chip tags and compact OCR selection produce the same validated server packet',()=>{const s=state();s.tags=addTags('후기','카페');s.tags=toggleTag(s.tags,'후기');s.tagsEdited=true;s.ocrStatus='ready';s.lines=withOcrInclusion([{line_id:uuid(),text:'수정한 간판',quad:[[0,0],[1,0],[1,1],[0,1]],origin:'user'}],true);let p=makePacket(s);assert.deepEqual(p.tags,[{display:'카페',origin:'user'}]);assert.equal(p.lines[0].text,'수정한 간판');s.lines=withOcrInclusion(s.lines,false);p=makePacket(s);assert.deepEqual(p.lines,[]);assert.equal(p.ocr_status,'ready');});
