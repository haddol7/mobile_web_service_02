"""Fetch one official ChokePoint sequence serially; retain original frames privately."""
from datetime import datetime,timezone
import hashlib,json,os,tarfile
from pathlib import Path
import requests
import cv2

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/private/cctv-walking/chokepoint'
FILES={'groundtruth.tar.xz':'5c9d4d38a1c614905fe48da48ecdf06c','P1E_S1.tar.xz':'195191772856c1a62650a1d47e897b2a'}

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    OUT.mkdir(parents=True,exist_ok=True);assets=[]
    for name,expected in FILES.items():
        target=OUT/name;url='https://zenodo.org/records/815657/files/'+name+'?download=1'
        if not target.exists():
            part=target.with_suffix('.part');size=0
            with requests.get(url,stream=True,timeout=(15,90)) as response:
                response.raise_for_status()
                with part.open('wb') as file:
                    for chunk in response.iter_content(1024*1024):
                        size+=len(chunk);assert size<430*1024**2;file.write(chunk)
            part.replace(target)
        assert hashlib.md5(target.read_bytes()).hexdigest()==expected,'Archive checksum mismatch'
        assets.append({'file':name,'url':url,'bytes':target.stat().st_size,'md5':expected})
        print(json.dumps({'downloaded':name,'bytes':target.stat().st_size}),flush=True)
    # No untrusted archive path is extracted. Copy bounded regular files under a fixed directory.
    with tarfile.open(OUT/'groundtruth.tar.xz') as bundle:
        for member in bundle:
            if member.isfile() and 'P1E_S1' in member.name and member.name.endswith('.xml'):
                assert member.size<4*1024**2
                (OUT/Path(member.name).name).write_bytes(bundle.extractfile(member).read())
    cameras={};previews=[]
    with tarfile.open(OUT/'P1E_S1.tar.xz') as bundle:
        for nested in bundle:
            camera=Path(nested.name).name.removesuffix('.tar.xz')
            if camera not in ('P1E_S1_C1','P1E_S1_C2') or not nested.isfile():continue
            folder=OUT/camera;folder.mkdir(exist_ok=True)
            with tarfile.open(fileobj=bundle.extractfile(nested),mode='r|xz') as images:
                for member in images:
                    if not member.isfile() or not member.name.lower().endswith('.jpg'):continue
                    assert member.size<2*1024**2
                    destination=folder/Path(member.name).name
                    if not destination.exists():destination.write_bytes(images.extractfile(member).read())
                    cameras[camera]=cameras.get(camera,0)+1
    for camera,count in cameras.items():
        frames=sorted((OUT/camera).glob('*.jpg'));assert len(frames)==count
        target=OUT/(camera+'.mp4');writer=cv2.VideoWriter(str(target),cv2.VideoWriter_fourcc(*'mp4v'),30,(800,600))
        assert writer.isOpened()
        for index,source in enumerate(frames):
            image=cv2.imread(str(source));assert image.shape[:2]==(600,800);writer.write(image)
            if index in (150,250,400):
                preview=OUT/(camera+f'-{index}.jpg');cv2.imwrite(str(preview),image);previews.append(str(preview.relative_to(ROOT)))
        writer.release()
        print(json.dumps({'sequence':camera,'frames':count,'size':[800,600],'path':str(target.relative_to(ROOT))}),flush=True)
    record={'collected_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu','assets':assets,'sequences':cameras,
            'previews':previews,'fps':30,'source':'https://arma.sourceforge.net/chokepoint/',
            'download':'https://zenodo.org/records/815657','license':'Research use with acknowledgement; see official ChokePoint licence',
            'attribution':'Wong, Chen, Mau, Sanderson, Lovell. CVPR Workshops 2011, doi:10.1109/CVPRW.2011.5981881',
            'capture_dates_known':False,'media_in_git':False,'pass':True}
    (OUT/'collection.json').write_text(json.dumps(record,indent=2)+'\n')
    (ROOT/'evidence/history/chokepoint-collection.json').write_text(json.dumps(record,indent=2)+'\n')

if __name__=='__main__':main()
