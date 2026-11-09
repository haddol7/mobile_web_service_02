"""Real YOLO/face inference for three repeat identities and two unenrolled identities."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import cv2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/private/monitoring-showcase/v2"


def main():
    assert os.environ.get("WSL_DISTRO_NAME"), "Use WSL"
    OUT.mkdir(parents=True, exist_ok=True)
    collection = json.loads((ROOT / "evidence/private/face-improvement/holdout/collection.json").read_text())
    enrolled = collection["enrolled_identities"][:3]
    unknown = collection["unknown_identities"][:2]
    profiles = []; cases = []
    for number, identity in enumerate(enrolled):
        alias = chr(65+number); key = "showcase-v2-"+alias.lower()
        reference = next(c for c in collection["clips"] if c["identity"]==identity and c["role"]=="reference")
        source = ROOT/reference["path"]; assert hashlib.sha256(source.read_bytes()).hexdigest()==reference["sha256"]
        capture = cv2.VideoCapture(str(source)); images=[]
        for index in (0, reference["decode"]["frames"]//2, reference["decode"]["frames"]-1):
            capture.set(cv2.CAP_PROP_POS_FRAMES,index); ok, frame=capture.read(); assert ok
            name=f"reference-{alias}-{index}.jpg"; assert cv2.imwrite(str(OUT/name),frame); images.append(name)
        capture.release()
        profiles.append({"id":key,"name":"인물 "+alias,"images":images})
        queries=[c for c in collection["clips"] if c["identity"]==identity and c["role"]=="query"][:2]
        assert len({c["source_video_id"] for c in [reference,*queries]})==3
        for at, clip in enumerate(queries,1):
            cases.append({"case":f"{alias}-{at}","name":f"인물 {alias} / 영상 {at}","expected":key,
                          "identity":identity,"reference_source_video_id":reference["source_video_id"],**clip})
    for at, identity in enumerate(unknown,1):
        clip=next(c for c in collection["clips"] if c["identity"]==identity and c["role"]=="query")
        cases.append({"case":f"unknown-{at}","name":f"미등록 인물 / 영상 {at}","expected":None,**clip})
    manifest=OUT/"references.json";manifest.write_text(json.dumps({"schema_version":1,"profiles":profiles},ensure_ascii=False,indent=2))
    for case in cases:
        source=ROOT/case["path"];assert hashlib.sha256(source.read_bytes()).hexdigest()==case["sha256"]
        folder=OUT/case["case"];logs=list(folder.glob("person-analysis/*.jsonl"))
        if not logs:
            command=[sys.executable,str(ROOT/"tools/run_edge.py"),"--source",str(source),"--device","cpu",
                     "--classes","0","--person-tracking","--face-references",str(manifest),"--face-stride","1",
                     "--vid-stride","4","--project",str(OUT),"--name",case["case"],"--exist-ok","--nosave"]
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=300)
            (OUT/(case["case"]+".log")).write_text(result.stdout+result.stderr)
            assert result.returncode==0, "Inspect private inference log: "+case["case"]
            logs=list(folder.glob("person-analysis/*.jsonl"))
        assert len(logs)==1
        rows=[json.loads(line) for line in logs[0].read_text().splitlines()]
        faces=[f for row in rows for f in row["faces"]]
        bound=[f for f in faces if f["body_track_id"] is not None]
        candidates={f["candidate_profile_id"] for f in faces if f["candidate_profile_id"]}
        assert not candidates-{case["expected"]}, "Wrong face candidate in real inference"
        if case["expected"]:
            assert any(f["candidate_profile_id"]==case["expected"] for f in bound), "No body-associated repeat identity: "+case["case"]
        case.update(log=str(logs[0].relative_to(ROOT)),frames_analyzed=len(rows),face_detections=len(faces),
                    linked_face_detections=len(bound),correct_candidates=sum(f["candidate_profile_id"]==case["expected"] and bool(case["expected"]) for f in faces))
        print(json.dumps({key:case[key] for key in ("case","frames_analyzed","face_detections","linked_face_detections","correct_candidates")}),flush=True)
        (OUT/"collection.json").write_text(json.dumps({"profiles":profiles,"cases":cases},ensure_ascii=False,indent=2))
    record={"verified_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu CPU",
            "identities_enrolled":3,"unenrolled_identities":2,"original_query_video_ids":len({c["source_video_id"] for c in cases}),
            "frames_analyzed":sum(c["frames_analyzed"] for c in cases),"all_enrolled_reappeared_in_two_different_source_videos":True,
            "capture_dates_known":False,"source_media_redistributed_in_repository":False,"model_training_performed":False,
            "automatic_identity_confirmation":False,"cases":[{k:c[k] for k in ("case","source_video_id","expected","frames_analyzed","face_detections","linked_face_detections","correct_candidates")} for c in cases],"pass":True}
    (ROOT/"evidence/history/showcase-inference.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__": main()
