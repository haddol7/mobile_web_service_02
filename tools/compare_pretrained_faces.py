"""Compare the larger existing face model at unchanged thresholds on the same exploratory fixture."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from verify_person_libraries import ROOT, PRIVATE, PUBLIC, make_face_fixture, inspect_output


def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run this model comparison in WSL.')
    previous=json.loads((PUBLIC/'integration.json').read_text())
    manifest,queries=make_face_fixture()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    runs=[]
    for index,query in enumerate(queries):
        name=stamp+f'-large-face-{index}'
        command=[sys.executable,str(ROOT/'tools/run_edge.py'),'--source',str(query['path']),
            '--device','cpu','--classes','0','--person-tracking','--face-references',str(manifest),
            '--face-stride','1','--face-model','buffalo_l','--project',str(PRIVATE),'--name',name]
        run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=180)
        (PRIVATE/(name+'.txt')).write_text(run.stdout+run.stderr,encoding='utf-8')
        assert run.returncode==0,f'Face comparison failed; inspect {name}.txt'
        output=PRIVATE/name
        logs=list((output/'person-analysis').glob('*.jsonl'));assert len(logs)==1
        records=[json.loads(line) for line in logs[0].read_text().splitlines()];assert len(records)==7
        videos=list(output.glob('*.mp4'));assert len(videos)==1;inspect_output(videos[0],7)
        faces=[face for row in records for face in row['faces']]
        accepted=[face for face in faces if face['candidate_profile_id'] is not None]
        correct=[face for face in accepted if query['expected'] is not None and face['candidate_profile_id']==query['expected']]
        result={'registered':query['expected'] is not None,'sampled_frames':7,'detected_faces':len(faces),
            'accepted_candidates':len(accepted),'correct_candidates':len(correct),
            'wrong_candidates':len(accepted)-len(correct),'unresolved':len(faces)-len(accepted),
            'minimum_similarity':min((face['similarity'] for face in faces),default=None),
            'maximum_similarity':max((face['similarity'] for face in faces),default=None),
            'faces_associated_to_one_yolo_track':sum(face['body_track_id'] is not None for face in faces)}
        runs.append(result);print(json.dumps(result),flush=True)
    passed=all(row['detected_faces']>0 and row['wrong_candidates']==0
               and (not row['registered'] or row['correct_candidates']>0) for row in runs)
    result={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu CPU',
        'models':{'buffalo_s':previous['face_smoke'],'buffalo_l':runs},
        'same_reference_images_and_query_samples':True,'threshold_unchanged':0.55,'margin_unchanged':0.08,
        'face_detection_mode':'InsightFace 2.1 Auto: 128 and 640 inputs',
        'buffalo_l_exploratory_smoke_matches_expected':passed,
        'independent_query_clips':3,'statistical_accuracy_established':False,
        'used_for_model_selection_not_final_holdout':True,'training_performed':False,
        'automatic_confirmation_enabled':False,'production_verified':False,
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ['YOLOv5/person_tracking.py','YOLOv5/detect.py','tools/compare_pretrained_faces.py']}}
    (PUBLIC/'face-model-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
