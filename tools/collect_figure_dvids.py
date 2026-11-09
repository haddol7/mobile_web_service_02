"""Collect genuine public-figure videos from the public-domain DVIDS source pages."""
from datetime import datetime,timezone
import hashlib,json,os,re
from pathlib import Path
import cv2,requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-demo'
SOURCES=[('trump-ball','https://www.dvidshub.net/video/506134/president-trump-talks-troops-afghanistan-sas-ball'),
         ('trump-arrival','https://www.dvidshub.net/video/512302/president-trump-arriving-langley-air-force-base'),
         ('obama-address','https://www.dvidshub.net/video/358042/president-obama-remarks-ebola-outbreak')]

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    OUT.mkdir(parents=True,exist_ok=True);clips=[]
    for key,page in SOURCES:
        response=requests.get(page,timeout=(10,30));response.raise_for_status();assert 'PUBLIC DOMAIN' in response.text
        (OUT/(key+'-source.html')).write_text(response.text)
        urls=re.findall(r'https[^"<> ]+\.mp4[^"<> ]*',response.text);assert urls
        url=urls[0];target=OUT/(key+'.mp4')
        if not target.exists():
            part=target.with_suffix('.part');total=0
            with requests.get(url,stream=True,timeout=(10,60)) as media:
                media.raise_for_status();expected=int(media.headers.get('Content-Length','0'));assert expected<180*1024**2
                with part.open('wb') as file:
                    for chunk in media.iter_content(1024*1024):
                        total+=len(chunk);assert total<180*1024**2;file.write(chunk)
            assert not expected or total==expected;part.replace(target)
        capture=cv2.VideoCapture(str(target));fps=capture.get(cv2.CAP_PROP_FPS);count=0
        while True:
            ok,image=capture.read()
            if not ok:break
            count+=1
        capture.release();assert count>100 and fps>0
        capture=cv2.VideoCapture(str(target));previews=[]
        for second in (5,15,30,60,120):
            if second>=count/fps:continue
            capture.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,image=capture.read();assert ok
            path=OUT/(key+f'-{second}.jpg');cv2.imwrite(str(path),image);previews.append(str(path.relative_to(ROOT)))
        capture.release()
        info={'id':key,'page':page,'url':url,'path':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
              'bytes':target.stat().st_size,'frames':count,'fps':fps,'previews':previews,'full_decode_pass':True,'license':'Public domain, DVIDS rights notice applies',
              'license_url':'https://www.dvidshub.net/about/copyright'}
        clips.append(info);print(json.dumps({key:info[key] for key in ('id','bytes','frames','fps')}),flush=True)
        result={'collected_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu','clips':clips,'pass':True,'media_in_git':False}
        (OUT/'dvids-collection.json').write_text(json.dumps(result,indent=2)+'\n')
        (ROOT/'evidence/history/public-figure-dvids-collection.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
