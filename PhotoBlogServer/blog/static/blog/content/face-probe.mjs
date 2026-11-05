import {WebVision,MODEL_VERSIONS} from './vision.mjs?v=face-confirm-5';
import {decode,render,digest} from './pipeline.mjs';
const panel=document.createElement('section');panel.className='panel';
panel.innerHTML='<h2>비공개 얼굴 사진 검증</h2><p>사진은 브라우저 메모리에서만 처리하며 게시·업로드하지 않습니다.</p><label for="face-probe-file">검증할 사진</label><input id="face-probe-file" type="file" accept="image/*"><button type="button" id="face-probe-run">선택한 사진 얼굴 검사</button><p id="face-probe-status" role="status">대기</p><canvas id="face-probe-photo" style="max-width:100%"></canvas><pre id="face-probe-record"></pre>';
document.querySelector('main').append(panel);
panel.querySelector('#face-probe-run').onclick=async()=>{
  const file=panel.querySelector('input').files[0];if(!file)return;
  const button=panel.querySelector('button'),status=panel.querySelector('#face-probe-status');button.disabled=true;status.textContent='얼굴 분석 중';
  const engine=new WebVision(),started=performance.now();
  try{
    const source=await decode(file),pixels=source.getContext('2d').getImageData(0,0,source.width,source.height).data;
    const regions=await engine.faces(source),masked=render(source,regions),output=panel.querySelector('canvas');output.width=masked.width;output.height=masked.height;output.getContext('2d').drawImage(masked,0,0);
    const edited=masked.getContext('2d').getImageData(0,0,source.width,source.height).data;
    const changed=regions.map(r=>{for(let y=Math.floor(r.y*source.height);y<Math.min(source.height,(r.y+r.h)*source.height);y+=3)for(let x=Math.floor(r.x*source.width);x<Math.min(source.width,(r.x+r.w)*source.width);x+=3){const i=(y*source.width+x)*4;if(pixels[i]!==edited[i]||pixels[i+1]!==edited[i+1]||pixels[i+2]!==edited[i+2])return true;}return false;});
    const untouched=source.getContext('2d').getImageData(0,0,source.width,source.height).data;
    const record={faces:regions.length,width:source.width,height:source.height,regions,masked_regions_changed:changed,source_pixels_unchanged:pixels.every((value,index)=>value===untouched[index]),sha256:await digest(file),elapsed_ms:Math.round(performance.now()-started),model_version:MODEL_VERSIONS.face,environment:navigator.userAgent,uploaded:false};
    panel.querySelector('pre').textContent=JSON.stringify(record,null,2);status.textContent=`완료 · 얼굴 ${regions.length}곳`;
  }catch(error){status.textContent='실패 · '+error.message;panel.querySelector('pre').textContent=JSON.stringify({error:error.message});}
  finally{engine.close();button.disabled=false;}
};
