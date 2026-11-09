"""Run genuine Trump and Obama clips against a shared five-profile gallery."""
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
from pathlib import Path
import cv2

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-demo'

def clip(source,target,start,seconds):
    capture=cv2.VideoCapture(str(source));fps=capture.get(cv2.CAP_PROP_FPS)
    capture.set(cv2.CAP_PROP_POS_FRAMES,round(start*fps));ok,image=capture.read();assert ok
    writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*'mp4v'),fps,(image.shape[1],image.shape[0]));assert writer.isOpened()
    count=0
    while ok and count<round(seconds*fps):
        writer.write(image);count+=1;ok,image=capture.read()
    writer.release();capture.release();assert count==round(seconds*fps)
    return count

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    sources=json.loads((OUT/'dvids-collection.json').read_text());base=ROOT/'evidence/private/hf-video-candidates'
    verified=json.loads((base/'download-verification.json').read_text())
    for name in ('BarackObama_001.mp4','BarackObama_044.mp4'):
        expected=next(row for row in verified['samples'] if row.get('member','').endswith('/'+name))
        assert hashlib.sha256((base/name).read_bytes()).hexdigest()==expected['sha256']
    for source in sources['clips']:assert hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest()==source['sha256']
    old=ROOT/'evidence/private/monitoring-showcase/v2/references.json';gallery=json.loads(old.read_text())['profiles']
    profiles=[{**p,'images':[str(old.parent/name) for name in p['images']]} for p in gallery]
    new=[{'id':'public-trump','name':'도널드 트럼프','source':OUT/'trump-ball.mp4','seconds':[1,3,5]},
         {'id':'public-obama','name':'버락 오바마','source':base/'BarackObama_001.mp4','seconds':[0,4.96,9.88]}]
    sys.path.insert(0,str(ROOT/'YOLOv5'));from person_tracking import create_face_app
    from face_features import reference_face
    app=create_face_app()
    for profile in new:
        images=[];capture=cv2.VideoCapture(str(profile['source']))
        for at,second in enumerate(profile['seconds']):
            capture.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,image=capture.read();assert ok
            face=reference_face(app.get(image),image.shape);assert face is not None
            name=profile['id']+f'-reference-{at}.jpg';assert cv2.imwrite(str(OUT/name),image);images.append(name)
            if at==1:
                x1,y1,x2,y2=face.bbox;pad=(x2-x1)*.2
                portrait=image[max(0,int(y1-pad)):min(image.shape[0],int(y2+pad)),max(0,int(x1-pad)):min(image.shape[1],int(x2+pad))]
                assert cv2.imwrite(str(OUT/(profile['id']+'-portrait.jpg')),portrait)
        capture.release();profiles.append({'id':profile['id'],'name':profile['name'],'images':images})
    manifest=OUT/'references.json';manifest.write_text(json.dumps({'schema_version':1,'profiles':profiles},ensure_ascii=False,indent=2)+'\n')
    cases=[{'case':'trump-speech','name':'트럼프 / 공개 연설','expected':'public-trump','source':OUT/'trump-ball.mp4','start':8,'seconds':9,
            'source_reference':'DVIDS/506134','source_url':sources['clips'][0]['page']},
           {'case':'trump-airbase-walk','name':'트럼프 / 공군기지 이동','expected':'public-trump','source':OUT/'trump-arrival.mp4','start':228,'seconds':12,
            'source_reference':'DVIDS/512302','source_url':sources['clips'][1]['page']},
           {'case':'obama-clip44','name':'오바마 / 공개 연설 구간 44','expected':'public-obama','source':base/'BarackObama_044.mp4','start':0,'seconds':9,
            'source_reference':'HDTF/WDA_BarackObama','source_url':'https://huggingface.co/datasets/saeed-5959/hdtf'},
           {'case':'obama-independent-recording','name':'오바마 / 별도 공개 영상','expected':'public-obama','source':OUT/'obama-address.mp4','start':10,'seconds':12,
            'source_reference':'DVIDS/358042','source_url':'https://www.dvidshub.net/video/358042/president-obama-remarks-ebola-outbreak'}]
    for case in cases:
        target=OUT/(case['case']+'.mp4')
        assert target!=case['source'],'The derived clip must not overwrite a source file'
        count=clip(case['source'],target,case['start'],case['seconds']) if not target.exists() else int(cv2.VideoCapture(str(target)).get(cv2.CAP_PROP_FRAME_COUNT))
        case['source_path']=str(case.pop('source').relative_to(ROOT));case['path']=str(target.relative_to(ROOT));case['sha256']=hashlib.sha256(target.read_bytes()).hexdigest();case['clip_frames']=count
        stride=3 if case['case'] in ('trump-speech','obama-independent-recording') else 6
        case['sampling_stride']=stride
        folder=OUT/case['case'];logs=list(folder.glob('person-analysis/*.jsonl'))
        if not logs:
            command=[sys.executable,str(ROOT/'tools/run_edge.py'),'--source',str(target),'--device','cpu','--classes','0','--person-tracking',
                     '--face-references',str(manifest),'--face-stride','1','--vid-stride',str(stride),'--project',str(OUT),'--name',case['case'],'--exist-ok','--nosave']
            environment={**os.environ,'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=480,env=environment)
            (OUT/(case['case']+'.log')).write_text(result.stdout+result.stderr);assert result.returncode==0,'Inspect private inference log'
            logs=list(folder.glob('person-analysis/*.jsonl'))
        assert len(logs)==1;rows=[json.loads(line) for line in logs[0].read_text().splitlines()]
        assert len(rows)==count//stride,'Incomplete inference log'
        faces=[f for r in rows for f in r['faces']]
        case.update(log=str(logs[0].relative_to(ROOT)),frames_analyzed=len(rows),face_detections=len(faces),
                    expected_linked_candidates=sum(f['body_track_id'] is not None and f['candidate_profile_id']==case['expected'] for f in faces),
                    other_profile_candidates=sum(f['candidate_profile_id'] is not None and f['candidate_profile_id']!=case['expected'] for f in faces))
        print(json.dumps({key:case[key] for key in ('case','frames_analyzed','face_detections','expected_linked_candidates','other_profile_candidates')}),flush=True)
        assert case['expected_linked_candidates']>0,'No actual body-associated match: '+case['case']
    record={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu CPU','profiles':profiles,'cases':cases,
            'capture_times_known':False,'obama_hdtf_clips_may_share_original_recording':True,'automatic_confirmation':False,'training_performed':False,'pass':True}
    (OUT/'inference.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    public={**record,'profiles':[{k:p[k] for k in ('id','name')} for p in profiles],'cases':cases}
    (ROOT/'evidence/history/public-figure-inference.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
