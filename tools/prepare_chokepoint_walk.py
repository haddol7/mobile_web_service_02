"""Prepare real near-frontal portal footage, then run the existing edge pipeline."""
from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys,tarfile
from pathlib import Path
import cv2

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/cctv-walking/chokepoint'

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    archive=OUT/'P1E_S1.tar.xz'
    if not archive.exists():archive=OUT/'P1E_S1.tar.part'
    # First camera is a complete nested archive even while later cameras are downloading.
    nested=OUT/'P1E_S1_C1.tar.xz'
    if not nested.exists():
        with tarfile.open(archive,mode='r|xz') as bundle:
            member=next(iter(bundle));assert member.name=='P1E_S1_C1.tar.xz'
            raw=bundle.extractfile(member).read();assert len(raw)==member.size
            nested.write_bytes(raw)
    folder=OUT/'P1E_S1_C1';folder.mkdir(exist_ok=True)
    with tarfile.open(nested) as bundle:
        for member in bundle:
            if member.isfile() and member.name.endswith('.jpg'):
                assert member.size<2*1024**2
                path=folder/Path(member.name).name
                if not path.exists():path.write_bytes(bundle.extractfile(member).read())
    with tarfile.open(OUT/'groundtruth.tar.xz') as bundle:
        for member in bundle:
            if member.isfile() and member.name.endswith('P1E_S1_C1.xml'):
                (OUT/'P1E_S1_C1.xml').write_bytes(bundle.extractfile(member).read())
    frames=sorted(folder.glob('*.jpg'));assert len(frames)>1200
    target=OUT/'P1E_S1_C1-first1200.mp4'
    if not target.exists():
        writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*'mp4v'),30,(800,600));assert writer.isOpened()
        for index,source in enumerate(frames[:1200]):
            image=cv2.imread(str(source));assert image.shape[:2]==(600,800);writer.write(image)
            if index in (150,250,400,600,800,1050):cv2.imwrite(str(OUT/f'walking-{index}.jpg'),image)
        writer.release()
    reference=ROOT/'evidence/private/monitoring-showcase/v2/references.json'
    logs=list((OUT/'inference').glob('person-analysis/*.jsonl'))
    if not logs:
        command=[sys.executable,str(ROOT/'tools/run_edge.py'),'--source',str(target),'--device','cpu','--classes','0',
                 '--person-tracking','--face-references',str(reference),'--face-stride','1','--vid-stride','10',
                 '--project',str(OUT),'--name','inference','--exist-ok','--nosave']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=480)
        (OUT/'inference.log').write_text(result.stdout+result.stderr)
        assert result.returncode==0,'Inspect private inference log'
        logs=list((OUT/'inference').glob('person-analysis/*.jsonl'))
    assert len(logs)==1
    rows=[json.loads(line) for line in logs[0].read_text().splitlines()]
    faces=[f for row in rows for f in row['faces']]
    record={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu CPU','source':'ChokePoint/P1E_S1_C1',
            'path':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'original_frames_available':len(frames),'clip_original_start_index':0,'clip_original_frames':1200,
            'fps':30,'size':[800,600],'frames_analyzed':len(rows),'faces_detected':len(faces),
            'linked_faces':sum(f['body_track_id'] is not None for f in faces),'candidates':sum(bool(f['candidate_profile_id']) for f in faces),
            'log':str(logs[0].relative_to(ROOT)),'capture_date_known':False,'automatic_confirmation':False,
            'outer_archive_checksum_verified':(OUT/'P1E_S1.tar.xz').exists(),'model_training_performed':False,'pass':True}
    (OUT/'inference.json').write_text(json.dumps(record,indent=2)+'\n')
    (ROOT/'evidence/history/chokepoint-inference.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)

if __name__=='__main__':main()
