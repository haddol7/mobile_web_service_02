import {PhotoStage} from './stage.mjs';
import {decode,digest} from './pipeline.mjs';
const configElement=document.querySelector('#detail-config');
if(configElement){const config=JSON.parse(configElement.textContent);if(config.matched_ids.length)show(config);}
async function show(config){
  const root=document.querySelector('#photo-detail-viewer'),status=document.querySelector('#detail-view-status');
  try{
    const url=new URL(config.image,location.origin);if(url.origin!==location.origin)throw Error('사진 주소를 확인해주세요.');const response=await fetch(url,{credentials:'same-origin',redirect:'error'});if(!response.ok)throw Error('사진을 불러오지 못했어요.');const blob=await response.blob();
    if(config.content.image_sha256&&await digest(blob)!==config.content.image_sha256)throw Error('사진이 변경되어 이전 글자 위치를 표시하지 않았어요. 새로고침 후 다시 검색해주세요.');
    const image=await decode(blob),stage=new PhotoStage(document.querySelector('#detail-stage'));root.hidden=false;stage.image(image);document.querySelector('#detail-photo').hidden=true;const plain=document.querySelector('#plain-photo-lines');if(plain)plain.hidden=true;
    const matched=config.content.lines.filter(line=>config.matched_ids.includes(line.line_id));status.textContent=matched.length?`사진 속 “${config.query}” · 일치 문구 ${matched.length}곳`:'문구를 누르면 사진의 위치를 확인할 수 있어요.';status.classList.toggle('detail-match-note',matched.length>0);
    function locationButton(line,prefix){const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent=prefix+line.text;button.onclick=()=>{stage.focus(line.quad);stage.element.scrollIntoView({block:'center',behavior:'smooth'});};return button;}
    document.querySelector('#detail-reset').onclick=()=>stage.reset();for(const line of matched)document.querySelector('#matched-locations').append(locationButton(line,'일치 위치: '));if(matched.length)stage.focus(matched[0].quad);
  }catch(error){root.hidden=false;for(const element of root.querySelectorAll('canvas,button,details'))element.hidden=true;status.textContent=error.message;}
}

