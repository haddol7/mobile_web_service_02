"""Inspect every official enrollment portrait before publishing the registry."""
import hashlib,json,os
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence/private/cctv-walking/people"


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    enrollment=json.loads((OUT/"enrollment.json").read_text())
    panels=[]
    for profile in enrollment["new_profiles"]:
        tile=np.full((150,232,3),250,np.uint8)
        assert len(profile["images"])==2
        for index,path in enumerate(profile["images"]):
            photo=cv2.imread(path);assert photo is not None
            assert Path(path).name.startswith(profile["dataset_identity"]+"-")
            scale=min(110/photo.shape[1],118/photo.shape[0])
            photo=cv2.resize(photo,(round(photo.shape[1]*scale),round(photo.shape[0]*scale)))
            left=index*116+(110-photo.shape[1])//2;top=(120-photo.shape[0])//2
            tile[top:top+photo.shape[0],left:left+photo.shape[1]]=photo
        cv2.putText(tile,'ChokePoint '+profile["dataset_identity"],(8,141),cv2.FONT_HERSHEY_SIMPLEX,.5,(30,45,55),1)
        panels.append(tile)
    while len(panels)%5:panels.append(np.full_like(panels[0],250))
    image=np.vstack([np.hstack(panels[start:start+5]) for start in range(0,len(panels),5)])
    path=OUT/"enrollment-review.jpg";assert cv2.imwrite(str(path),image)
    proof={"pass":True,"profiles":len(enrollment["new_profiles"]),"stills":sum(len(p["images"]) for p in enrollment["new_profiles"]),
           "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"path":path.relative_to(ROOT).as_posix(),
           "purpose":"All enrollment portrait pairs with official source subject IDs; not query input"}
    (ROOT/"evidence/history/chokepoint-people-enrollment-review.json").write_text(json.dumps(proof,indent=2)+"\n")
    print(json.dumps(proof),flush=True)


if __name__=="__main__":main()
