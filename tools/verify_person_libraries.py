"""Exercise the actual YOLOv5 hook on raw MOT video and cross-source face clips in WSL."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import cv2
import motmetrics as mm
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'evidence/private/person-libraries'
PUBLIC = ROOT / 'evidence/person-libraries'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_detector(source, name, *, faces=None):
    command = [sys.executable, str(ROOT/'tools/run_edge.py'), '--source', str(source),
               '--device','cpu','--classes','0','--person-tracking',
               '--project',str(PRIVATE),'--name',name]
    if faces:
        command += ['--face-references',str(faces),'--face-stride','1']
    else:
        command += ['--count-line','0.5','0','0.5','1']
    started = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=300)
    elapsed = time.perf_counter()-started
    (PRIVATE/(name+'.txt')).write_text(result.stdout+result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'YOLO library run failed; inspect local {name}.txt')
    output = PRIVATE/name
    logs = list((output/'person-analysis').glob('*.jsonl'))
    assert len(logs) == 1, 'Use a fresh output directory for each verification run'
    records = [json.loads(line) for line in logs[0].read_text().splitlines()]
    videos = list(output.glob('*.mp4'))
    assert len(videos) == 1
    return records, videos[0], elapsed


def inspect_output(path, expected):
    capture = cv2.VideoCapture(str(path))
    count=0; preview=None
    while True:
        ok,frame = capture.read()
        if not ok:break
        count+=1
        if count == max(1,expected//2):preview=frame
    capture.release()
    assert count == expected
    cv2.imwrite(str(path.with_suffix('.jpg')),preview)


def tracking_score(sequence, records):
    normalized = json.loads((ROOT/sequence['normalized_ground_truth']['path']).read_text())
    assert sha(ROOT/sequence['normalized_ground_truth']['path']) == sequence['normalized_ground_truth']['sha256']
    sx,sy = normalized['video_scale']
    truth = defaultdict(list)
    for frame,identity,x,y,w,h,visibility in normalized['rows']:
        truth[int(frame)].append((int(identity),[x*sx,y*sy,w*sx,h*sy]))
    accumulator = mm.MOTAccumulator(auto_id=True)
    for row in records:
        actual = truth[row['frame_index']]
        predictions = row['tracks']
        gt_boxes = np.array([box for _,box in actual]).reshape(-1,4)
        pred_boxes = np.array([[x1,y1,x2-x1,y2-y1] for x1,y1,x2,y2 in
                               [item['bbox'] for item in predictions]]).reshape(-1,4)
        distances = mm.distances.iou_matrix(gt_boxes,pred_boxes,max_iou=0.5)
        accumulator.update([identity for identity,_ in actual],
                           [item['track_id'] for item in predictions],distances)
    metrics=['idf1','num_switches','num_false_positives','num_misses','num_objects','num_predictions']
    values = mm.metrics.create().compute(accumulator,metrics=metrics).iloc[0].to_dict()
    return {key:(float(value) if key=='idf1' else int(value)) for key,value in values.items()}


def make_face_fixture():
    source = ROOT/'evidence/private/hf-video-candidates'
    verified = json.loads((source/'download-verification.json').read_text())
    groups = defaultdict(list)
    for item in verified['samples']:
        if 'VoxCeleb2' in item['dataset']:
            parts = Path(item['member']).parts
            path = source/'_'.join(parts[-3:])
            assert sha(path) == item['sha256']
            groups[parts[-3]].append((parts[-2],path))
    ids = sorted(groups)
    assert len(ids) >= 3
    folder = PRIVATE/'face-fixture'; folder.mkdir(parents=True,exist_ok=True)
    profiles=[]; queries=[]
    for index,identity in enumerate(ids[:3]):
        clips=sorted(groups[identity]); assert len(clips)>=2 and clips[0][0]!=clips[1][0]
        profile = f'reference-{index+1:03d}' if index<2 else None
        if profile:
            capture = cv2.VideoCapture(str(clips[0][1]))
            total=int(capture.get(cv2.CAP_PROP_FRAME_COUNT)); references=[]
            for j,frame_index in enumerate([0,total//2,total-1]):
                capture.set(cv2.CAP_PROP_POS_FRAMES,frame_index)
                ok,image=capture.read(); assert ok
                name=f'{profile}-{j}.jpg'; assert cv2.imwrite(str(folder/name),image)
                references.append(name)
            capture.release(); profiles.append({'id':profile,'images':references})
        original=clips[1][1]
        opaque=hashlib.sha256(original.read_bytes()).hexdigest()[:20]
        target=folder/(opaque+'.mp4')
        capture=cv2.VideoCapture(str(original)); total=int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        sampled=np.linspace(0,total-1,7,dtype=int).tolist(); writer=None
        for frame_index in sampled:
            capture.set(cv2.CAP_PROP_POS_FRAMES,frame_index)
            ok,image=capture.read(); assert ok
            if writer is None:
                writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*'mp4v'),7,
                                       (image.shape[1],image.shape[0])); assert writer.isOpened()
            writer.write(image)
        capture.release(); writer.release()
        queries.append({'path':target,'expected':profile,'source_video_id':clips[1][0],
                        'source_frame_indices':sampled,'registered_video_id':clips[0][0] if profile else None})
    manifest=folder/'references.json'
    manifest.write_text(json.dumps({'schema_version':1,'profiles':profiles},indent=2)+'\n')
    (folder/'oracle.json').write_text(json.dumps([{**item,'path':str(item['path'])} for item in queries],indent=2)+'\n')
    return manifest,queries


def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run this integration test in WSL.')
    PRIVATE.mkdir(parents=True,exist_ok=True); PUBLIC.mkdir(parents=True,exist_ok=True)
    # Fresh folders prevent append-only outputs from earlier runs contaminating this evidence.
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    collection=json.loads((ROOT/'evidence/tracking-samples/collection.json').read_text())
    tracking=[]
    for name in ['TUD-Campus','TUD-Stadtmitte']:
        sequence=next(item for item in collection['sequences'] if item['id']==name)
        source=ROOT/sequence['video']['path']; assert sha(source)==sequence['video']['sha256']
        records,video,elapsed=run_detector(source,stamp+'-'+name)
        assert [row['frame_index'] for row in records]==list(range(1,sequence['decoded_frames']+1))
        inspect_output(video,len(records))
        result={'sequence':name,'split':sequence['split'],'frames':len(records),
                'frames_with_tracks':sum(bool(row['tracks']) for row in records),
                'track_ids':len({item['track_id'] for row in records for item in row['tracks']}),
                'line_crossings':sum(len(row['crossings']) for row in records),
                'elapsed_seconds_including_startup':elapsed,
                'diagnostic_iou_0_5':tracking_score(sequence,records),
                'official_mot_leaderboard_score':False,
                'passage_accuracy_measured':False,'output_video_fully_decoded':True}
        tracking.append(result); print(json.dumps(result),flush=True)
    manifest,queries=make_face_fixture(); face_runs=[]
    for i,query in enumerate(queries):
        records,video,elapsed=run_detector(query['path'],stamp+f'-face-{i}',faces=manifest)
        assert len(records)==7; inspect_output(video,7)
        eligible=[face for row in records for face in row['faces']]
        accepted=[face for face in eligible if face['candidate_profile_id'] is not None]
        correct=[face for face in accepted if query['expected'] is not None
                 and face['candidate_profile_id']==query['expected']]
        wrong=[face for face in accepted if face not in correct]
        face_runs.append({'registered':query['expected'] is not None,'sampled_frames':7,
            'detected_faces':len(eligible),'accepted_candidates':len(accepted),
            'correct_candidates':len(correct),'wrong_candidates':len(wrong),
            'unresolved':len(eligible)-len(accepted),
            'frames_with_yolo_person_tracks':sum(bool(row['tracks']) for row in records),
            'faces_associated_to_one_yolo_track':sum(face['body_track_id'] is not None for face in eligible),
            'minimum_similarity':min((face['similarity'] for face in eligible),default=None),
            'maximum_similarity':max((face['similarity'] for face in eligible),default=None),
            'elapsed_seconds_including_startup':elapsed})
        print(json.dumps(face_runs[-1]),flush=True)
    smoke=all(row['detected_faces']>0 and row['wrong_candidates']==0
              and (not row['registered'] or row['correct_candidates']>0) for row in face_runs)
    result={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu CPU',
        'libraries':['norfair==2.3.0','supervision==0.31.5','insightface==2.1','motmetrics==1.4.0'],
        'weights_sha256':sha(ROOT/'YOLOv5/yolov5s.pt'),'tracking':tracking,'face_smoke':face_runs,
        'face_smoke_matches_expected':smoke,'face_threshold':0.55,'face_margin':0.08,
        'face_detection_mode':'InsightFace 2.1 Auto: 128 and 640 inputs',
        'face_sample_protocol':'2 registered labels, 1 unknown label; 7 frames per query from a different source video ID; exploratory smoke only',
        'independent_face_query_clips':3,'statistical_face_accuracy_established':False,
        'automatic_identity_confirmation_enabled':False,'model_training_performed':False,
        'django_upload_enabled':False,'production_verified':False,'pipeline_executed':True,
        'source_sha256':{name:sha(ROOT/name) for name in [
            'YOLOv5/detect.py','YOLOv5/person_tracking.py','tools/verify_person_libraries.py']}}
    (PUBLIC/'integration.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
