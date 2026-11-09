"""Make QA panels from actual detector records, separate from all inference input."""
import json
import os
from pathlib import Path

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence/private/cctv-walking/expanded"


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    panels=[]
    evidence=[]
    for path in sorted(OUT.glob("*/inference.json")):
        result=json.loads(path.read_text())
        info=json.loads((path.parent/"collection.json").read_text())
        rows=[json.loads(line) for line in (ROOT/result["log"]).read_text().splitlines()]
        candidates=[(row,face) for row in rows for face in row["faces"]
                    if face["body_track_id"] is not None and not face["candidate_profile_id"]]
        assert candidates
        row,face=max(candidates,key=lambda pair:(pair[1]["bbox"][2]-pair[1]["bbox"][0])*(pair[1]["bbox"][3]-pair[1]["bbox"][1])*pair[1].get("detection_score",1))
        original_index=round(row["video_seconds"]*info["fps"])
        name=info["images"][original_index]
        source=cv2.imread(str(path.parent/"images"/name))
        assert source is not None
        for track in row["tracks"]:
            x1,y1,x2,y2=map(round,track["bbox"])
            cv2.rectangle(source,(x1,y1),(x2,y2),(90,175,60),2)
        for detected in row["faces"]:
            x1,y1,x2,y2=map(round,detected["bbox"])
            cv2.rectangle(source,(x1,y1),(x2,y2),(20,145,235),2)
        panel=np.full((332,400,3),248,np.uint8)
        panel[:300]=cv2.resize(source,(400,300))
        cv2.putText(panel,f'{result["camera"]} / original {name}',(9,321),cv2.FONT_HERSHEY_SIMPLEX,.43,(35,55,65),1)
        panels.append(panel)
        evidence.append({"camera":result["camera"],"analyzed_frame_index":row["frame_index"],
                         "replay_seconds":row["video_seconds"],"original_image":name,"face_linked_to_body":True,
                         "identity_confirmed":False,"input_used_for_inference":False})
    assert len(panels)==4
    image=np.vstack([np.hstack(panels[:2]),np.hstack(panels[2:])])
    assert cv2.imwrite(str(OUT/"source-review.jpg"),image)
    result={"pass":True,"panels":evidence,"purpose":"visual QA of real model boxes; not an accuracy benchmark",
            "path":(OUT/"source-review.jpg").relative_to(ROOT).as_posix()}
    (ROOT/"evidence/history/chokepoint-expanded-source-review.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result),flush=True)


if __name__=="__main__":
    main()
