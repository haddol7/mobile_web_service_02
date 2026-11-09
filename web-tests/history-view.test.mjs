import test from 'node:test';
import assert from 'node:assert/strict';
import {sceneGroups,shortAnswer,applyTrackReview} from '../PhotoBlogServer/blog/static/blog/history-view.mjs';

const frame=(id,session,time,extra={})=>({id,session_id:session,video_seconds:time,tracks:[],passages:[],...extra});
test('scene grouping retains every frame without joining sessions or time windows',()=>{
  const rows=[frame('a','one',1),frame('b','one',2),frame('c','one',11),frame('d','two',2)];
  const groups=sceneGroups(rows);
  assert.equal(groups.length,3);assert.deepEqual(groups.flatMap(group=>group.frames.map(row=>row.id)).sort(),['a','b','c','d']);
  assert.equal(rows.length,4);
});
test('representative favors a recorded passage and all neighbors remain accessible',()=>{
  const groups=sceneGroups([frame('new','s',2),frame('event','s',1,{passages:[{id:'p'}]}),frame('candidate','s',3,{tracks:[{candidate:'a'}]})]);
  assert.equal(groups[0].representative.id,'event');assert.deepEqual(groups[0].frames.map(row=>row.id),['event','new','candidate']);
});
test('frames without a time are not silently merged',()=>{
  assert.equal(sceneGroups([frame('a','s',null),frame('b','s',null)]).length,2);
});
test('brief answer keeps the first complete sentence and leaves canonical text available',()=>{
  const original='선 통과는 6건입니다. 실제 사람 수와 다릅니다.';
  assert.equal(shortAnswer(original),'선 통과는 6건입니다.');assert.equal(original,'선 통과는 6건입니다. 실제 사람 수와 다릅니다.');
});
test('operator review updates the shared track in every frame without changing other tracks',()=>{
  const frames=[frame('a','s',1,{tracks:[{id:9,candidate:'person',revision:1},{id:10,revision:4}]}),frame('b','s',2,{tracks:[{id:9,candidate:'person',revision:1}]})];
  applyTrackReview(frames,9,{confirmed:'person',revision:2});
  for(const row of frames){assert.equal(row.tracks[0].confirmed,'person');assert.equal(row.tracks[0].revision,2);assert.equal(row.tracks[0].reviewed,true);}
  assert.deepEqual(frames[0].tracks[1],{id:10,revision:4});
});
