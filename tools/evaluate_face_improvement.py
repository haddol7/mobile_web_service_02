"""Compare old/new policies on new identities after freezing the development choice."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil

import numpy as np
from face_improvement_data import ROOT,CONDITIONS,extract,scores,evaluate


def main():
    if platform.system()!="Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside WSL.")
    public=ROOT/"evidence/person-libraries"
    private=ROOT/"evidence/private/face-improvement/evaluation"
    private.mkdir(parents=True,exist_ok=True)
    frozen=public/"face-policy-frozen.json"
    policy=json.loads(frozen.read_text())
    policy_hash=hashlib.sha256(frozen.read_bytes()).hexdigest()
    calibration=json.loads((public/"face-policy-calibration.json").read_text())
    assert hashlib.sha256((public/"face-policy-calibration.json").read_bytes()).hexdigest()==policy["calibration_record_sha256"]
    collection=json.loads((ROOT/"evidence/private/face-improvement/holdout/collection.json").read_text())
    ids=set(collection["enrolled_identities"]+collection["unknown_identities"])
    assert not ids&set(calibration["development_identity_ids"])
    protocol={"frozen_utc":datetime.now(timezone.utc).isoformat(),"policy_sha256":policy_hash,
        "known_identities":12,"unknown_identities":12,"query_frames_per_clip":12,"conditions":CONDITIONS,
        "adoption_criteria":{"original_recall_gain_min":.10,"candidate_precision_min":.99,
                             "unknown_false_accept_rate_max":.01},
        "policy_selection_from_holdout_allowed":False,"model_training_allowed":False}
    (private/"evaluation-protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    (public/"face-improvement-protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    meta,arrays=extract(collection,private,CONDITIONS)
    assert meta["recognizer_sha256"]==policy["recognizer_sha256"]
    legacy_rank=scores(meta,arrays,mode="single",improved_registration=False)
    fixed_rank=scores(meta,arrays,mode="single",improved_registration=True)
    improved_rank=scores(meta,arrays,mode=policy["embedding_mode"],improved_registration=True)
    comparisons={};predictions=[]
    for condition in CONDITIONS:
        before,before_rows=evaluate(meta,legacy_rank,.55,.08,condition)
        ref_only,_=evaluate(meta,fixed_rank,.55,.08,condition)
        after,after_rows=evaluate(meta,improved_rank,policy["threshold"],policy["margin"],condition)
        comparisons[condition]={"legacy":before,"registration_fix_only":ref_only,"improved":after,
            "recall_gain":after["known_recall"]-before["known_recall"]}
        predictions.extend(after_rows)
    assert hashlib.sha256(frozen.read_bytes()).hexdigest()==policy_hash
    # Replay cached real model features through the production matching implementation.
    from person_tracking import FaceReferences
    replay=FaceReferences.__new__(FaceReferences)
    replay.threshold,replay.margin=policy["threshold"],policy["margin"]
    column=0 if policy["embedding_mode"]=="single" else 1
    replay.references={identity:arrays["references"][
        [i for i,r in enumerate(meta["references"]) if r["identity"]==identity and r["improved_valid"]],column]
        for identity in improved_rank[3]}
    checked=0
    candidate_by_key={(r["clip_sha256"],r["frame_index"],r["condition"]):r["candidate"] for r in predictions}
    for i,row in enumerate(meta["queries"]):
        if not row["face_detected"]:continue
        actual=replay.match_embedding(arrays["queries"][i,column])
        assert actual["candidate_profile_id"]==candidate_by_key[row["clip_sha256"],row["frame_index"],row["condition"]]
        checked+=1
    tests_pass=all(c["improved"]["candidate_precision"] is not None and
                   c["improved"]["candidate_precision"]>=.99 and c["improved"]["unknown_false_accept_rate"]<=.01
                   for c in comparisons.values())
    adopt=tests_pass and comparisons["original"]["recall_gain"]>=.10
    default=ROOT/"YOLOv5/face_policy.json"
    if adopt:
        shutil.copyfile(frozen,default)
    (private/"predictions.json").write_text(json.dumps(predictions,indent=2)+"\n")
    result={"verified_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu CPU",
        "protocol":protocol,"policy":policy,"policy_sha256":policy_hash,"identity_disjoint":True,
        "development_identity_count":len(calibration["development_identity_ids"]),
        "final_identity_count":len(ids),"query_clips":48,"distinct_query_frames":576,
        "frame_conditions":len(meta["queries"]),"comparisons":comparisons,
        "production_matching_replay_checked":checked,"new_policy_default_applied":adopt,
        "default_policy_sha256":hashlib.sha256(default.read_bytes()).hexdigest() if adopt else None,
        "private_directory":str(private.relative_to(ROOT)),
        "source_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
            "YOLOv5/person_tracking.py","YOLOv5/face_features.py","tools/face_improvement_data.py",
            "tools/evaluate_face_improvement.py","YOLOv5/history_sender.py"]},
        "yolo_integration_verified_in_this_run":False,"production_verified":False,
        "training_performed":False,"automatic_confirmation_enabled":False,
        "execution_pass":True,"adoption_checks_pass":adopt}
    (public/"face-improvement-evaluation.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"comparisons":comparisons,"new_policy_default_applied":adopt},indent=2),flush=True)


if __name__=="__main__":
    main()
