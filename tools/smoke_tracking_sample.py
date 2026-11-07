"""Check that an actual collected raw pedestrian clip runs through the existing YOLO detector."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run the detector smoke check inside WSL.')
    collection=json.loads((ROOT/'evidence/tracking-samples/collection.json').read_text())
    sequence=next(item for item in collection['sequences'] if item['id']=='TUD-Campus')
    source=ROOT/sequence['video']['path']
    assert sha(source)==sequence['video']['sha256']
    output=ROOT/'evidence/private/tracking-samples/smoke'
    command=[sys.executable,str(ROOT/'tools/run_edge.py'),'--source',str(source),'--device','cpu',
             '--classes','0','--nosave','--save-txt','--save-conf','--project',str(output),
             '--name','TUD-Campus','--exist-ok']
    run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=120)
    log=re.sub(r'\x1b\[[0-9;]*m','',run.stdout+run.stderr)
    public=ROOT/'evidence/tracking-samples'
    (public/'detector-smoke.txt').write_text(log+f'\nExit code: {run.returncode}\n',encoding='utf-8')
    assert run.returncode==0,'Actual video inference failed'
    frames=[int(value) for value in re.findall(r'video 1/1 \((\d+)/71\)',log)]
    assert frames==list(range(1,72)),'Detector did not process all 71 video frames'
    labels=sorted((output/'TUD-Campus/labels').glob('*.txt'))
    assert labels,'No pedestrian detections were produced'
    boxes=0
    for path in labels:
        for line in path.read_text().splitlines():
            values=list(map(float,line.split()))
            assert len(values)==6 and values[0]==0
            assert all(0<=value<=1 for value in values[1:])
            boxes+=1
    result={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu CPU',
            'input_sequence':'TUD-Campus','raw_video_sha256':sha(source),
            'weights_sha256':sha(ROOT/'YOLOv5/yolov5s.pt'),
            'frames_processed':len(frames),'frames_with_person_labels':len(labels),'detected_person_boxes':boxes,
            'server_upload_enabled':False,'tracking_accuracy_measured':False,
            'detector_accuracy_measured':False,'pass':True,
            'source_sha256':{name:sha(ROOT/name) for name in ['tools/smoke_tracking_sample.py','tools/run_edge.py','YOLOv5/detect.py']}}
    (public/'detector-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
