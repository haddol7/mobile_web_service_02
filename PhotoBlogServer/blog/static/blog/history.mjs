import {sceneGroups,shortAnswer,applyTrackReview} from './history-view.mjs';
const $=s=>document.querySelector(s);
const filter=$('#history-filter'),dialog=$('#history-detail'),status=$('#history-status');
const config=JSON.parse($('#history-config').textContent);
if(config.question_page){const viewport=()=>{const box=window.visualViewport,height=box?.height||innerHeight,top=box?.offsetTop||0;document.body.dataset.questionCompact=String(height<400);const inset=Math.max(0,(document.querySelector('body>header')?.getBoundingClientRect().bottom||0)-top);document.documentElement.style.setProperty('--question-height',Math.max(0,height-inset)+'px');document.documentElement.style.setProperty('--question-top',(top+inset)+'px');};window.addEventListener('resize',viewport);window.visualViewport?.addEventListener('resize',viewport);window.visualViewport?.addEventListener('scroll',viewport);viewport();}
let profiles=[],page=1,next=null,current=null,rows=[],days=[],generation=0,currentScene=[];
const scenes=new Map(),questionDialog=$('#history-question-dialog'),answerDialog=$('#history-answer-dialog');
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
const csrf=()=>document.querySelector('[name=csrfmiddlewaretoken]').value;
async function api(path,method='GET',data){
  const response=await fetch('/api/v1/history/'+path,{method,credentials:'same-origin',
    headers:{Accept:'application/json',...(data?{'Content-Type':'application/json','X-CSRFToken':csrf()}:{} )},
    body:data?JSON.stringify(data):undefined});
  const result=await response.json();
  if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result));
  return result;
}
let selectedSession=new URLSearchParams(location.search).get('session')||'';
let filtersReady=false;
$('#history-question').querySelector('[type=submit]').disabled=true;
function params(){const f=new FormData(filter);return {profile:f.get('profile')||'',start:f.get('start')||'',end:f.get('end')||'',include_candidates:f.has('include_candidates'),date_basis:f.get('date_basis')||'processed',...(selectedSession?{session:selectedSession}:{})};}
function name(key){return profiles.find(p=>p.key===key)?.name||key;}
function timeLabel(row){
  if(filter.elements.date_basis.value==='processed')return '분석 '+new Date(row.processed_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})+(row.video_seconds!=null?' / 영상 '+Number(row.video_seconds).toFixed(1)+'초':'');
  if(row.observed_at)return new Date(row.observed_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})+(row.source_kind==='live'?' 수신':' 촬영');
  return '촬영 날짜 미상'+(row.video_seconds!=null?' / 영상 '+Number(row.video_seconds).toFixed(1)+'초':'');
}
function options(select,blank){select.replaceChildren(new Option(blank,''));profiles.forEach(p=>select.add(new Option(p.name,p.key)));}
function drawDays(){
  const nav=$('#history-days');if(!nav)return;nav.replaceChildren();
  const choose=(label,key,selected)=>{const button=node('button',label,'day-chip');button.type='button';button.setAttribute('aria-pressed',String(selected));button.onclick=()=>{filter.elements.start.value=key;filter.elements.end.value=key;page=1;load();};nav.append(button);};
  choose('전체 날짜','',!filter.elements.start.value&&!filter.elements.end.value);
  days.filter(day=>day.date_key).forEach(day=>choose(day.date_key.slice(5).replace('-','/')+' ('+day.session_count+')',day.date_key,filter.elements.start.value===day.date_key&&filter.elements.end.value===day.date_key));
}
function draw(){
  const grid=$('#history-grid');grid.replaceChildren();
  const grouped=rows.some(row=>row.frames)?rows.map(row=>({representative:row,frames:row.frames||[row]})):sceneGroups(rows);scenes.clear();
  if(!grouped.length){const empty=node('div',null,'history-empty');empty.append(node('strong','조건에 맞는 관측 장면이 없습니다.'),node('p','Edge에서 기록이 수신되면 표시됩니다. 촬영 날짜가 없는 자료는 날짜 조회에서 제외됩니다.','muted'));grid.append(empty);}
  let lastDay;
  grouped.forEach(group=>{const row=group.representative;group.frames.forEach(frame=>scenes.set(frame.id,group.frames));
    const day=row.date_key||'unknown';if(day!==lastDay){lastDay=day;const heading=node('h2',row.date_label||'촬영 날짜 미상','history-date-heading');heading.append(node('span',filter.elements.date_basis.value==='processed'?'분석일':'원본 촬영일'));grid.append(heading);}
    const card=node('button',null,'history-card');card.type='button';card.setAttribute('aria-label',row.source+' '+timeLabel(row));
    if(row.image_url){const image=node('img');image.src=row.image_url;image.alt='관측 사진';image.loading='lazy';card.append(image);}
    const copy=node('span',null,'copy');copy.append(node('strong',row.source),node('span',timeLabel(row),'muted'));
    const known=[...new Set(row.tracks.filter(t=>t.confirmed).map(t=>name(t.confirmed)))];
    const candidates=[...new Set(row.tracks.filter(t=>!t.confirmed&&!t.reviewed&&t.candidate).map(t=>name(t.candidate)))];
    copy.append(node('span',known.length?'확인: '+known.join(', '):candidates.length?'얼굴 후보 확인 필요':'인물 미확인','identity-badge'+(candidates.length&&!known.length?' pending':'')));
    copy.append(node('span','기록 사진 '+(row.sample_count||group.frames.length)+'장'+(row.purpose==='demo'?' / 공개 영상 시연':''),'muted scene-count'));card.append(copy);
    card.onclick=()=>open(row);grid.append(card);
  });
  $('#history-prev').disabled=page===1;$('#history-next').disabled=!next;$('#history-page-number').textContent=page+'페이지';
}
async function load(){
  const ticket=++generation;status.dataset.state='loading';status.textContent='기록을 불러오고 있습니다.';
  const query=new URLSearchParams({...params(),page,limit:12});
  try{const result=await api('sessions/?'+query);if(ticket!==generation)return;rows=result.results;days=result.days||[];next=result.next_page;drawDays();draw();status.dataset.state='ready';status.textContent=rows.length?'이 페이지 '+rows.length+'개 장면 / '+(filter.elements.date_basis.value==='processed'?'분석일':'원본 촬영일')+' 기준':'조건에 맞는 기록이 없습니다.';}
  catch(error){if(ticket===generation){status.dataset.state='error';status.textContent='기록을 불러오지 못했습니다. 다시 시도해주세요.';const retry=node('button','다시 시도');retry.type='button';retry.onclick=load;status.append(' ',retry);}}
}
function selectedTrack(){return current?.tracks.find(t=>String(t.id)===$('#detail-track').value);}
function trackDetails(){
  const track=selectedTrack();$('#detail-profile').value=track?.confirmed||'';
  $('#detail-candidate').textContent=!track?'추적 기록이 없는 사진입니다.':track.confirmed?'운영자 확인: '+name(track.confirmed):
    track.reviewed?'운영자가 인물 미확인으로 처리했습니다.':track.candidate?'얼굴 후보: '+name(track.candidate)+' / 유사도 '+Number(track.similarity).toFixed(2):'얼굴 후보가 없습니다.';
  $('#detail-confirm').disabled=!track;
}
function open(row){
  currentScene=scenes.get(row.id)||[row];showFrame(row);if(!dialog.open)dialog.showModal();
}
function showFrame(row){
  current=row;$('#detail-status').textContent='';$('#detail-time').textContent=row.source+' / '+timeLabel(row);
  const image=$('#detail-image');image.hidden=!row.image_url;if(row.image_url)image.src=row.image_url;
  const select=$('#detail-track');select.replaceChildren();row.tracks.forEach(t=>select.add(new Option('추적 '+t.track_id,String(t.id))));
  options($('#detail-profile'),'인물 미확인');trackDetails();
  const position=currentScene.findIndex(frame=>frame.id===row.id);$('#scene-navigation').hidden=currentScene.length<2;$('#scene-position').textContent=(position+1)+' / '+currentScene.length;
  $('#scene-prev').disabled=position<=0;$('#scene-next').disabled=position+1>=currentScene.length;
}
$('#scene-prev').onclick=()=>{const at=currentScene.findIndex(frame=>frame.id===current.id);if(at>0)showFrame(currentScene[at-1]);};
$('#scene-next').onclick=()=>{const at=currentScene.findIndex(frame=>frame.id===current.id);if(at+1<currentScene.length)showFrame(currentScene[at+1]);};
$('#detail-close').onclick=()=>dialog.close();$('#detail-track').onchange=trackDetails;
$('#detail-confirm').onclick=async()=>{
  const track=selectedTrack();if(!track)return;
  const button=$('#detail-confirm');button.disabled=true;
  try{const result=await api('tracks/'+track.id+'/','PATCH',{revision:track.revision,profile:$('#detail-profile').value||null});
    applyTrackReview([...rows,...currentScene,...[...scenes.values()].flat()],track.id,result);trackDetails();draw();
    if(current.image_url){const updated=new URL(current.image_url,location.origin);updated.searchParams.set('review',String(result.revision));$('#detail-image').src=updated.href;}
    $('#detail-status').textContent='확인 내용을 저장했습니다.';}
  catch(error){$('#detail-status').textContent=error.message;}finally{button.disabled=false;}
};
$('#detail-rename').onclick=async()=>{
  const key=$('#detail-profile').value;if(!key){$('#detail-status').textContent='이름을 바꿀 인물을 선택해주세요.';return;}
  const value=prompt('인물 프로필 이름',name(key));if(!value?.trim())return;
  try{await api('profiles/','PATCH',{key,name:value.trim()});profiles.find(p=>p.key===key).name=value.trim();
    const old=filter.elements.profile.value;options(filter.elements.profile,'전체 추적 기록');filter.elements.profile.value=old;
    options($('#detail-profile'),'인물 미확인');$('#detail-profile').value=key;trackDetails();draw();}
  catch(error){$('#detail-status').textContent=error.message;}
};
filter.onsubmit=e=>{e.preventDefault();if(answerDialog.open)answerDialog.close();if(!config.question_page)filter.querySelector('details').open=false;page=1;if(!config.question_page)load();};
filter.elements.profile.onchange=()=>{if(!config.question_page)filter.requestSubmit();};
$('#history-clear').onclick=()=>{filter.reset();selectedSession='';filter.querySelector('details').open=false;page=1;load();};
$('#history-prev').onclick=()=>{if(page>1){page--;load();}};$('#history-next').onclick=()=>{if(next){page=next;load();}};
document.querySelectorAll('[data-question]').forEach(b=>b.onclick=()=>{$('#question').value=b.dataset.question;$('#question').focus();});
$('#ai-choice').hidden=!config.llm_ready;
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>$('#'+button.dataset.close).close());
$('#question-panel').addEventListener('toggle',()=>{if($('#question-panel').open&&!questionDialog.open&&!answerDialog.open)questionDialog.showModal();});
questionDialog.addEventListener('close',()=>{$('#question-panel').open=false;});
$('#ask-again').onclick=()=>{answerDialog.close();if(config.question_page)$('#question').focus();else{$('#question-panel').open=true;questionDialog.showModal();}};
function evidenceCard(group){
  const row=group.representative;group.frames.forEach(frame=>scenes.set(frame.id,group.frames));
  const button=node('button');button.type='button';
  if(row.image_url){const image=node('img');image.src=row.image_url;image.alt='답변 근거 사진';image.loading='lazy';button.append(image);}
  button.append(node('span',row.source+' / '+timeLabel(row)));button.onclick=()=>{answerDialog.close();open(row);};return button;
}
function renderAnswer(panel,result){
  const facts=result.facts,metrics=node('div',null,'answer-metrics');metrics.append(node('span','영상 '+(facts.source_count??0)+'개'),node('span','확인된 추적 '+facts.confirmed_tracks+'개'));
  panel.replaceChildren(metrics);const generated=result.llm.status==='generated';
  const retrieval=result.retrieval||{};
  if(retrieval.strategy==='semantic')panel.append(node('p',retrieval.status==='ranked'?'의미 검색으로 선택한 최대 5개 영상의 기록입니다.':retrieval.status==='no_match'?'질문과 유사한 영상 설명을 찾지 못했습니다.':retrieval.status==='empty'?'조회 조건에 맞는 기록이 없습니다.':'의미 검색을 사용할 수 없어 조건 조회 결과를 표시했습니다. 색인 상태를 확인해주세요.','answer-note'));
  if(generated)panel.append(node('strong','AI 설명'));
  panel.append(node('p',generated?result.llm.text:shortAnswer(result.answer)));
  panel.append(node('p',facts.sampled_frames?'통과 건수는 사람 수나 방문 횟수와 다릅니다.':'기록 없음이 실제 부재를 뜻하지는 않습니다.','answer-note'));
  if(result.llm.status==='unavailable')panel.append(node('p','AI 설명을 받지 못해 기록 조회 결과를 표시했습니다.','answer-note'));
  const full=node('details',null,'answer-details');full.append(node('summary','집계 자세히'),node('p',result.answer));panel.append(full);
  panel.append(node('strong','근거 사진 '+result.evidence.length+'장'));const groups=sceneGroups(result.evidence),links=node('div',null,'evidence-links');groups.slice(0,3).forEach(group=>links.append(evidenceCard(group)));panel.append(links);
  if(groups.length>3){const more=node('details',null,'evidence-all'),rest=node('div',null,'evidence-links');more.append(node('summary','근거 장면 '+(groups.length-3)+'개 더 보기'));groups.slice(3).forEach(group=>rest.append(evidenceCard(group)));more.append(rest);panel.append(more);}
}
$('#history-question').onsubmit=async e=>{
  e.preventDefault();if(!filtersReady)return;const form=e.currentTarget,button=form.querySelector('[type=submit]');button.disabled=true;
  form.elements.question.blur();
  if(questionDialog.open)questionDialog.close();$('#question-panel').open=false;if(!answerDialog.open)answerDialog.showModal();
  const panel=$('#history-answer');panel.hidden=false;panel.replaceChildren(node('p','기록을 확인하고 있습니다.'));
  try{const result=await api('ask/','POST',{...params(),question:form.elements.question.value,generate:!!form.elements.generate?.checked,semantic:!!form.elements.semantic?.checked});
    renderAnswer(panel,result);
  }catch(error){panel.replaceChildren(node('p','답변을 불러오지 못했습니다. 다시 질문해주세요.'));}finally{button.disabled=false;}
};
api('profiles/').then(result=>{profiles=result.results;options(filter.elements.profile,'전체 관측 기록');const initial=new URLSearchParams(location.search);const key=initial.get('profile');if(profiles.some(p=>p.key===key))filter.elements.profile.value=key;filter.elements.include_candidates.checked=initial.get('include_candidates')==='true';filter.elements.date_basis.value=initial.get('date_basis')==='recorded'?'recorded':'processed';for(const field of ['start','end'])if(/^\d{4}-\d{2}-\d{2}$/.test(initial.get(field)||''))filter.elements[field].value=initial.get(field);filtersReady=true;$('#history-question').querySelector('[type=submit]').disabled=false;if(!config.question_page)return load();}).catch(error=>status.textContent=error.message);
