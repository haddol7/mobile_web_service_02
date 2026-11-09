"""Enroll official still identities, then run new, separately labeled video analyses."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid5,NAMESPACE_URL
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from chokepoint_identity import ground_truth_identity,dataset_track_identity
from expand_chokepoint_walk import file_hash

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence/private/cctv-walking/people"
sys.path.insert(0,str(ROOT/"YOLOv5"))
from person_tracking import create_face_app
from face_features import reference_face


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def stamp():return datetime.now(timezone.utc).isoformat()


def specs():
    base=ROOT/"evidence/private/cctv-walking/chokepoint"
    info=json.loads((base/"inference.json").read_text())
    original=json.loads((ROOT/"evidence/history/cctv-walking-cloud.json").read_text())
    rows=[{"camera":"P1E_S1_C1","video":info["path"],"video_sha256":info["sha256"],
           "source_images":str((base/"P1E_S1_C1").relative_to(ROOT)),"groundtruth":str((base/"P1E_S1_C1.xml").relative_to(ROOT)),
           "label":"출입 통로 / 정면 보행 / 인물 등록 후 분석",
           "source_reference":"ChokePoint/P1E_S1_C1/first1200-available-frames"}]
    from expand_chokepoint_walk import CASES
    for case in CASES:
        folder=ROOT/"evidence/private/cctv-walking/expanded"/case["camera"]
        info=json.loads((folder/"collection.json").read_text())
        rows.append({"camera":case["camera"],"video":info["video"],"video_sha256":info["video_sha256"],
                     "source_images":str((folder/"images").relative_to(ROOT)),
                     "groundtruth":str((folder/"groundtruth.xml").relative_to(ROOT)) if (folder/"groundtruth.xml").exists() else None,
                     "label":case["label"]+" / 인물 등록 후 분석",
                     "source_reference":"ChokePoint/"+case["camera"]+"/available-frames"})
    return rows


def enroll():
    collection=json.loads((OUT/"stills-collection.json").read_text())
    assert collection["pass"] and file_hash(OUT/"Still.tar.xz","md5")==collection["official_md5"]
    sources=defaultdict(list)
    for row in collection["images"]:
        match=re.fullmatch(r"ID(\d{4})",Path(row["member"]).stem,re.I)
        assert match,"Unrecognized official still identity"
        sources[match[1]].append(row)
    app=create_face_app()
    directory=OUT/"references";directory.mkdir(exist_ok=True)
    licence=(ROOT/"docs/testing/licenses/ChokePoint.txt").read_bytes()
    (OUT/"CHOKEPOINT_LICENSE.txt").write_bytes(licence)
    (directory/"CHOKEPOINT_LICENSE.txt").write_bytes(licence)
    new=[];audit=[]
    for identity,images in sorted(sources.items()):
        refs=[]
        for source in images:
            raw=cv2.imread(str(ROOT/source["path"]));assert raw is not None
            scale=min(1.,1600/max(raw.shape[:2]))
            image=cv2.resize(raw,(round(raw.shape[1]*scale),round(raw.shape[0]*scale)))
            face=reference_face(app.get(image),image.shape)
            if face is None:
                audit.append({"identity":identity,"source":source["member"],"accepted":False})
                continue
            x1,y1,x2,y2=face.bbox;w=x2-x1;h=y2-y1
            bounds=(max(0,round(x1-.3*w)),max(0,round(y1-.3*h)),min(image.shape[1],round(x2+.3*w)),min(image.shape[0],round(y2+.3*h)))
            crop=image[bounds[1]:bounds[3],bounds[0]:bounds[2]]
            ratio=min(1.,512/max(crop.shape[:2]));crop=cv2.resize(crop,(round(crop.shape[1]*ratio),round(crop.shape[0]*ratio)))
            filename=identity+"-"+Path(source["member"]).parent.name.lower()+".jpg"
            target=directory/filename;assert cv2.imwrite(str(target),crop,[cv2.IMWRITE_JPEG_QUALITY,93])
            refs.append(target.resolve().as_posix())
            audit.append({"identity":identity,"source":source["member"],"source_sha256":file_hash(ROOT/source["path"]),
                          "accepted":True,"reference_sha256":file_hash(target),"path":target.relative_to(ROOT).as_posix()})
        assert refs,"No usable official enrollment photo for "+identity
        new.append({"id":"chokepoint-"+identity,"name":"출입 인물 "+str(int(identity)).zfill(2),"images":refs,
                    "dataset_identity":identity})
        print(json.dumps({"enrolled":identity,"photos":len(refs)}),flush=True)
    original=ROOT/"evidence/private/public-figure-demo/references.json"
    previous=json.loads(original.read_text())["profiles"]
    for row in previous:
        row["images"]=[str((original.parent/item).resolve()) if isinstance(item,str)
                       else {**item,"image":str((original.parent/item["image"]).resolve())} for item in row["images"]]
    gallery={"schema_version":1,"profiles":previous+[{key:value for key,value in row.items() if key!="dataset_identity"} for row in new]}
    save(OUT/"references.json",gallery)
    save(OUT/"enrollment.json",{"pass":True,"new_profiles":new,"audit":audit,"sources":specs(),
                               "gallery_sha256":file_hash(OUT/"references.json"),"official_subject_ids":sorted(sources),
                               "verified_utc":stamp(),"training_performed":False})
    save(ROOT/"evidence/history/chokepoint-people-enrollment.json",{
        "pass":True,"verified_utc":stamp(),"new_profiles":len(new),"gallery_profiles":len(gallery["profiles"]),
        "accepted_stills":sum(row["accepted"] for row in audit),"rejected_stills":sum(not row["accepted"] for row in audit),
        "official_subject_ids":sorted(sources),"query_video_frames_used_for_enrollment":False,
        "gallery_sha256":file_hash(OUT/"references.json"),"actual_paid_api_calls":0,"model_training_performed":False})


def truth_for(case):
    if not case["groundtruth"]:return {}
    dataset=ET.parse(ROOT/case["groundtruth"]).getroot();assert dataset.get("name")==case["camera"]
    return {int(frame.get("number")):[{"identity":p.get("id"),"eyes":[(float(p.find(tag).get("x")),float(p.find(tag).get("y"))) for tag in ("leftEye","rightEye")]} for p in frame.findall("person")] for frame in dataset}


def analyze():
    registration=json.loads((OUT/"enrollment.json").read_text())
    assert file_hash(OUT/"references.json")==registration["gallery_sha256"]
    cases=[]
    for case in registration["sources"]:
        assert file_hash(ROOT/case["video"])==case["video_sha256"]
        folder=OUT/"analysis"/case["camera"]
        record=folder/"verified.json"
        if record.exists():
            info=json.loads(record.read_text());assert info["gallery_sha256"]==registration["gallery_sha256"]
            cases.append(info);continue
        command=[sys.executable,str(ROOT/"tools/run_edge.py"),"--source",str(ROOT/case["video"]),"--device","cpu","--classes","0",
                 "--person-tracking","--face-references",str(OUT/"references.json"),"--face-stride","5","--vid-stride","2",
                 "--project",str(OUT/"analysis"),"--name",case["camera"],"--exist-ok","--nosave"]
        folder.mkdir(parents=True,exist_ok=True)
        print(json.dumps({"analysis_started":case["camera"],"body_fps":15,"face_fps":3}),flush=True)
        with (folder/"model.log").open("w") as output:
            result=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,timeout=1800,
                                  env={**os.environ,"OMP_NUM_THREADS":"2","MKL_NUM_THREADS":"2","OPENBLAS_NUM_THREADS":"2"})
        assert result.returncode==0,"Inspect model.log"
        logs=list((folder/"person-analysis").glob("*.jsonl"));assert len(logs)==1
        rows=[json.loads(line) for line in logs[0].read_text().splitlines()]
        assert len({row["frame_index"] for row in rows})==len(rows)
        truths=truth_for(case);source_images=sorted((ROOT/case["source_images"]).glob("*.jpg"))
        ground=[];by_track=defaultdict(list);correct=wrong=held=0
        for row in rows:
            index=round(row["video_seconds"]*30);assert index<len(source_images)
            original=source_images[index].name
            people=truths.get(int(Path(original).stem),[])
            for face in row["faces"]:
                identity=ground_truth_identity(face["bbox"],people)
                ground.append({"frame_index":row["frame_index"],"identity":identity,"candidate":face["candidate_profile_id"],
                               "track_id":face["body_track_id"],"original_image":original})
                if face["body_track_id"] is not None:
                    by_track[face["body_track_id"]].append(identity)
                if identity:
                    if face["candidate_profile_id"]=="chokepoint-"+identity:correct+=1
                    elif face["candidate_profile_id"]:wrong+=1
                    else:held+=1
        info={**case,"gallery_sha256":registration["gallery_sha256"],"log":logs[0].relative_to(ROOT).as_posix(),
              "frames_analyzed":len(rows),"face_detections":len(ground),"scored_face_matches":correct+wrong+held,
              "correct_candidates":correct,"wrong_candidates":wrong,"unresolved_labeled_faces":held,
              "mixed_identity_tracks":[key for key,values in by_track.items() if len({v for v in values if v})>1],
              "verified_utc":stamp()}
        save(folder/"groundtruth-check.json",ground);save(record,info);cases.append(info)
        print(json.dumps({key:info[key] for key in ("camera","frames_analyzed","face_detections","correct_candidates","wrong_candidates")}),flush=True)
    save(OUT/"analysis.json",{"pass":True,"cases":cases,"verified_utc":stamp()})
    save(ROOT/"evidence/history/chokepoint-people-analysis.json",{"pass":True,"cases":cases,"verified_utc":stamp(),
        "model_training_performed":False,"actual_paid_api_calls":0,"groundtruth_unavailable_for_crowd":True})


def prepare():
    registration=json.loads((OUT/"enrollment.json").read_text());analysis=json.loads((OUT/"analysis.json").read_text())
    profiles=[{"id":row["id"],"name":row["name"]} for row in json.loads((OUT/"references.json").read_text())["profiles"]]
    entries=[];case_proofs=[]
    for case in analysis["cases"]:
        rows=[json.loads(line) for line in (ROOT/case["log"]).read_text().splitlines()]
        labeled=json.loads((OUT/"analysis"/case["camera"]/"groundtruth-check.json").read_text())
        correct_ground={(value["frame_index"],value["track_id"],value["candidate"]) for value in labeled
                        if value["identity"] and value["candidate"]=="chokepoint-"+value["identity"]}
        by_identity=defaultdict(list)
        useful=[row for row in rows if row["faces"] and row["tracks"]]
        assert useful
        for row in useful:
            for face in row["faces"]:
                key=face["candidate_profile_id"]
                if key and key.startswith("chokepoint-") and face["body_track_id"] is not None:
                    if case["groundtruth"] and (row["frame_index"],face["body_track_id"],key) not in correct_ground:continue
                    by_identity[key].append((face["similarity"],row["frame_index"]))
        selected={useful[round((len(useful)-1)*n/9)]["frame_index"] for n in range(10)}
        for values in by_identity.values():
            values.sort(reverse=True)
            selected.update(index for _,index in values[:2])
        session=uuid5(NAMESPACE_URL,"chokepoint-enrolled-v1/"+case["video_sha256"]+registration["gallery_sha256"]).hex
        config={"id":session,"source_label":case["label"],"source_kind":"video","recording_started_at":None,
                "model_versions":{"yolov5":"7.0","face_model":"buffalo_l","face_policy":"candidate-2",
                                  "gallery":"chokepoint-stills-v1","demo_provenance":"NICTA ChokePoint; official still enrollment, raw video reanalysis"},
                "profiles":profiles,"purpose":"demo","source_reference":case["source_reference"]}
        capture=cv2.VideoCapture(str(ROOT/case["video"]))
        case_entries=[]
        for row in useful:
            if row["frame_index"] not in selected:continue
            index=round(row["video_seconds"]*30);capture.set(cv2.CAP_PROP_POS_FRAMES,index);ok,image=capture.read();assert ok
            key=hashlib.sha256(f'{session}:{row["frame_index"]}'.encode()).hexdigest()
            target=OUT/"observations"/(key+".jpg");target.parent.mkdir(exist_ok=True)
            assert cv2.imwrite(str(target),image,[cv2.IMWRITE_JPEG_QUALITY,87])
            frame={name:row[name] for name in ("frame_index","video_seconds","processed_at_utc","tracks","faces","crossings","image_size")}
            frame["captured_at"]=None;assert not frame["crossings"]
            entry={"id":key,"packet":{"schema_version":1,"session":config,"frame":frame,"post_id":None},
                   "image":target.relative_to(ROOT).as_posix()}
            entries.append(entry);case_entries.append(entry)
        capture.release()
        evidence_by_track=defaultdict(list)
        all_candidates=defaultdict(set)
        for item in labeled:
            if item["track_id"] is not None:
                evidence_by_track[item["track_id"]].append(item["identity"])
                if item["candidate"]:all_candidates[item["track_id"]].add(item["candidate"])
        best={}
        for entry in case_entries:
            faces=entry["packet"]["frame"]["faces"]
            for face in faces:
                track=face["body_track_id"]
                if sum(value["body_track_id"]==track for value in faces)!=1:continue
                if track is not None and face["candidate_profile_id"] and (track not in best or face["similarity"]>best[track][0]):
                    best[track]=(face["similarity"],face["candidate_profile_id"])
        confirmations=[]
        for track,(_,candidate) in best.items():
            if all_candidates[track]!={candidate}:continue
            identity=dataset_track_identity(evidence_by_track[track],candidate)
            if identity:
                confirmations.append({"track_id":track,"profile":"chokepoint-"+identity,"basis":"dataset"})
        case_proofs.append({"camera":case["camera"],"session":session,"source_reference":case["source_reference"],
                            "selected_frames":len(case_entries),"candidate_profiles":sorted(by_identity),
                            "dataset_confirmations":confirmations,"crowd_has_no_groundtruth":not bool(case["groundtruth"])})
    save(OUT/"packets.json",{"pass":True,"profiles":registration["new_profiles"],"cases":case_proofs,"entries":entries})
    print(json.dumps({"prepared_profiles":len(registration["new_profiles"]),"new_analysis_sessions":len(case_proofs),
                      "selected_photos":len(entries),"dataset_track_confirmations":sum(len(row["dataset_confirmations"]) for row in case_proofs)}),flush=True)


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("stage",choices=["enroll","analyze","prepare"])
    args=parser.parse_args();{"enroll":enroll,"analyze":analyze,"prepare":prepare}[args.stage]()


if __name__=="__main__":main()
