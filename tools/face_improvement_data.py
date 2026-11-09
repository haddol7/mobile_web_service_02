"""Actual raw/flip features cached privately for calibration and identity-disjoint evaluation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"YOLOv5"))
from face_features import reference_face,eligible_faces,feature
from person_tracking import create_face_app

CONDITIONS=["original","low_light_35_percent","low_resolution_64px"]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def transformed(image,condition):
    if condition=="low_light_35_percent":return np.rint(image.astype(float)*.35).astype(np.uint8)
    if condition=="low_resolution_64px":
        h,w=image.shape[:2];ratio=min(1.,64/max(h,w))
        low=cv2.resize(image,(max(1,round(w*ratio)),max(1,round(h*ratio))),interpolation=cv2.INTER_AREA)
        return cv2.resize(low,(w,h),interpolation=cv2.INTER_LINEAR)
    return image.copy()


def extract(collection,folder,conditions):
    folder.mkdir(parents=True,exist_ok=True)
    contract={"model":"buffalo_l","conditions":conditions,"reference_indices":"first,middle,last",
        "query_frames":12,"feature_code_sha256":sha(ROOT/"YOLOv5/face_features.py"),
        "source_clips":[(c["sha256"],c["role"],c["identity"]) for c in collection["clips"]]}
    fingerprint=hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()
    meta_file=folder/"features.json";features_file=folder/"features.npz"
    if meta_file.exists() and features_file.exists():
        meta=json.loads(meta_file.read_text())
        if meta["fingerprint"]==fingerprint and sha(features_file)==meta["features_sha256"]:
            arrays=np.load(features_file,allow_pickle=False)
            print(json.dumps({"reused_private_features":True,"queries":len(meta["queries"])}),flush=True)
            return meta,{k:arrays[k] for k in arrays.files}
    app=create_face_app("buffalo_l")
    recognizer_path=Path(app.models["recognition"].model_file)
    refs,queries,ref_vectors,query_vectors=[],[],[],[]
    started=time.perf_counter()
    for number,clip in enumerate(collection["clips"]):
        source=ROOT/clip["path"];assert sha(source)==clip["sha256"]
        total=clip["decode"]["frames"]
        indices=[0,total//2,total-1] if clip["role"]=="reference" else np.linspace(0,total-1,12,dtype=int).tolist()
        cap=cv2.VideoCapture(str(source))
        for index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES,index);ok,original=cap.read();assert ok
            if clip["role"]=="reference":
                # Reproduce the previous reference JPEG contract for a fair old/new comparison.
                ok,encoded=cv2.imencode(".jpg",original,[cv2.IMWRITE_JPEG_QUALITY,95]);assert ok
                image=cv2.imdecode(encoded,cv2.IMREAD_COLOR)
                faces=app.get(image);selected=reference_face(faces,image.shape)
                legacy=faces[0] if len(faces)==1 else None
                vector_face=selected if selected is not None else legacy
                # Largest foreground selection and old exact-one-face selection agree when both apply.
                ref_vectors.append(np.stack([feature(app,vector_face,image,mode) if vector_face is not None else np.zeros(512,np.float32)
                                             for mode in ["single","flip_mean"]]))
                refs.append({"identity":clip["identity"],"clip_sha256":clip["sha256"],
                    "frame_index":index,"legacy_valid":legacy is not None,
                    "improved_valid":selected is not None,"detected_faces":len(faces)})
            else:
                for condition in conditions:
                    image=transformed(original,condition)
                    faces=eligible_faces(app.get(image))
                    selected=max(faces,key=lambda f:(f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1])) if faces else None
                    query_vectors.append(np.stack([feature(app,selected,image,mode) if selected is not None else np.zeros(512,np.float32)
                                                   for mode in ["single","flip_mean"]]))
                    queries.append({"identity":clip["identity"],"enrolled":clip["enrolled"],
                        "clip_sha256":clip["sha256"],"source_video_id":clip["source_video_id"],"frame_index":index,
                        "condition":condition,"face_detected":selected is not None})
        cap.release()
        print(json.dumps({"feature_clips_completed":number+1,"selected":len(collection["clips"]),
                          "query_conditions":len(queries)}),flush=True)
    arrays={"references":np.stack(ref_vectors),"queries":np.stack(query_vectors)}
    np.savez_compressed(features_file,**arrays)
    meta={"created_utc":datetime.now(timezone.utc).isoformat(),"fingerprint":fingerprint,"contract":contract,
        "features_sha256":sha(features_file),"recognizer_sha256":sha(recognizer_path),
        "references":refs,"queries":queries,"elapsed_seconds":time.perf_counter()-started,
        "private_biometric_features_not_for_upload":True}
    meta_file.write_text(json.dumps(meta,indent=2)+"\n")
    return meta,arrays


def scores(meta,arrays,*,mode,improved_registration=True):
    column=0 if mode=="single" else 1
    valid="improved_valid" if improved_registration else "legacy_valid"
    identities=sorted({r["identity"] for r in meta["references"] if r[valid]})
    per_person=[]
    for identity in identities:
        ids=[i for i,r in enumerate(meta["references"]) if r["identity"]==identity and r[valid]]
        gallery=arrays["references"][ids,column]
        per_person.append((arrays["queries"][:,column]@gallery.T).max(axis=1))
    matrix=np.stack(per_person,axis=1)
    order=np.argsort(-matrix,axis=1)
    best=matrix[np.arange(len(matrix)),order[:,0]]
    gap=best-matrix[np.arange(len(matrix)),order[:,1]] if len(identities)>1 else best+1
    labels=np.array(identities)[order[:,0]]
    return labels,best,gap,identities


def evaluate(meta,ranked,threshold,margin,condition=None):
    labels,similarities,gaps,identities=ranked
    indices=[i for i,q in enumerate(meta["queries"]) if condition is None or q["condition"]==condition]
    rows=[];known_correct=known_wrong=unknown_wrong=held_known=held_unknown=no_face_known=no_face_unknown=0
    known_clips={};unknown_clips={}
    for i in indices:
        row=meta["queries"][i]
        accepted=row["face_detected"] and similarities[i]>=threshold and gaps[i]>=margin
        correct=accepted and row["enrolled"] and labels[i]==row["identity"]
        wrong=accepted and not correct
        if row["enrolled"]:
            known_correct+=int(correct);known_wrong+=int(wrong)
            held_known+=int(not accepted and row["face_detected"])
            no_face_known+=int(not row["face_detected"])
            known_clips.setdefault(row["clip_sha256"],[]).append((correct,wrong))
        else:
            unknown_wrong+=int(wrong)
            held_unknown+=int(not accepted and row["face_detected"])
            no_face_unknown+=int(not row["face_detected"])
            unknown_clips.setdefault(row["clip_sha256"],[]).append(wrong)
        rows.append({**row,"candidate":str(labels[i]) if accepted else None,
                     "similarity":float(similarities[i]),"margin":float(gaps[i]),
                     "outcome":"correct" if correct else "wrong" if wrong else "unresolved" if row["face_detected"] else "no_face"})
    known=known_correct+known_wrong+held_known+no_face_known
    unknown=unknown_wrong+held_unknown+no_face_unknown
    summary={"known_frames":known,"unknown_frames":unknown,"correct_candidates":known_correct,
        "wrong_known_candidates":known_wrong,"unknown_false_candidates":unknown_wrong,
        "known_unresolved":held_known,"unknown_unresolved":held_unknown,"known_no_face":no_face_known,
        "unknown_no_face":no_face_unknown,"known_recall":known_correct/known if known else None,
        "candidate_precision":known_correct/(known_correct+known_wrong+unknown_wrong) if known_correct+known_wrong+unknown_wrong else None,
        "unknown_false_accept_rate":unknown_wrong/unknown if unknown else None,
        "known_clips_with_correct_candidate":sum(any(v[0] for v in values) for values in known_clips.values()),
        "known_clips_with_wrong_candidate":sum(any(v[1] for v in values) for values in known_clips.values()),
        "unknown_clips_with_false_candidate":sum(any(v for v in values) for values in unknown_clips.values()),
        "enrolled_profiles":len(identities)}
    return summary,rows
