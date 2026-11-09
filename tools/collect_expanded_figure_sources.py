"""Collect whole, distinct DVIDS recordings, retaining dates, rights and checksums."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib,html,json,os,re
from pathlib import Path
import cv2,requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-expanded'
CATALOG=ROOT/'docs/testing/public-figure-expansion-sources.json'
MAX_BYTES=900*1024**2

def probe(item):
    person,page=item;identifier=re.search(r'/video/(\d+)',page)[1]
    try:
        response=requests.get(page,timeout=(10,30));response.raise_for_status()
        assert 'PUBLIC DOMAIN' in response.text,'Public-domain notice unavailable'
        urls=re.findall(r'https[^"<> ]+\.mp4[^"<> ]*',response.text);assert urls,'Public player video unavailable'
        text=html.unescape(re.sub('<[^>]+>',' ',response.text));text=re.sub(r'\s+',' ',text)
        date=re.search(r'Date Taken:\s*(\d{2}\.\d{2}\.\d{4})',text);assert date,'Capture day unavailable'
        day=datetime.strptime(date[1],'%m.%d.%Y').date().isoformat()
        title=html.unescape(re.search(r'<h1[^>]*>(.*?)</h1>',response.text,re.S)[1]);title=re.sub('<[^>]+>','',title).strip()
        head=requests.head(urls[0],timeout=(10,25),allow_redirects=True);head.raise_for_status();size=int(head.headers.get('Content-Length','0'))
        assert 0<size<=MAX_BYTES,'Source outside bounded download size'
        (OUT/(identifier+'-source.html')).write_text(response.text)
        return {'person':person,'source_id':identifier,'source_reference':'DVIDS/'+identifier,'source_url':response.url,'media_url':urls[0],
                'title':title,'capture_day_as_published':day,'declared_bytes':size,'status':'eligible',
                'license':'Public domain; DVIDS rights notice applies','license_url':'https://www.dvidshub.net/about/copyright'}
    except Exception as error:return {'person':person,'source_url':page,'source_id':identifier,'status':'unavailable','reason':str(error)[:180]}

def collect(item):
    target=OUT/(item['source_id']+'.mp4')
    if not target.exists():
        part=target.with_suffix('.part');count=0
        with requests.get(item['media_url'],stream=True,timeout=(10,90)) as response:
            response.raise_for_status()
            with part.open('wb') as file:
                for chunk in response.iter_content(1024*1024):
                    count+=len(chunk);assert count<=MAX_BYTES;file.write(chunk)
        assert count==item['declared_bytes'];part.replace(target)
    assert target.stat().st_size==item['declared_bytes']
    digest=hashlib.sha256()
    with target.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):digest.update(block)
    capture=cv2.VideoCapture(str(target));declared=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));fps=capture.get(cv2.CAP_PROP_FPS);count=0
    while True:
        ok,image=capture.read()
        if not ok:break
        count+=1
    capture.release();assert count>20 and abs(count-declared)<=2 and fps>0
    previews=[];capture=cv2.VideoCapture(str(target))
    for second in sorted({min(15,count/fps/4),count/fps*.25,count/fps*.5,count/fps*.75}):
        capture.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,image=capture.read();assert ok
        path=OUT/(item['source_id']+f'-{round(second)}.jpg');assert cv2.imwrite(str(path),image);previews.append({'second':second,'path':str(path.relative_to(ROOT))})
    capture.release()
    return {**item,'path':str(target.relative_to(ROOT)),'sha256':digest.hexdigest(),'frames':count,'fps':fps,
            'seconds':count/fps,'decoded_size':[image.shape[1],image.shape[0]],'full_decode_pass':True,'previews':previews}

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL';OUT.mkdir(parents=True,exist_ok=True)
    catalog=json.loads(CATALOG.read_text());metadata=OUT/'probes.json'
    if metadata.exists():probes=json.loads(metadata.read_text())
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:probes=list(pool.map(probe,[(p,u) for p,urls in catalog['sources'].items() for u in urls]))
        metadata.write_text(json.dumps(probes,ensure_ascii=False,indent=2)+'\n')
    chosen=[]
    for person in catalog['sources']:
        days=set();media=set();eligible=sorted([r for r in probes if r['person']==person and r['status']=='eligible'],key=lambda r:r['declared_bytes'])
        for item in eligible:
            if item['capture_day_as_published'] in days or item['media_url'] in media:continue
            days.add(item['capture_day_as_published']);media.add(item['media_url']);chosen.append(item)
            if len(days)==catalog['target_new_sources_per_person']:break
        assert len(days)>=catalog['target_new_sources_per_person'],f'Insufficient distinct dated sources: {person}, {len(days)}'
    (OUT/'selected.json').write_text(json.dumps(chosen,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'selected':len(chosen),'bytes':sum(r['declared_bytes'] for r in chosen),'per_person':{p:sum(r['person']==p for r in chosen) for p in catalog['sources']}}),flush=True)
    clips=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(collect,item) for item in chosen]
        for future in as_completed(jobs):
            item=future.result();clips.append(item);print(json.dumps({'collected':len(clips),'source':item['source_reference'],'person':item['person'],'frames':item['frames']}),flush=True)
            record={'collected_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu','clips':clips,
                    'media_in_git':False,'pass':len(clips)==len(chosen),'target_per_person':catalog['target_new_sources_per_person']}
            (OUT/'collection.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            (ROOT/'evidence/history/public-figure-expanded-collection.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    assert len({r['sha256'] for r in clips})==len(clips),'Duplicate original bytes'

if __name__=='__main__':main()
