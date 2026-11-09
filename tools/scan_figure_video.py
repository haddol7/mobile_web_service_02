"""Locate actual enrolled-face candidates in a long, mixed-subject source video."""
from datetime import datetime,timezone
import hashlib,json,os,sys
from pathlib import Path
import cv2

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-demo'
assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
sys.path.insert(0,str(ROOT/'YOLOv5'));from person_tracking import FaceReferences
gallery=FaceReferences(OUT/'references.json')
capture=cv2.VideoCapture(str(OUT/'trump-arrival.mp4'));fps=capture.get(cv2.CAP_PROP_FPS);total=capture.get(cv2.CAP_PROP_FRAME_COUNT)/fps
samples=[]
for second in range(0,int(total),8):
    capture.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,image=capture.read();assert ok
    faces=gallery.analyze(image);hits=[f for f in faces if f['candidate_profile_id']=='public-trump']
    samples.append({'second':second,'face_count':len(faces),'matches':hits})
    if hits:
        path=OUT/f'trump-located-{second}.jpg';assert cv2.imwrite(str(path),image)
        print(json.dumps({'second':second,'similarity':max(f['similarity'] for f in hits),'preview':str(path.relative_to(ROOT))}),flush=True)
capture.release()
result={'verified_utc':datetime.now(timezone.utc).isoformat(),'source':'DVIDS/512302','sample_interval_seconds':8,
        'purpose':'Locate demonstration intervals, not an accuracy benchmark','samples':samples,'pass':True}
(OUT/'trump-location-scan.json').write_text(json.dumps(result,indent=2)+'\n')
