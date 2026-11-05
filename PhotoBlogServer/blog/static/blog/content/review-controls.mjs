import {normalize,parseTags} from './rules.mjs';

export function addTags(current,input){return parseTags([...parseTags(current),...parseTags(input)].join(', ')).join(', ');}
export function toggleTag(current,value){
  const tag=parseTags(value);if(tag.length!==1)throw Error('태그를 하나 선택해주세요.');
  const tags=parseTags(current),key=normalize(tag[0]);
  return tags.some(t=>normalize(t)===key)?tags.filter(t=>normalize(t)!==key).join(', '):addTags(current,value);
}
export function tagChoices(current,suggestions=[]){
  const selected=parseTags(current),keys=new Set(selected.map(normalize)),seen=new Set();
  return [...selected,...suggestions].filter(tag=>{const key=normalize(tag);if(seen.has(key))return false;seen.add(key);return true;}).map(tag=>({tag,selected:keys.has(normalize(tag))}));
}
export function withOcrInclusion(lines,included){return lines.map((line,index)=>({...line,included:included&&index<100}));}
