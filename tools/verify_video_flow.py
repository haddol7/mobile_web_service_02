"""Verify real video inference, duplicate suppression and rejected authentication in an isolated WSL DB."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from threading import Thread
from wsgiref.simple_server import make_server, WSGIRequestHandler

import cv2
import numpy as np
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/video-flow'
def digest(data):return hashlib.sha256(data).hexdigest()
class Quiet(WSGIRequestHandler):
    def log_message(self,*_):pass

def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run inside the WSL project virtual environment.')
    OUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='assessment02-video-') as temporary:
        private=Path(temporary)
        os.environ.update(DJANGO_SETTINGS_MODULE='photoblog.settings',DJANGO_DEBUG='true',
                          DJANGO_DB_PATH=str(private/'db.sqlite3'),DJANGO_MEDIA_ROOT=str(private/'media'))
        sys.path.insert(0,str(ROOT/'PhotoBlogServer'));sys.path.insert(0,str(ROOT/'YOLOv5'))
        import django
        django.setup()
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
        from django.db import connections
        from rest_framework.authtoken.models import Token
        from changedetection import ChangeDetection,UploadError
        call_command('migrate',interactive=False,verbosity=0)
        owner=get_user_model().objects.create(username='daejinha',is_active=True)
        owner.set_unusable_password();owner.save(update_fields=['password'])
        token=Token.objects.create(user=owner).key
        video=private/'presence.avi'
        bus=cv2.resize(cv2.imread(str(ROOT/'YOLOv5/data/images/bus.jpg')),(480,640))
        empty=np.full_like(bus,128)
        phases=[('empty',6),('bus',12),('empty',6),('bus',6)]
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),5,(480,640))
        assert writer.isOpened()
        for phase,count in phases:
            for _ in range(count):writer.write(bus if phase=='bus' else empty)
        writer.release()
        server=make_server('127.0.0.1',0,get_wsgi_application(),handler_class=Quiet)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        try:
            command=[sys.executable,str(ROOT/'tools/run_edge.py'),'--source',str(video),'--device','cpu',
                     '--server',origin,'--project',str(OUT),'--name','detected','--exist-ok','--nosave']
            env=dict(os.environ,YOLO_API_TOKEN=token)
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,env=env,timeout=180)
            output=re.sub(r'\x1b\[[0-9;]*m','',result.stdout+result.stderr)
            (OUT/'detector-output.txt').write_text(output+f'\nExit code: {result.returncode}\n',encoding='utf-8')
            assert result.returncode==0,'Video inference failed'
            response=requests.get(origin+'/api_root/Post/',timeout=15);assert response.status_code==200
            posts=response.json();assert len(posts)==2,f'Expected two appearance uploads, got {len(posts)}'
            captures=[]
            for row in posts:
                assert row['title']=='YOLO: person, bus'
                photo=requests.get(row['image'],timeout=15);assert photo.status_code==200
                image=cv2.imdecode(np.frombuffer(photo.content,np.uint8),cv2.IMREAD_COLOR)
                assert image.shape[:2]==(240,320)
                captures.append({'post_id':row['id'],'image_sha256':digest(photo.content),'size':[320,240]})
            rejected=ChangeDetection(['person'],base_url=origin,token='invalid-test-only')
            try:
                rejected.add(None,[1],private/'rejected',bus)
            except UploadError:
                pass
            else:raise AssertionError('Invalid credentials did not raise an upload error')
            assert list((private/'rejected').rglob('*.jpg')),'Failed frame was not retained'
            after=requests.get(origin+'/api_root/Post/',timeout=15).json()
            assert after==posts,'Rejected upload changed registered posts'
            from verify_cloud_pipeline import verify_endpoint
            protocol_out=OUT/'cloud-protocol-simulation'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            protocol=verify_endpoint(origin,token,protocol_out,allow_local=True)
            assert protocol['pass'] and not protocol['production_verified']
            record={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu',
                    'input':'locally generated video using official bus.jpg and blank frames',
                    'frames':30,'fps':5,'phases':phases,'uploaded_posts':captures,
                    'persistent_frames_suppressed':True,'reappearance_uploaded':True,
                    'invalid_auth_rejected_and_frame_retained':True,'rejected_upload_did_not_change_posts':True,
                    'cloud_verifier_tested_against_isolated_local_server':True,
                    'cloud_protocol_record':str((protocol_out/'verification.json').relative_to(ROOT)),
                    'webcam_tested':False,'pass':True}
            (OUT/'verification.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
            print(json.dumps(record,indent=2))
        finally:
            server.shutdown();server.server_close();connections.close_all()

if __name__=='__main__':main()
