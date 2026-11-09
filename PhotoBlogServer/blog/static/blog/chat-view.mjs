import {shortAnswer} from './history-view.mjs';
export const emptyScope=()=>({profile:'',start:'',end:'',date_basis:'processed',include_candidates:false});
export function cleanScope(value={}){return {profile:value.profile||'',start:value.start||'',end:value.end||'',date_basis:value.date_basis==='recorded'?'recorded':'processed',include_candidates:value.include_candidates===true};}
export function scopeLabel(scope,profiles=[]){const person=profiles.find(row=>row.key===scope.profile)?.name||'전체 기록';return person+(scope.start||scope.end?' / 날짜 지정':'')+(scope.include_candidates?' / 후보 포함':'');}
export function replyText(result){return result?.llm?.status==='generated'?result.llm.text:shortAnswer(result?.answer||'응답을 확인하지 못했습니다.');}
// The owner explicitly approved automatic APIs for their app sends on 2026-11-09.
// This does not authorize real provider calls from Codex tests.
export function requestBody(question,scope,conversationId,requestId,llmReady){return {...cleanScope(scope),question,conversation_id:conversationId,request_id:requestId,semantic:true,generate:!!llmReady};}
export function mergeTurns(current,incoming){const values=new Map();for(const row of [...current,...incoming])values.set(row.request_id,row);return [...values.values()].sort((a,b)=>a.id-b.id);}
