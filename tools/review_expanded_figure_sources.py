"""Build a labeled QA contact sheet from genuine source pixels and detector boxes."""
import json,os
from pathlib import Path
import cv2,numpy as np

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-expanded'
assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
scans=json.loads((OUT/'scans.json').read_text());panels=[]
for item in sorted(scans.values(),key=lambda r:(r['person'],r['capture_day_as_published'])):
    picture=cv2.imread(str(ROOT/item['preview']));assert picture is not None
    panel=np.full((236,460,3),245,np.uint8);panel[:180,:320]=cv2.resize(picture,(320,180))
    matches=[face for sample in item['samples'] for face in sample['target_hits']]
    face=max(matches,key=lambda f:f['similarity']);x1,y1,x2,y2=map(int,face['bbox']);pad=round((x2-x1)*.15)
    crop=picture[max(0,y1-pad):min(picture.shape[0],y2+pad),max(0,x1-pad):min(picture.shape[1],x2+pad)];assert crop.size
    panel[22:150,326:454]=cv2.resize(crop,(128,128))
    name='Trump' if item['person']=='public-trump' else 'Obama'
    cv2.putText(panel,f'{name} / {item["capture_day_as_published"]} / {item["source_id"]}',(7,201),cv2.FONT_HERSHEY_SIMPLEX,.48,(25,45,55),1)
    cv2.putText(panel,f'Face candidate {item["source_face_score"]:.2f}; genuine DVIDS source',(7,222),cv2.FONT_HERSHEY_SIMPLEX,.43,(50,65,75),1)
    panels.append(panel)
assert len(panels)==16
sheet=np.vstack([np.hstack(panels[n:n+4]) for n in range(0,16,4)])
assert cv2.imwrite(str(OUT/'source-review.jpg'),sheet)
print(json.dumps({'pass':True,'source_panels':len(panels),'path':str((OUT/'source-review.jpg').relative_to(ROOT))}))
