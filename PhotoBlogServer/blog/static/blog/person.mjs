const csrf=document.querySelector('[name=csrfmiddlewaretoken]')?.value;
const review=document.querySelector('#review');
if(location.hash==='#review'&&review)review.open=true;
for(const card of document.querySelectorAll('.face-review')) for(const button of card.querySelectorAll('[data-confirm]')) button.onclick=async()=>{
  const buttons=[...card.querySelectorAll('button')],status=card.querySelector('.review-result');buttons.forEach(b=>b.disabled=true);status.textContent='확인 내용을 저장하고 있습니다.';
  try{const response=await fetch('/api/v1/history/tracks/'+card.dataset.track+'/',{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({revision:Number(card.dataset.revision),profile:button.dataset.confirm||null})});
    if(!response.ok)throw Error(response.status===409?'다른 확인 내용이 저장되었습니다. 화면을 새로고침해주세요.':'저장하지 못했습니다. 다시 시도해주세요.');
    status.textContent='저장했습니다. 이력을 갱신합니다.';location.reload();
  }catch(error){status.textContent=error.message;buttons.forEach(b=>b.disabled=false);}
};
