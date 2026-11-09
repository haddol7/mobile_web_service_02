"""Find genuine named-face intervals, then validate the existing edge pipeline in batch."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
from pathlib import Path
import cv2

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-expanded'
GALLERY=ROOT/'evidence/private/public-figure-demo/references.json'
LABELS={'563342':'일본 출국','508029':'취임 선서 행사','742724':'대국민 연설','733563':'백악관 브리핑','632165':'정부 회의',
        '526302':'이스라엘 회담','628029':'서명 행사','759368':'현장 브리핑','493194':'백악관 발언','287224':'보스턴 방문',
        '362956':'보건안보 회의','456872':'핵안보 정상회의','413783':'국방부 기자회견','324601':'브뤼셀 연설','391729':'국제회의 발언','359270':'나토 기자회견'}

def write(path,data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)

def scan():
    collection=json.loads((OUT/'collection.json').read_text())
    prior=json.loads((OUT/'scans.json').read_text()) if (OUT/'scans.json').exists() else {}
    gallery_sha=hashlib.sha256(GALLERY.read_bytes()).hexdigest()
    sys.path.insert(0,str(ROOT/'YOLOv5'));from person_tracking import FaceReferences
    sys.path.insert(0,str(ROOT));from tools.prepare_public_figure_demo import clip
    gallery=FaceReferences(GALLERY);assert gallery.registration['profiles']==5 and not gallery.rejected_references
    (OUT/'clips').mkdir(exist_ok=True)
    for item in collection['clips']:
        key=item['source_id'];previous=prior.get(key)
        if previous:
            assert previous['original_sha256']==item['sha256'] and previous['gallery_sha256']==gallery_sha
            if previous.get('source_face_score',0)>=.5:continue
        capture=cv2.VideoCapture(str(ROOT/item['path']));length=item['seconds'];samples=[];best=None
        times=[5,15,30,60,120,*[length*f for f in (.1,.25,.5,.75,.9)]]
        for second in dict.fromkeys(round(min(max(0,t),max(0,length-4)),2) for t in times):
            capture.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,image=capture.read();assert ok
            faces=gallery.analyze(image);hits=[f for f in faces if f['candidate_profile_id']==item['person']]
            samples.append({'source_seconds':second,'face_count':len(faces),'target_hits':hits})
            if hits:
                score=max(f['similarity'] for f in hits)
                if best is None or score>best['score']:best={'second':second,'score':score,'image':image.copy()}
                if score>=.5:break
        if best is None or best['score']<.5:
            for second in range(10,min(int(length),1200),20):
                if any(abs(second-s['source_seconds'])<3 for s in samples):continue
                capture.set(cv2.CAP_PROP_POS_MSEC,second*1000);ok,image=capture.read();assert ok
                faces=gallery.analyze(image);hits=[f for f in faces if f['candidate_profile_id']==item['person']]
                samples.append({'source_seconds':second,'face_count':len(faces),'target_hits':hits})
                if hits:
                    score=max(f['similarity'] for f in hits)
                    if best is None or score>best['score']:best={'second':second,'score':score,'image':image.copy()}
                    if score>=.5:break
        capture.release()
        result={'source_id':key,'original_sha256':item['sha256'],'gallery_sha256':gallery_sha,'samples':samples,'candidate_located':best is not None}
        if best:
            start=max(0,min(best['second']-2,max(0,length-8)));seconds=min(8,length-start)
            target=OUT/'clips'/(key+'.mp4');count=clip(ROOT/item['path'],target,start,seconds)
            preview=OUT/(key+'-located.jpg');cv2.imwrite(str(preview),best['image'])
            alias='트럼프' if item['person']=='public-trump' else '오바마'
            result.update(person=item['person'],name=f'{alias} / {item["capture_day_as_published"]} {LABELS.get(key,"공개 영상")}',
                          source_reference=item['source_reference'],source_url=item['source_url'],capture_day_as_published=item['capture_day_as_published'],
                          path=str(target.relative_to(ROOT)),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),clip_frames=count,
                          original_start_seconds=start,clip_seconds=seconds,source_face_score=best['score'],preview=str(preview.relative_to(ROOT)))
        prior[key]=result;write(OUT/'scans.json',prior)
        print(json.dumps({'source':key,'candidate_located':best is not None,'samples':len(samples),'score':best['score'] if best else None}),flush=True)

def infer():
    collection=json.loads((OUT/'collection.json').read_text());assert collection['pass']
    scans=json.loads((OUT/'scans.json').read_text());assert len(scans)==len(collection['clips']) and all(v['candidate_located'] for v in scans.values())
    folder=OUT/'batch-inference';ready=folder/'completed.json'
    sources={r['source_id']:r['sha256'] for r in scans.values()}
    if ready.exists():assert json.loads(ready.read_text())==sources
    else:
        assert not list(folder.glob('person-analysis/*.jsonl')),'Inspect interrupted inference before retrying'
        command=[sys.executable,str(ROOT/'tools/run_edge.py'),'--source',str(OUT/'clips'),'--device','cpu','--classes','0','--person-tracking',
                 '--face-references',str(GALLERY),'--face-stride','1','--vid-stride','12','--project',str(OUT),'--name','batch-inference','--exist-ok','--nosave']
        environment={**os.environ,'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=1200,env=environment)
        (OUT/'batch-inference.log').write_text(result.stdout+result.stderr);assert result.returncode==0,'Inspect private inference log'
        write(ready,sources)
    cases=[]
    for item in scans.values():
        key=hashlib.sha256(('0:'+str(ROOT/item['path'])).encode()).hexdigest()[:16]
        log=folder/'person-analysis'/(key+'.jsonl');rows=[json.loads(line) for line in log.read_text().splitlines()]
        assert len(rows)==item['clip_frames']//12,'Incomplete sampled inference'
        def valid(row):
            owners=Counter(f['body_track_id'] for f in row['faces'] if f['body_track_id'] is not None)
            return any(f['body_track_id'] is not None and owners[f['body_track_id']]==1 and f['candidate_profile_id']==item['person'] for f in row['faces'])
        good=[r for r in rows if valid(r)];assert len(good)>=3,'Insufficient usable candidate rows: '+item['source_id']
        cases.append({**item,'case':'dvids-'+item['source_id'],'expected':item['person'],'log':str(log.relative_to(ROOT)),
                      'frames_analyzed':len(rows),'usable_candidate_frames':len(good),
                      'other_profile_candidates':sum(f['candidate_profile_id'] not in (None,item['person']) for row in rows for f in row['faces'])})
    result={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu CPU','cases':cases,
            'gallery_sha256':hashlib.sha256(GALLERY.read_bytes()).hexdigest(),'profiles':json.loads(GALLERY.read_text())['profiles'],
            'automatic_confirmation':False,'sampling_stride':12,'training_performed':False,'pass':True}
    write(OUT/'inference.json',result)
    public={**result,'profiles':[{k:p[k] for k in ('id','name')} for p in result['profiles']]}
    write(ROOT/'evidence/history/public-figure-expanded-inference.json',public)
    print(json.dumps({'pass':True,'sources':len(cases),'frames_analyzed':sum(c['frames_analyzed'] for c in cases),'usable_candidate_frames':sum(c['usable_candidate_frames'] for c in cases)}),flush=True)

if __name__=='__main__':
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['scan','infer']);args=parser.parse_args()
    scan() if args.phase=='scan' else infer()
