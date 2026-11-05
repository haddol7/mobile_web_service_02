import {MosaicDraft,GenerationGate,THEMES,MAPPING_VERSION,makePacket,parseTags} from './rules.mjs';
import {decode,encode,render,digest} from './pipeline.mjs';
import {PhotoStage} from './stage.mjs?v=editor-fit-1';
import {WebVision,MODEL_VERSIONS} from './vision.mjs?v=ocr-page-2';
import {editorViewport,coordinatePatch} from './editor-controls.mjs?v=editor-fit-1';
import {addTags,toggleTag,tagChoices,withOcrInclusion} from './review-controls.mjs?v=review-tabs-1';

const root=document.querySelector('#content-composer');
if(root)initialize();
function initialize(){
  const config=JSON.parse(document.querySelector('#composer-config').textContent),form=root.querySelector('#photo-form'),$=id=>root.querySelector('#'+id),gate=new GenerationGate();
  const state={postId:config.post_id,revision:0,theme:null,tags:'',tagSuggestions:[],themeEdited:false,tagsEdited:false,themeConfirmed:false,tagsConfirmed:false,analyzed:false,ocrStatus:'not_analyzed',lines:[],modelVersions:{},mappingVersion:MAPPING_VERSION,busy:false,saving:false,faceChecked:false,publicDirty:true,imageChanged:false,dirty:false,uncertain:false,committed:false,conflict:false};
  let engine=null,frame=null,selected=-1,selectedLine=-1,draft=new MosaicDraft(),frozenFields=[],faceMessage=$('face-note').textContent;
  const stage=new PhotoStage($('mosaic-stage'),{draft,onChange:changed=>{state.faceChecked=false;state.publicDirty=true;state.dirty=true;refresh(changed);},onSelect:index=>{selected=index;regionControls();},onZoom:zoom=>{$('photo-zoom').value=String(zoom);$('photo-zoom-value').value=zoom.toFixed(1)+'×';}}),reviewStage=new PhotoStage($('review-stage'));
  function viewport(){const box=editorViewport(window.visualViewport,window.innerHeight);root.style.setProperty('--editor-height',box.height+'px');root.style.setProperty('--editor-top',box.top+'px');root.dataset.editorCompact=String(box.height<=580);}
  window.addEventListener('resize',viewport);window.visualViewport?.addEventListener('resize',viewport);window.visualViewport?.addEventListener('scroll',viewport);viewport();
  function faceNote(text){faceMessage=text;$('face-note').textContent=text;}
  function more(open,focus=false){$('editor-more-panel').hidden=!open;$('editor-more').setAttribute('aria-expanded',String(open));if(open)$('editor-more-close').focus();else if(focus)$('editor-more').focus();}
  function mode(name){stage.mode=name;for(const button of root.querySelectorAll('[data-mode]'))button.setAttribute('aria-pressed',String(button.dataset.mode===name));}
  function status(text,{error=false,busy=state.busy}={}){$('work-status').textContent=text;$('work-status').classList.toggle('error',error);$('work-status').classList.toggle('busy',busy);$('review-status').textContent=text;$('review-status').hidden=!busy&&!error;$('review-status').classList.toggle('error',error);$('picker-status').textContent=text;$('picker-status').hidden=!busy&&!error;$('picker-status').classList.toggle('error',error);if(root.dataset.activePane==='mosaic'&&(busy||error))$('face-note').textContent=text;}
  function reviewTab(name,focus=false){
    root.dataset.reviewTab=name;for(const panel of root.querySelectorAll('[data-review-panel]'))panel.hidden=panel.dataset.reviewPanel!==name;
    for(const button of root.querySelectorAll('[data-review-tab]')){const active=button.dataset.reviewTab===name;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;if(active&&focus)button.focus();}
    reviewStage.highlights=[];reviewStage.reset();if(name==='text'&&state.lines[selectedLine])requestAnimationFrame(()=>reviewStage.focus(state.lines[selectedLine].quad));
  }
  function reviewSummary(){const tags=parseTags(state.tags).length,lines=state.ocrStatus==='ready'?state.lines.filter(l=>l.included).length:0;$('tag-count').textContent=String(tags);$('line-count').textContent=String(state.lines.length);$('review-summary').textContent=`${THEMES[state.theme]||'미분류'} · 태그 ${tags}개 · 검색 문구 ${lines}개`;}
  function step(name){if(name!=='photo'&&!state.source)return;if(name==='review'&&!state.publicBlob){status('먼저 얼굴을 확인하고 게시 사본을 만들어주세요.');return;}more(false);const editing=name==='mosaic',reviewing=name==='review',workspace=['photo','mosaic','review'].includes(name);root.dataset.activePane=name;document.body.classList.toggle('mosaic-editing',workspace);document.documentElement.classList.toggle('mosaic-editing',workspace);for(const el of document.querySelectorAll('body>header,body>footer'))el.inert=workspace;root.querySelector('.composer-steps').hidden=workspace;$('work-status').hidden=workspace;for(const el of root.querySelectorAll('[data-pane]'))el.hidden=el.dataset.pane!==name;for(const button of root.querySelectorAll('[data-step]'))button.setAttribute('aria-current',button.dataset.step===name?'step':'false');if(editing&&!state.busy)$('face-note').textContent=faceMessage;if(reviewing){reviewSummary();reviewTab(root.dataset.reviewTab||'story');}viewport();requestAnimationFrame(()=>{if(!workspace)root.scrollIntoView({block:'start'});stage.draw();reviewStage.draw();});}
  function regionControls(){
    const list=$('region-list');list.replaceChildren(new Option('전체 영역','-1'));draft.regions.forEach((r,i)=>list.add(new Option(`${i+1}번 · ${r.automatic?'자동 얼굴':'직접 가림'} · ${r.active?'가림':'해제'}`,String(i))));if(!draft.regions[selected])selected=-1;list.value=String(selected);stage.selected=selected;
    const region=draft.regions[selected];$('toggle-region').disabled=state.busy||!region;$('remove-region').disabled=state.busy||!region;$('toggle-region').textContent=region?.active?'가림 해제':'다시 가림';$('toggle-region').setAttribute('aria-label',region?.active?'선택 영역 가림 해제':'선택 영역 가리기');if(region)$('mosaic-strength').value=String(region.strength);
    $('selection-actions').hidden=!region;$('strength-label').textContent=region?'선택 강도':'전체 강도';
    for(const input of root.querySelectorAll('[data-coordinate]')){input.disabled=state.busy||!region;if(region)input.value=String(Math.round(region[input.dataset.coordinate]*1000)/10);}
    $('publish-photo').disabled=state.busy||!state.faceChecked||state.publicDirty||state.uncertain||state.committed||state.conflict;
  }
  function busy(value){state.busy=value;stage.disabled=value;if(value){stage.gesture=null;stage.pointers.clear();}else{for(const [el,disabled] of frozenFields)el.disabled=disabled;frozenFields=[];if(root.dataset.activePane==='mosaic')$('face-note').textContent=faceMessage;}root.setAttribute('aria-busy',String(value));for(const button of $('photo-tools').querySelectorAll('button'))button.disabled=value;$('cancel-analysis').hidden=!value||state.saving;$('cancel-analysis').disabled=false;$('review-cancel').hidden=!value||state.saving;$('review-cancel').disabled=false;$('picker-stop').hidden=!value||state.saving;$('picker-stop').disabled=false;$('review-header-spacer').hidden=value&&!state.saving;for(const button of root.querySelectorAll('[data-review-tab]'))button.disabled=state.saving;$('redetect').disabled=false;$('redetect').textContent=value?'중단':'다시 찾기';$('redetect').setAttribute('aria-label',value?'자동 분석 중단':'얼굴 다시 찾기');$('editor-more').disabled=false;$('editor-more').textContent=value?'중단':'더보기';$('editor-more').setAttribute('aria-label',value?'자동 분석 중단':'편집 옵션 더보기');for(const id of ['photo-zoom','region-list','mosaic-strength','photo-tags','skip-ocr'])$(id).disabled=value;for(const checkbox of $('ocr-lines').querySelectorAll('input'))checkbox.disabled=value||state.ocrStatus==='skipped';for(const id of ['include-lines','exclude-lines'])$(id).disabled=value||state.ocrStatus==='skipped'||!state.lines.length;$('ocr-text').disabled=value||!state.lines[selectedLine]?.included||state.ocrStatus==='skipped';regionControls();}
  function job(message){more(false);const ticket=gate.advance();engine?.close();engine=new WebVision();busy(true);status(message);return {ticket,engine};}
  function finish(task,message){if(!gate.accepts(task.ticket))return;busy(false);if(message)status(message);}
  function changed(){state.dirty=true;reviewSummary();regionControls();}
  function refresh(immediate=false){
    const draw=()=>{frame=null;if(!state.source)return;state.preview=render(state.source,draft.regions,state.preview);stage.source=state.preview;stage.draw();regionControls();};
    if(immediate){if(frame)cancelAnimationFrame(frame);draw();}else if(!frame)frame=requestAnimationFrame(draw);
  }
  function retainOldLines(){const held=state.lines.filter(l=>l.origin==='user'||!l.included).map(l=>l.text);if(held.length){$('previous-lines').hidden=false;$('previous-lines').querySelector('p').textContent=held.join(' · ');}state.lines=[];selectedLine=-1;state.ocrStatus='not_analyzed';renderLines();}
  async function choose(file){
    if(!file)return;const task=job('사진을 이 브라우저에서 준비하고 있어요…');
    try{const source=await decode(file);if(!gate.accepts(task.ticket))return;retainOldLines();state.source=source;state.preview=null;state.publicBlob=null;state.publicImage=null;state.faceChecked=false;state.publicDirty=true;state.imageChanged=true;state.modelVersions={};state.mappingVersion=MAPPING_VERSION;state.dirty=true;state.analyzed=false;state.tagSuggestions=[];if(!state.themeEdited&&!state.themeConfirmed)state.theme=null;if(!state.tagsEdited&&!state.tagsConfirmed)state.tags='';renderTags();draft=new MosaicDraft();stage.draft=draft;selected=-1;stage.image(source);reviewStage.image(null);refresh(true);step('mosaic');status('얼굴을 찾고 있어요. 사진은 서버로 전송되지 않습니다.');
      try{const faces=await task.engine.faces(source);if(!gate.accepts(task.ticket))return;draft.detected(faces);draft.checkpoint();state.modelVersions.face=MODEL_VERSIONS.face;faceNote(faces.length?`얼굴 ${faces.length}곳을 가렸어요. 빠진 곳을 확인해주세요.`:'찾은 얼굴이 없어요. 필요한 곳을 직접 가려주세요.');refresh(true);}
      catch(error){if(!gate.accepts(task.ticket))return;faceNote('자동 탐지에 실패했어요. 다시 찾거나 직접 영역을 추가해주세요.');}
      finish(task,'얼굴을 확인하고 게시 사본을 만들어주세요.');
    }catch(error){if(gate.accepts(task.ticket)){finish(task);status(error.message,{error:true});}}
  }
  async function detectAgain(){if(!state.source||state.busy)return;const task=job('얼굴을 다시 찾고 있어요…');try{const faces=await task.engine.faces(state.source);if(!gate.accepts(task.ticket))return;draft.detected(faces);state.modelVersions.face=MODEL_VERSIONS.face;state.faceChecked=false;state.publicDirty=true;faceNote(`자동 탐지 ${faces.length}곳 · 직접 만든 영역은 유지했어요.`);refresh(true);finish(task,'가림 결과를 확인해주세요.');}catch(error){if(!gate.accepts(task.ticket))return;finish(task);status('얼굴 탐지에 실패했어요. 직접 영역을 추가할 수 있어요.',{error:true});}}
  function renderTags(){
    const themes=$('theme-options');themes.replaceChildren();for(const [value,label] of [['','미분류'],...Object.entries(THEMES)]){const button=document.createElement('button');button.type='button';button.className='choice-chip';button.textContent=label;button.disabled=state.busy;button.setAttribute('aria-pressed',String(value===(state.theme||'')));button.onclick=()=>{state.theme=value||null;state.themeEdited=true;renderTags();changed();};themes.append(button);}
    const tags=$('tag-options');tags.replaceChildren();for(const {tag,selected} of tagChoices(state.tags,state.tagSuggestions)){const button=document.createElement('button');button.type='button';button.className='choice-chip';button.textContent=(selected?'✓ ':'＋ ')+tag;button.disabled=state.busy;button.setAttribute('aria-pressed',String(selected));button.onclick=()=>{try{state.tags=toggleTag(state.tags,tag);state.tagsEdited=true;renderTags();changed();$('tag-message').textContent=`태그 ${parseTags(state.tags).length}/10개 선택`;$('tag-message').classList.remove('error');}catch(error){$('tag-message').textContent=error.message;$('tag-message').classList.add('error');}};tags.append(button);}
    if(!tags.childElementCount){const hint=document.createElement('p');hint.className='review-hint';hint.textContent='추천 태그가 없어요. 아래에서 직접 추가할 수 있어요.';tags.append(hint);}reviewSummary();
  }
  function commitTags(){
    const input=$('photo-tags');if(!input.value.trim())return true;
    try{state.tags=addTags(state.tags,input.value);state.tagsEdited=true;input.value='';renderTags();$('tag-message').textContent=`태그 ${parseTags(state.tags).length}/10개 선택`;$('tag-message').classList.remove('error');changed();requestAnimationFrame(()=>{const area=$('tag-options').closest('.tag-review-options'),tag=[...$('tag-options').querySelectorAll('[aria-pressed=true]')].at(-1);if(area&&tag){const overflow=tag.getBoundingClientRect().bottom-area.getBoundingClientRect().bottom;if(overflow>0)area.scrollTop+=overflow+4;}});return true;}
    catch(error){$('tag-message').textContent=error.message;$('tag-message').classList.add('error');return false;}
  }
  function renderSuggestion(result){
    state.analyzed=true;state.mappingVersion=MAPPING_VERSION;state.modelVersions.label=MODEL_VERSIONS.label;
    if(!state.themeEdited&&!state.themeConfirmed)state.theme=result.theme;
    if(!state.tagsEdited&&!state.tagsConfirmed)state.tags=result.tags.join(', ');
    state.tagSuggestions=result.tags;$('theme-note').textContent=result.theme?`자동 추천: ${THEMES[result.theme]} · 바꾸려면 테마를 누르세요.`:'미분류로 두었어요. 어울리는 테마를 직접 고를 수 있어요.';renderTags();
  }
  function selectLine(index,{focusPhoto=true}={}){
    selectedLine=state.lines[index]?index:-1;const line=state.lines[selectedLine];$('ocr-correction').hidden=!line;
    for(const button of $('ocr-lines').querySelectorAll('[data-line]')){const active=Number(button.dataset.line)===selectedLine;button.setAttribute('aria-pressed',String(active));button.closest('.ocr-compact-row').classList.toggle('selected',active);}
    if(!line){reviewStage.highlights=[];reviewStage.draw();return;}
    $('ocr-selected-label').textContent=`${index+1}번 문구 교정`;$('ocr-selection-state').textContent=line.included?'검색 포함':'검색 제외';$('ocr-text').value=line.text;$('ocr-text').disabled=state.busy||!line.included||state.ocrStatus==='skipped';
    if(focusPhoto&&root.dataset.activePane==='review'&&root.dataset.reviewTab==='text'&&reviewStage.source)reviewStage.focus(line.quad);
  }
  function renderLines(){
    const disabled=state.ocrStatus==='skipped',lines=$('ocr-lines'),scroll=lines.scrollTop;lines.replaceChildren();$('skip-ocr').checked=disabled;
    const included=state.lines.filter(l=>l.included).length,names={ready:`${included}/${state.lines.length}개 포함${included<state.lines.length?' · 미선택 문구는 확인 후 포함하세요.':''}`,no_text:'검색에 쓸 만큼 뚜렷한 글자를 찾지 못했어요.',failed:'인식에 실패했어요. 다시 읽거나 검색 없이 게시하세요.',skipped:'글자 검색을 사용하지 않아요.',not_analyzed:'아직 분석하지 않았어요. 다시 읽기를 눌러주세요.'};$('ocr-note').textContent=names[state.ocrStatus];
    for(const id of ['include-lines','exclude-lines'])$(id).disabled=state.busy||disabled||!state.lines.length;
    state.lines.forEach((line,index)=>{
      const row=document.createElement('div');row.className='ocr-compact-row'+(line.included?'':' excluded');const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=line.included;checkbox.disabled=state.busy||disabled;checkbox.setAttribute('aria-label',`${index+1}번 문구 검색에 포함`);
      checkbox.onchange=()=>{if(checkbox.checked&&state.lines.filter(l=>l.included).length>=100){checkbox.checked=false;$('ocr-note').textContent='최대 100개까지 포함할 수 있어요.';return;}line.included=checkbox.checked;selectedLine=index;renderLines();changed();};
      const button=document.createElement('button');button.type='button';button.className='ocr-line-select';button.dataset.line=String(index);button.disabled=state.busy;button.setAttribute('aria-label',`${index+1}번 문구 위치·교정: ${line.text}`);const number=document.createElement('span');number.className='ocr-line-number';number.textContent=String(index+1);const text=document.createElement('span');text.className='ocr-line-preview';text.textContent=line.text;button.append(number,text);button.onclick=()=>selectLine(index);row.append(checkbox,button);lines.append(row);
    });
    if(!state.lines.length){const empty=document.createElement('p');empty.className='ocr-empty review-hint';empty.textContent=state.busy?'분석 결과가 여기에 표시돼요.':'문구가 없어도 게시할 수 있어요.';lines.append(empty);}
    if(state.lines.length>100)$('ocr-note').textContent+=` · 최대 100개`;selectLine(Math.min(Math.max(selectedLine,0),state.lines.length-1));lines.scrollTop=scroll;reviewSummary();
  }
  async function analyze(task,kind='both'){
    if(kind!=='ocr')try{status('사진의 테마와 태그를 추천하고 있어요…');const result=await task.engine.classify(state.publicImage);if(!gate.accepts(task.ticket))return;renderSuggestion(result);}catch(error){if(gate.accepts(task.ticket))$('theme-note').textContent='자동 추천에 실패했어요. 테마와 태그를 직접 선택할 수 있어요.';}
    if(!gate.accepts(task.ticket))return;
    if(kind!=='labels')try{status('한글·영문 문구를 읽고 있어요…');const result=await task.engine.ocr(state.publicBlob,state.width,state.height,m=>{if(gate.accepts(task.ticket)){if(m.status==='recognizing text')status('사진 속 글자를 읽고 있어요…');if(m.status==='reading document')status('문서의 기울기를 보정해 읽고 있어요…');if(m.status==='confirming document')status('손글씨·문서 후보를 확인하고 있어요…');if(m.status==='confirming text')status(`글자 후보를 재확인하고 있어요… ${Math.round((m.progress||0)*100)}%`);}});if(!gate.accepts(task.ticket))return;state.modelVersions.ocr_ko=MODEL_VERSIONS.ocr_ko;state.modelVersions.ocr_latin=MODEL_VERSIONS.ocr_latin;state.lines=result;state.ocrStatus=result.length?'ready':'no_text';renderLines();}catch(error){if(gate.accepts(task.ticket)){state.ocrStatus='failed';state.lines=[];renderLines();}}
    finish(task,'테마·문구와 이야기를 확인한 뒤 게시해주세요.');
  }
  async function apply(){
    if(!state.source||state.busy)return;const task=job('실제 픽셀에 가림을 적용한 게시 사본을 만들고 있어요…');
    try{const result=await encode(render(state.source,draft.regions));if(!gate.accepts(task.ticket))return;retainOldLines();Object.assign(state,{publicBlob:result.blob,publicImage:result.bitmap,sha:result.sha,width:result.bitmap.width,height:result.bitmap.height,faceChecked:true,publicDirty:false,imageChanged:true,analyzed:false});if(!state.themeEdited&&!state.themeConfirmed)state.theme=null;if(!state.tagsEdited&&!state.tagsConfirmed)state.tags='';renderTags();reviewStage.image(result.bitmap);step('review');await analyze(task);}catch(error){if(gate.accepts(task.ticket)){finish(task);status(error.message,{error:true});}}
  }
  async function reanalyze(kind){if(state.busy||!state.publicBlob)return;if(kind==='ocr'&&state.lines.some(l=>l.origin==='user'||!l.included)&&!window.confirm('글자를 다시 읽으면 현재 교정·검색 제외 설정이 새 인식 결과로 바뀝니다. 이전 문구는 메모로 남깁니다. 다시 읽을까요?'))return;if(kind==='ocr')retainOldLines();const task=job('분석을 다시 준비하고 있어요…');await analyze(task,kind);}
  function saveMessage(text,linkText=null,url=null){const area=$('save-result');area.hidden=false;area.replaceChildren();const p=document.createElement('p');p.textContent=text;area.append(p);if(linkText){const link=document.createElement('a');link.className='button secondary';link.textContent=linkText;link.href=url;link.target='_blank';link.rel='noopener';area.append(link);}area.scrollIntoView({block:'nearest'});}
  async function publish(event){
    event.preventDefault();if(state.busy||state.uncertain||state.committed||state.conflict)return;
    if(!state.faceChecked||state.publicDirty||!state.publicBlob){status('얼굴을 확인한 게시 사본을 먼저 만들어주세요.',{error:true});return;}
    if(!commitTags()){reviewTab('tags');$('photo-tags').focus();return;}
    if(![...$('story-fields').querySelectorAll('input,textarea')].every(el=>el.checkValidity()))reviewTab('story');
    if(!form.reportValidity())return;let packet;
    try{packet=makePacket(state);}catch(error){reviewTab('text');status(error.message,{error:true});return;}
    const data=new FormData();data.set('title',$('id_title').value);data.set('text',$('id_text').value);data.set('photo_content',JSON.stringify(packet));if(!state.postId||state.imageChanged)data.set('image',state.publicBlob,'public-photo.jpg');
    frozenFields=[...form.querySelectorAll('input,select,textarea')].map(el=>[el,el.disabled]);for(const [el] of frozenFields)el.disabled=true;state.saving=true;busy(true);status('사진과 확인한 내용을 저장하고 있어요…');
    try{
      const response=await fetch(state.postId?`/api_root/Post/${state.postId}/`:'/api_root/Post/',{method:state.postId?'PATCH':'POST',credentials:'same-origin',redirect:'error',headers:{Accept:'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value},body:data});
      let result;try{result=await response.json();}catch(error){if(response.ok)throw Error('uncertain');result={detail:`서버 응답을 확인하지 못했어요. (${response.status})`};}
      if(!response.ok){if(response.status===409){state.conflict=true;saveMessage('다른 곳에서 사진이나 내용을 수정했어요. 지금 입력은 유지했습니다. 최신 글을 확인한 뒤 수정 화면을 다시 열어주세요.','최신 사진글 보기',`/post/${state.postId}/`);}throw Object.assign(Error(result.detail||Object.values(result).flat(2).join(' ')),{http:response.status});}
      state.committed=true;state.dirty=false;state.saving=false;busy(false);saveMessage('사진글이 저장되었습니다. 상세 조회가 실패해도 다시 게시하지 마세요.','저장한 사진글 열기',`/post/${result.id}/`);status('사진 게시 완료',{busy:false});window.location.assign(`/post/${result.id}/`);
    }catch(error){state.saving=false;busy(false);if(!error.http){state.uncertain=true;saveMessage('전송 결과를 확인하지 못했어요. 입력은 유지했고 자동 재전송을 멈췄습니다. 목록에서 게시 여부를 먼저 확인해주세요.','사진 목록에서 확인','/');status('게시 여부 확인이 필요해요.',{error:true});}else status(error.message,{error:true});regionControls();}
  }
  async function loadExisting(){
    const task=job('게시한 사진과 교정 내용을 불러오고 있어요…');
    try{const imageURL=new URL(config.image,location.origin);if(imageURL.origin!==location.origin)throw Error('같은 서버의 사진만 편집할 수 있어요.');const [response,imageResponse]=await Promise.all([fetch(`/api/v1/posts/${state.postId}/content/`,{credentials:'same-origin'}),fetch(imageURL,{credentials:'same-origin'})]);if(!response.ok||!imageResponse.ok)throw Error('기존 사진을 불러오지 못했어요.');const metadata=await response.json(),blob=await imageResponse.blob(),sha=await digest(blob),source=await decode(blob);if(metadata.image_sha256&&metadata.image_sha256!==sha)throw Error('사진이 변경됐어요. 수정 화면을 다시 열어주세요.');
      if(!gate.accepts(task.ticket))return;Object.assign(state,{revision:metadata.revision,source,publicBlob:blob,publicImage:source,sha,width:metadata.width||source.originalWidth,height:metadata.height||source.originalHeight,theme:metadata.theme,tags:metadata.tags.map(t=>t.display).join(', '),themeEdited:metadata.theme_origin==='user',tagsEdited:true,themeConfirmed:true,tagsConfirmed:true,analyzed:metadata.theme_status!=='not_analyzed',ocrStatus:metadata.ocr_status,lines:metadata.lines.map(l=>({...l,included:true})),modelVersions:metadata.model_versions,mappingVersion:metadata.mapping_version||MAPPING_VERSION,faceChecked:true,publicDirty:false});
      stage.image(source);reviewStage.image(source);renderTags();renderLines();step('review');finish(task,'게시된 사진을 불러왔어요. 새로 가리려면 얼굴 편집을 눌러주세요.');
    }catch(error){finish(task);status(error.message,{error:true});}
  }
  // Progressive enhancement retains the mandatory basic web form without JS.
  $('id_image').required=false;form.noValidate=true;root.classList.add('enhanced');$('photo-tools').hidden=false;$('review-story-slot').append($('story-fields'));form.addEventListener('submit',publish);
  $('photo-input').onchange=e=>choose(e.target.files[0]);$('camera-input').onchange=e=>choose(e.target.files[0]);for(const button of root.querySelectorAll('[data-step]'))button.onclick=()=>step(button.dataset.step);
  for(const button of root.querySelectorAll('[data-mode]'))button.onclick=()=>mode(button.dataset.mode);
  $('redetect').onclick=()=>state.busy?$('cancel-analysis').click():detectAgain();$('apply-mosaic').onclick=apply;$('back-to-mosaic').onclick=()=>step('mosaic');$('review-reset').onclick=()=>reviewStage.reset();$('reset-view').onclick=()=>stage.reset();$('photo-zoom').oninput=e=>stage.setZoom(Number(e.target.value));
  $('editor-more').onclick=()=>state.busy?$('cancel-analysis').click():more($('editor-more-panel').hidden);
  $('editor-more-close').onclick=()=>more(false,true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('editor-more-panel').hidden){e.preventDefault();more(false,true);}});
  document.addEventListener('pointerdown',e=>{if(!$('editor-more-panel').hidden&&!$('editor-more-panel').contains(e.target)&&!$('editor-more').contains(e.target))more(false);});
  $('region-list').onchange=e=>{selected=Number(e.target.value);mode(selected>=0?'select':'pan');regionControls();stage.draw();};
  $('add-region').onclick=()=>{draft.add(.3,.3,.25,.25);selected=draft.regions.length-1;mode('select');more(false);state.faceChecked=false;state.publicDirty=true;changed();refresh(true);stage.element.focus();};
  $('toggle-region').onclick=()=>{const r=draft.regions[selected];if(r){draft.update(selected,{active:!r.active});state.faceChecked=false;state.publicDirty=true;changed();refresh(true);}};
  $('remove-region').onclick=()=>{draft.remove(selected);selected=-1;state.faceChecked=false;state.publicDirty=true;changed();refresh(true);};
  for(const [id,method] of [['undo-mosaic','undo'],['reset-mosaic','reset']])$(id).onclick=()=>{draft[method]();selected=-1;state.faceChecked=false;state.publicDirty=true;changed();refresh(true);};
  $('mosaic-strength').onchange=e=>{const strength=Number(e.target.value);if(selected>=0)draft.update(selected,{strength});else{draft.remember();draft.replace(draft.regions.map(r=>({...r,strength})));}state.faceChecked=false;state.publicDirty=true;changed();refresh(true);};
  for(const input of root.querySelectorAll('[data-coordinate]')){const names={x:'가로',y:'세로',w:'너비',h:'높이'};input.parentElement.firstChild.textContent=names[input.dataset.coordinate]+' (%) ';input.onchange=()=>{const patch=coordinatePatch(draft.regions[selected],input.dataset.coordinate,input.value);if(!patch){regionControls();return;}draft.update(selected,patch);state.faceChecked=false;state.publicDirty=true;changed();refresh(true);};}
  for(const button of root.querySelectorAll('[data-review-tab]')){button.onclick=()=>reviewTab(button.dataset.reviewTab);button.onkeydown=e=>{const tabs=[...root.querySelectorAll('[data-review-tab]')],index=tabs.indexOf(button);let next;if(e.key==='ArrowRight')next=(index+1)%tabs.length;else if(e.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=tabs.length-1;else return;e.preventDefault();reviewTab(tabs[next].dataset.reviewTab,true);};}
  $('add-tag').onclick=commitTags;$('photo-tags').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();commitTags();}};$('photo-tags').oninput=()=>{state.dirty=true;};
  $('ocr-text').oninput=e=>{const line=state.lines[selectedLine];if(!line)return;line.text=e.target.value;line.origin='user';const button=$('ocr-lines').querySelector(`[data-line="${selectedLine}"]`);button.querySelector('.ocr-line-preview').textContent=line.text;button.setAttribute('aria-label',`${selectedLine+1}번 문구 위치·교정: ${line.text}`);changed();};
  for(const [id,include] of [['include-lines',true],['exclude-lines',false]])$(id).onclick=()=>{state.lines=withOcrInclusion(state.lines,include);renderLines();changed();};
  $('skip-ocr').onchange=e=>{if(e.target.checked){state.savedOcrStatus=state.ocrStatus;state.ocrStatus='skipped';}else state.ocrStatus=state.savedOcrStatus||'not_analyzed';renderLines();changed();};$('rerun-labels').onclick=()=>reanalyze('labels');$('rerun-ocr').onclick=()=>reanalyze('ocr');
  $('cancel-analysis').onclick=()=>{gate.advance();engine?.close();busy(false);if(!state.publicBlob){state.faceChecked=false;state.publicDirty=true;faceNote('자동 탐지를 중단했어요. 얼굴을 직접 확인하고 가릴 수 있어요.');}status('분석을 중단했어요. 내용을 직접 확인해주세요.');};
  $('review-cancel').onclick=()=>$('cancel-analysis').click();$('picker-stop').onclick=()=>$('cancel-analysis').click();
  $('ocr-text').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();e.target.blur();}};
  for(const id of ['id_title','id_text'])$(id).addEventListener('input',changed);
  window.addEventListener('beforeunload',e=>{if(state.dirty&&!state.committed){e.preventDefault();e.returnValue='';}});window.addEventListener('pagehide',()=>engine?.close());
  renderTags();renderLines();reviewTab('story');regionControls();if(config.post_id)loadExisting();else step('photo');
}

