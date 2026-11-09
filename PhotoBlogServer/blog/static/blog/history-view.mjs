// Group nearby frames for display only; original IDs and identity states are retained.
export function sceneGroups(rows){
  const groups=new Map();
  const score=row=>(row.passages?.length||0)*10+(row.tracks||[]).reduce((n,t)=>n+(t.confirmed?4:!t.reviewed&&t.candidate?2:0),0);
  for(const row of rows){
    const bucket=row.video_seconds!=null?'video:'+Math.floor(Number(row.video_seconds)/10):row.observed_at?'time:'+row.observed_at.slice(0,18):'frame:'+row.id;
    const key=(row.session_id||row.id)+':'+bucket;
    if(!groups.has(key))groups.set(key,{representative:row,frames:[]});
    const group=groups.get(key);group.frames.push(row);
    if(score(row)>score(group.representative))group.representative=row;
  }
  return [...groups.values()].map(group=>({...group,frames:group.frames.slice().sort((a,b)=>(a.video_seconds??Infinity)-(b.video_seconds??Infinity))}));
}
export function shortAnswer(text){const stop=text.indexOf('다. ');return stop<0?text:text.slice(0,stop+2);}
export function applyTrackReview(frames,id,review){
  for(const frame of frames)for(const track of frame.tracks||[])if(track.id===id){track.confirmed=review.confirmed;track.revision=review.revision;track.reviewed=true;}
}
