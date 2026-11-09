"""Collect attributed White House public speech videos for two named demo profiles."""
from datetime import datetime,timezone
import hashlib,json,os,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
import cv2,requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-demo'
TITLES=["2017-03-18 President Trump's Weekly Address.webm","President Trump Congratulates the Collegiate National Champions of 2016-2017.webm","2016-01-09 President Obama's Weekly Address.webm"]

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    OUT.mkdir(parents=True,exist_ok=True)
    response=requests.get('https://commons.wikimedia.org/w/api.php',params={'action':'query','format':'json','prop':'imageinfo','titles':'|'.join('File:'+title for title in TITLES),'iiprop':'url|size|sha1|extmetadata'},headers={'User-Agent':'MobileWebServiceCourseDemo/1.0 (local research dataset collection)'},timeout=(10,30))
    response.raise_for_status();data=response.json()
    (OUT/'commons-metadata.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    record=[]
    for page in sorted(data['query']['pages'].values(),key=lambda p:'Obama' in p['title']):
        info=page['imageinfo'][0];assert info['size']<110*1024**2
        meta=info['extmetadata'];assert meta['LicenseShortName']['value']=='Public domain'
        if 'Obama' in page['title']:continue  # Existing verified HDTF originals are already local.
        filename='obama-address.webm' if 'Obama' in page['title'] else 'trump-weekly.webm' if 'Weekly' in page['title'] else 'trump-champions.webm'
        target=OUT/filename
        if not target.exists():
            part=target.with_suffix('.part');part.unlink(missing_ok=True)
            with part.open('wb') as file:
                for start in range(0,info['size'],4*1024**2):
                    end=min(info['size']-1,start+4*1024**2-1)
                    for attempt in range(5):
                        media=requests.get(info['url'].split('?')[0],headers={'User-Agent':'MobileWebServiceCourseDemo/1.0 (local research dataset collection)','Range':f'bytes={start}-{end}','Accept-Encoding':'identity'},timeout=(10,60))
                        if media.status_code!=429:break
                        delay=int(media.headers.get('Retry-After','10'));assert delay<=60
                        print(json.dumps({'title':page['title'],'rate_limit_wait_seconds':delay}),flush=True);time.sleep(delay+1)
                    media.raise_for_status()
                    assert media.status_code==206 and media.headers.get('Content-Range','').startswith(f'bytes {start}-')
                    assert len(media.content)==end-start+1
                    file.write(media.content)
            assert part.stat().st_size==info['size'];part.replace(target)
        assert hashlib.sha1(target.read_bytes()).hexdigest()==info['sha1']
        capture=cv2.VideoCapture(str(target));count=0;fps=capture.get(cv2.CAP_PROP_FPS)
        while True:
            ok,image=capture.read()
            if not ok:break
            count+=1
        capture.release();assert count>30
        previews=[];capture=cv2.VideoCapture(str(target))
        for second in (5,15,30):
            capture.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,image=capture.read();assert ok
            preview=OUT/(target.stem+f'-{second}.jpg');cv2.imwrite(str(preview),image);previews.append(str(preview.relative_to(ROOT)))
        capture.release()
        item={'title':page['title'],'page_id':page['pageid'],'url':info['descriptionurl'],'download_url':info['url'],
              'path':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'sha1':info['sha1'],
              'size':info['size'],'frames_decoded':count,'fps':fps,'dimensions':[info['width'],info['height']],
              'date_as_published':meta.get('DateTimeOriginal',{}).get('value'),'license':'Public domain','artist':meta.get('Artist',{}).get('value'),
              'full_decode_pass':True,'previews':previews}
        record.append(item);print(json.dumps({k:item[k] for k in ('title','frames_decoded','fps','size')}),flush=True)
    result={'collected_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu','clips':record,'media_in_git':False,'pass':len(record)==2,'status':'complete' if len(record)==2 else 'incomplete_not_used'}
    (OUT/'commons-collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'evidence/history/public-figure-collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
