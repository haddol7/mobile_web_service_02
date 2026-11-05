"""Verify actual YOLO registration against the designated photo API using explicitly provisioned auth."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from urllib.parse import urlsplit

import requests

ROOT=Path(__file__).resolve().parents[1]
PRODUCTION='https://daejinha.pythonanywhere.com'
def sha(data):return hashlib.sha256(data).hexdigest()

def verify_endpoint(origin,token,out,*,allow_local=False):
    origin=origin.rstrip('/');url=urlsplit(origin)
    local=allow_local and url.scheme=='http' and url.hostname=='127.0.0.1' and url.path==''
    if origin!=PRODUCTION and not local:raise ValueError('Only the designated production origin or explicit isolated local test is allowed.')
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    def posts():
        response=session.get(origin+'/api_root/Post/',timeout=(5,30),allow_redirects=False)
        assert response.status_code==200,'Public list failed'
        value=response.json();assert isinstance(value,list)
        return value
    def image(row):
        target=urlsplit(row['image'])
        assert (target.scheme,target.netloc)==(url.scheme,url.netloc),'Unexpected image origin'
        response=session.get(row['image'],timeout=(5,30),allow_redirects=False)
        assert response.status_code==200,'Public image failed'
        return response.content
    prior=out/'verification.json'
    if prior.exists():
        saved=json.loads(prior.read_text())
        assert saved.get('pass') and saved['origin']==origin,'Inspect a failed/different run before retrying'
        match=next((row for row in posts() if row['id']==saved['new_post']['id']),None)
        assert match is not None and sha(image(match))==saved['new_post']['image_sha256']
        return dict(saved,read_only_recheck=True)
    started=out/'attempt.json'
    if started.exists():raise RuntimeError('An earlier attempt exists. Inspect registered posts before another upload.')
    before=posts()
    baseline={row['id']:{'record_sha256':sha(json.dumps(row,sort_keys=True).encode()),'image_sha256':sha(image(row))} for row in before}
    started.write_text(json.dumps({'started_utc':datetime.now(timezone.utc).isoformat(),'origin':origin,'baseline':baseline},indent=2))
    env=dict(os.environ,YOLO_API_TOKEN=token)
    command=[sys.executable,str(ROOT/'tools/run_edge.py'),'--source',str(ROOT/'YOLOv5/data/images/bus.jpg'),
             '--device','cpu','--server',origin,'--project',str(out),'--name','inference','--exist-ok','--nosave']
    run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
    log=re.sub(r'\x1b\[[0-9;]*m','',run.stdout+run.stderr).replace(token,'[REDACTED]')
    (out/'detector-output.txt').write_text(log+f'\nExit code: {run.returncode}\n',encoding='utf-8')
    assert run.returncode==0,'Detector process failed'
    after=posts();new=[row for row in after if row['id'] not in baseline]
    assert len(new)==1,'Expected one new detected post'
    registered=new[0];assert registered['title']=='YOLO: person, bus'
    for row in after:
        if row['id'] in baseline:
            assert sha(json.dumps(row,sort_keys=True).encode())==baseline[row['id']]['record_sha256'],'Existing post changed'
            assert sha(image(row))==baseline[row['id']]['image_sha256'],'Existing photo changed'
    assert set(baseline).issubset({row['id'] for row in after}),'An existing post disappeared'
    blob=image(registered)
    local_images=list((out/'inference/detected').rglob('*.jpg'))
    assert len(local_images)==1 and sha(local_images[0].read_bytes())==sha(blob),'Uploaded image bytes differ'
    root=session.get(origin+'/api_root/',timeout=(5,30),allow_redirects=False)
    page=session.get(origin+'/',timeout=(5,30),allow_redirects=False)
    detail=session.get(origin+f"/post/{registered['id']}/",timeout=(5,30),allow_redirects=False)
    assert root.status_code==page.status_code==detail.status_code==200
    result={'verified_utc':datetime.now(timezone.utc).isoformat(),'origin':origin,
            'environment':'isolated WSL simulation' if local else 'WSL YOLO client against PythonAnywhere',
            'production_verified':not local,'source_transition_verified':False,
            'existing_posts_preserved':True,'existing_photos_preserved':True,'existing_count':len(before),
            'new_post':{'id':registered['id'],'title':registered['title'],'image_sha256':sha(blob)},
            'api_root_status':root.status_code,'blog_status':page.status_code,'detail_status':detail.status_code,
            'pass':True}
    prior.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result

def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run the Edge/backend verifier in WSL.')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials',type=Path,default=Path.home()/'.config/mobile-web-service/common02/edge-auth.json')
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT/'tools/deployment'))
    import pythonanywhere_auth as auth
    if not args.credentials.is_file():raise SystemExit('Designated Edge API authentication has not been provisioned. No upload attempted.')
    config=json.loads(auth.private_read(args.credentials))
    if set(config)!={'base_url','username','token'} or config['base_url']!=PRODUCTION or config['username']!='daejinha' or not re.fullmatch('[a-f0-9]{40}',config['token']):
        raise SystemExit('Invalid designated Edge API configuration. No upload attempted.')
    print(json.dumps(verify_endpoint(PRODUCTION,config['token'],ROOT/'evidence/cloud'),indent=2))

if __name__=='__main__':main()
