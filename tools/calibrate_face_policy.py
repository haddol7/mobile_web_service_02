"""Choose candidate thresholds on development identities only; no model training."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import numpy as np

from face_improvement_data import ROOT,extract,scores,evaluate


def main():
    if platform.system()!="Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in WSL.")
    private=ROOT/"evidence/private/face-improvement/development"
    public=ROOT/"evidence/person-libraries"
    collection=json.loads((ROOT/"evidence/private/face-validation/collection.json").read_text())
    protocol={"created_utc":datetime.now(timezone.utc).isoformat(),"role":"development_only",
        "embedding_modes":["single","flip_mean"],"threshold_grid":[round(i/100,2) for i in range(25,61)],
        "margin_grid":[.02,.04,.06,.08,.10],"selection":"maximize correct candidates with zero observed known or unknown wrong candidates; prefer larger threshold/margin on ties",
        "minimum_impostor_score_buffer":.05,
        "held_out_identity_ids_used":False,"training_performed":False}
    private.mkdir(parents=True,exist_ok=True)
    (private/"calibration-protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    meta,arrays=extract(collection,private,["original"])
    old,unused=evaluate(meta,scores(meta,arrays,mode="single",improved_registration=False),.55,.08)
    ranking={mode:scores(meta,arrays,mode=mode) for mode in protocol["embedding_modes"]}
    safety={}
    for mode,ranked in ranking.items():
        column=0 if mode=="single" else 1
        impostors=[]
        for identity in ranked[3]:
            reference_ids=[i for i,r in enumerate(meta["references"]) if r["identity"]==identity and r["improved_valid"]]
            values=(arrays["queries"][:,column]@arrays["references"][reference_ids,column].T).max(axis=1)
            mask=np.array([not q["enrolled"] or q["identity"]!=identity for q in meta["queries"]])
            impostors.extend(values[mask].tolist())
        maximum=max(impostors)
        safety[mode]={"max_development_impostor_similarity":maximum,
                      "minimum_threshold":maximum+protocol["minimum_impostor_score_buffer"],
                      "impostor_comparisons":len(impostors)}
    grid=[];feasible=[]
    for mode,ranked in ranking.items():
        for threshold in protocol["threshold_grid"]:
            for margin in protocol["margin_grid"]:
                summary,_=evaluate(meta,ranked,threshold,margin)
                row={"embedding_mode":mode,"threshold":threshold,"margin":margin,**summary}
                grid.append(row)
                if (not row["wrong_known_candidates"] and not row["unknown_false_candidates"]
                        and threshold>=safety[mode]["minimum_threshold"]):
                    feasible.append(row)
    assert feasible
    chosen=max(feasible,key=lambda r:(r["correct_candidates"],r["threshold"],r["margin"],r["embedding_mode"]=="single"))
    assert chosen["correct_candidates"]>old["correct_candidates"],"No measured improvement; retain legacy policy"
    result={"calibrated_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu CPU",
        "protocol":protocol,"single_gallery_safety":safety,"legacy_reproduction":old,"selected":chosen,"grid":grid,
        "development_identity_ids":collection["enrolled_identities"]+collection["unknown_identities"],
        "held_out_identity_ids_used":False,"training_performed":False,
        "recognizer_sha256":meta["recognizer_sha256"],
        "source_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
            "tools/calibrate_face_policy.py","tools/face_improvement_data.py","YOLOv5/face_features.py"]}}
    record=public/"face-policy-calibration.json"
    record.write_text(json.dumps(result,indent=2)+"\n")
    policy={"schema_version":1,"version":"candidate-2","model":"buffalo_l",
        "threshold":chosen["threshold"],"margin":chosen["margin"],"embedding_mode":chosen["embedding_mode"],
        "reference_min_size":20,"reference_dominance_area_ratio":4,
        "recognizer_sha256":meta["recognizer_sha256"],"automatic_confirmation_enabled":False,
        "calibration_record":"evidence/person-libraries/face-policy-calibration.json",
        "calibration_record_sha256":hashlib.sha256(record.read_bytes()).hexdigest(),
        "calibration_only_no_final_evaluation":True}
    frozen=private/"frozen-policy.json"
    frozen.write_text(json.dumps(policy,indent=2)+"\n")
    (public/"face-policy-frozen.json").write_text(json.dumps(policy,indent=2)+"\n")
    print(json.dumps({"legacy":old,"selected":chosen,"policy":policy},indent=2),flush=True)


if __name__=="__main__":
    main()
