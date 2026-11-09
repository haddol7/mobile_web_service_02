"""Evaluate new-identity, cross-source video frames using the production face matcher."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT/"evidence/private/face-validation"
PUBLIC = ROOT/"evidence/person-libraries"
CONDITIONS = ["original", "low_light_35_percent", "low_resolution_64px"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_frames(path, indices):
    cap = cv2.VideoCapture(str(path))
    selected = {}
    for index in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, image = cap.read()
        assert ok
        selected[index] = image
    cap.release()
    return selected


def primary(faces):
    return max(faces, key=lambda f:(f["bbox"][2]-f["bbox"][0])*(f["bbox"][3]-f["bbox"][1])) if faces else None


def transform(image, condition):
    if condition == "low_light_35_percent":
        return np.rint(image.astype(float)*.35).astype(np.uint8)
    if condition == "low_resolution_64px":
        h,w = image.shape[:2]
        factor = min(1.,64/max(h,w))
        small = cv2.resize(image,(max(1,round(w*factor)),max(1,round(h*factor))),interpolation=cv2.INTER_AREA)
        return cv2.resize(small,(w,h),interpolation=cv2.INTER_LINEAR)
    return image.copy()


def summarize(rows):
    known = [r for r in rows if r["enrolled"]]
    unknown = [r for r in rows if not r["enrolled"]]
    correct = sum(r["outcome"]=="correct_candidate" for r in known)
    wrong_known = sum(r["outcome"]=="wrong_candidate" for r in known)
    false_unknown = sum(r["outcome"]=="wrong_candidate" for r in unknown)
    accepted = correct+wrong_known+false_unknown
    known_clips, unknown_clips = defaultdict(list), defaultdict(list)
    people = defaultdict(list)
    for row in known:
        known_clips[row["clip_sha256"]].append(row)
        people[row["identity"]].append(row)
    for row in unknown:
        unknown_clips[row["clip_sha256"]].append(row)
    return {
        "known_frames":len(known), "correct_candidates":correct, "wrong_known_candidates":wrong_known,
        "known_unresolved":sum(r["outcome"]=="unresolved" for r in known),
        "known_no_face":sum(r["outcome"]=="no_face" for r in known),
        "known_correct_per_sampled_frame":correct/len(known) if known else None,
        "known_identity_macro_recall":float(np.mean([
            sum(r["outcome"]=="correct_candidate" for r in values)/len(values) for values in people.values()])) if people else None,
        "unknown_frames":len(unknown), "unknown_false_candidates":false_unknown,
        "unknown_unresolved":sum(r["outcome"]=="unresolved" for r in unknown),
        "unknown_no_face":sum(r["outcome"]=="no_face" for r in unknown),
        "unknown_false_candidates_per_sampled_frame":false_unknown/len(unknown) if unknown else None,
        "accepted_candidate_precision":correct/accepted if accepted else None,
        "known_clips":len(known_clips),
        "known_clips_with_any_correct_candidate":sum(any(r["outcome"]=="correct_candidate" for r in v) for v in known_clips.values()),
        "known_clips_with_any_wrong_candidate":sum(any(r["outcome"]=="wrong_candidate" for r in v) for v in known_clips.values()),
        "unknown_clips":len(unknown_clips),
        "unknown_clips_with_any_false_candidate":sum(any(r["outcome"]=="wrong_candidate" for r in v) for v in unknown_clips.values()),
        "mean_face_analysis_seconds":float(np.mean([r["seconds"] for r in rows])) if rows else None}


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in the project WSL virtualenv.")
    collection = json.loads((PRIVATE/"collection.json").read_text())
    sys.path.insert(0,str(ROOT/"YOLOv5"))
    from person_tracking import create_face_app, FaceReferences
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    directory = PRIVATE/stamp
    directory.mkdir(parents=True)
    protocol = {
        "frozen_utc":datetime.now(timezone.utc).isoformat(),
        "reference_frames_per_video":3, "reference_indices":"first, middle, last",
        "query_frames_per_video":12, "query_indices":"uniform including first and last",
        "threshold":.55, "profile_margin":.08, "model":"buffalo_l",
        "primary_face_policy":"largest detected face with min side 20px, independently in each transformed image",
        "conditions":CONDITIONS, "threshold_adjustment_allowed":False,
        "known_identities":12, "unknown_identities":6, "query_clips":36,
        "original_and_synthetic_conditions_are_not_independent_samples":True}
    (directory/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    (PUBLIC/"expanded-face-protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    identities = collection["enrolled_identities"]+collection["unknown_identities"]
    labels = {identity:f"validation-{i+1:03d}" for i,identity in enumerate(collection["enrolled_identities"])}
    profiles, registration, previews = [], [], {}
    source_hashes = set()
    app = create_face_app("buffalo_l")
    reference_decoded = set()
    for item in collection["clips"]:
        assert sha(ROOT/item["path"]) == item["sha256"]
        if item["role"] != "reference":
            continue
        total = item["decode"]["frames"]
        images = read_frames(ROOT/item["path"],[0,total//2,total-1])
        valid, rejected, files = 0,0,[]
        for index,image in images.items():
            reference_decoded.add(hashlib.sha256(image.tobytes()).hexdigest())
            name=f'{labels[item["identity"]]}-{index}.jpg'
            assert cv2.imwrite(str(directory/name),image,[cv2.IMWRITE_JPEG_QUALITY,95])
            faces=app.get(cv2.imread(str(directory/name)))
            valid += len(faces)==1
            rejected += len(faces)!=1
            files.append(name)
        if valid:
            profiles.append({"id":labels[item["identity"]],"images":files})
        registration.append({"identity":item["identity"], "valid_reference_images":valid,
                             "rejected_reference_images":rejected, "enrollable":valid>0})
        previews[item["identity"]] = [images[total//2]]
    del app
    gc.collect()
    assert profiles, "No enrollable profiles"
    manifest = directory/"references.json"
    manifest.write_text(json.dumps({"schema_version":1,"profiles":profiles},indent=2)+"\n")
    matcher = FaceReferences(manifest,model="buffalo_l",threshold=.55,margin=.08,embedding_mode="single",legacy_registration=True)
    queries = [item for item in collection["clips"] if item["role"]=="query"]
    overlap = 0
    per_frame = []
    output = directory/"predictions.jsonl"
    started_all = time.perf_counter()
    for number,item in enumerate(queries):
        indices=np.linspace(0,item["decode"]["frames"]-1,12,dtype=int).tolist()
        assert len(set(indices))==12
        frames = read_frames(ROOT/item["path"],indices)
        previews.setdefault(item["identity"],[])
        previews[item["identity"]].append(frames[indices[len(indices)//2]])
        expected = labels.get(item["identity"]) if item["enrolled"] else None
        for index,image in frames.items():
            overlap += int(hashlib.sha256(image.tobytes()).hexdigest() in reference_decoded)
            for condition in CONDITIONS:
                transformed=transform(image,condition)
                started=time.perf_counter()
                faces=matcher.analyze(transformed)
                elapsed=time.perf_counter()-started
                selected=primary(faces)
                candidate=selected["candidate_profile_id"] if selected else None
                outcome=("no_face" if selected is None else "unresolved" if candidate is None
                         else "correct_candidate" if expected is not None and candidate==expected else "wrong_candidate")
                row={"identity":item["identity"],"enrolled":item["enrolled"],"expected_profile":expected,
                     "clip_sha256":item["sha256"],"source_video_id":item["source_video_id"],"frame_index":index,
                     "condition":condition,"outcome":outcome,"candidate_profile":candidate,
                     "similarity":selected["similarity"] if selected else None,"margin":selected["margin"] if selected else None,
                     "faces_detected":len(faces),"seconds":elapsed}
                per_frame.append(row)
                with output.open("a",encoding="utf-8") as log:
                    log.write(json.dumps(row)+"\n")
        print(json.dumps({"processed_query_clips":number+1,"selected":len(queries),
                          "frame_conditions":len(per_frame)}),flush=True)
    summaries={condition:summarize([r for r in per_frame if r["condition"]==condition]) for condition in CONDITIONS}
    per_person=[]
    for identity in identities:
        item={"identity":identity,"enrolled":identity in labels,"conditions":{}}
        for condition in CONDITIONS:
            rows=[r for r in per_frame if r["identity"]==identity and r["condition"]==condition]
            item["conditions"][condition]={key:sum(r["outcome"]==key for r in rows)
                for key in ["correct_candidate","wrong_candidate","unresolved","no_face"]}
        per_person.append(item)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sheets=[]
    for page in range(3):
        fig,axes=plt.subplots(6,3,figsize=(8,14),dpi=120)
        for row,identity in enumerate(identities[page*6:page*6+6]):
            images=previews[identity]
            if identity not in labels: images=[None]+images
            for col,axis in enumerate(axes[row]):
                if col<len(images) and images[col] is not None:
                    axis.imshow(cv2.cvtColor(images[col],cv2.COLOR_BGR2RGB))
                axis.axis("off")
                axis.set_title(identity+(" ref" if col==0 else f" query {col}"),fontsize=9)
        fig.suptitle("Source review: reference and two distinct source-video IDs")
        fig.tight_layout(rect=[0,0,1,.98])
        path=directory/f"source-review-{page+1}.png"
        fig.savefig(path);plt.close(fig)
        sheets.append(str(path.relative_to(ROOT)))
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),dpi=140)
    names=["Original","Low light 35%","64px downsample"]
    for axis,known in zip(axes,[True,False]):
        denominator=288 if known else 144
        keys=(["correct_candidates","known_unresolved","known_no_face","wrong_known_candidates"] if known
              else ["unknown_unresolved","unknown_no_face","unknown_false_candidates"])
        labels_bar=(["Correct candidate","Unresolved","No face","Wrong candidate"] if known
                    else ["Unresolved","No face","False candidate"])
        colors=["#2b765d","#adb8b1","#d9d9d9","#bb4040"] if known else ["#adb8b1","#d9d9d9","#bb4040"]
        left=np.zeros(3)
        for key,label,color in zip(keys,labels_bar,colors):
            values=np.array([summaries[c][key]/denominator*100 for c in CONDITIONS])
            axis.barh(names,values,left=left,label=label,color=color)
            left+=values
        axis.set_xlim(0,100);axis.set_xlabel("Sampled frame conditions (%)")
        axis.set_title("Enrolled people" if known else "Unknown people")
        axis.legend(loc="lower center",bbox_to_anchor=(.5,-.35),ncol=2,fontsize=8)
    fig.suptitle("Buffalo L: fixed 0.55 threshold and 0.08 profile margin")
    fig.tight_layout(rect=[0,.08,1,.94])
    chart=PUBLIC/"expanded-face-results.png";fig.savefig(chart);plt.close(fig)
    result={
        "verified_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu CPU",
        "face_module":"Production FaceReferences.analyze and match_embedding with actual InsightFace ONNX models",
        "yolo_pipeline_rerun_for_this_batch":False,
        "protocol":protocol,"collection":"evidence/person-libraries/expanded-face-collection.json",
        "registration":registration,"accepted_registration":matcher.registration,
        "query_clips":len(queries),"source_frames_sampled":len(queries)*12,
        "frame_conditions_processed":len(per_frame),"threshold_unchanged":True,
        "exact_reference_decoded_frame_overlap":overlap,"conditions":summaries,
        "per_identity":per_person,"elapsed_seconds":time.perf_counter()-started_all,
        "private_directory":str(directory.relative_to(ROOT)),"source_review_images":sheets,
        "chart":str(chart.relative_to(ROOT)),"chart_sha256":sha(chart),
        "training_performed":False,"automatic_confirmation_enabled":False,"production_verified":False,
        "different_recording_dates_proven":False,"pretrained_model_training_identity_overlap_unknown":True,
        "limitations":["Different source-video IDs do not alone prove distinct original recordings.",
                      "Twelve frames within each clip are correlated; frame conditions are not independent people.",
                      "Low light and low resolution are controlled transformations, not new recorded videos.",
                      "Dataset labels, rather than independent manual identity annotations, supply the expected identities."],
        "execution_pass":True,"source_sha256":{name:sha(ROOT/name) for name in [
            "tools/verify_face_generalization.py","tools/collect_face_validation.py","YOLOv5/person_tracking.py"]}}
    (PUBLIC/"expanded-face-validation.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"complete":True,"conditions":summaries,"source_review_images":sheets},indent=2),flush=True)


if __name__ == "__main__":
    main()
