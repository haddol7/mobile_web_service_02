"""Check fixed-policy open-set behavior with different numbers of enrolled profiles."""
from datetime import datetime,timezone
from itertools import combinations
import hashlib
import json
import os
from pathlib import Path
import platform

import numpy as np
from face_improvement_data import ROOT,CONDITIONS


def main():
    if platform.system()!="Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside WSL.")
    public=ROOT/"evidence/person-libraries";private=ROOT/"evidence/private/face-improvement/evaluation"
    policy=json.loads((public/"face-policy-frozen.json").read_text())
    meta=json.loads((private/"features.json").read_text())
    arrays=np.load(private/"features.npz",allow_pickle=False)
    column=0 if policy["embedding_mode"]=="single" else 1
    identities=sorted({r["identity"] for r in meta["references"] if r["improved_valid"]})
    matrix=np.stack([(arrays["queries"][:,column]@arrays["references"][
        [i for i,r in enumerate(meta["references"]) if r["identity"]==identity and r["improved_valid"]],column].T).max(axis=1)
        for identity in identities],axis=1)
    query_ids=np.array([q["identity"] for q in meta["queries"]])
    face_detected=np.array([q["face_detected"] for q in meta["queries"]])
    result={};unique_wrong={}
    for condition in CONDITIONS:
        mask=np.array([q["condition"]==condition for q in meta["queries"]])
        data,truth,detected=matrix[mask],query_ids[mask],face_detected[mask]
        checks={}
        for count in sorted(set([1,2,3,6,len(identities)])):
            if count>len(identities):continue
            aggregate={"subsets":0,"correct":0,"wrong":0,"known_frames":0,"unknown_frames":0,
                       "unknown_false_candidates":0,"subsets_with_wrong_candidate":0}
            worst_precision=1.;worst_far=0.
            for subset in combinations(range(len(identities)),count):
                names=np.array(identities)[list(subset)]
                values=data[:,subset]
                order=np.argsort(-values,axis=1)
                best=values[np.arange(len(data)),order[:,0]]
                gap=best-values[np.arange(len(data)),order[:,1]] if count>1 else best+1
                labels=names[order[:,0]]
                known=np.isin(truth,names)
                accepted=detected&(best>=policy["threshold"])&(gap>=policy["margin"])
                correct=accepted&known&(labels==truth)
                wrong=accepted&~correct
                for position in np.flatnonzero(wrong):
                    source_index=np.flatnonzero(mask)[position]
                    source=meta["queries"][int(source_index)]
                    key=(condition,source["clip_sha256"],source["frame_index"],str(labels[position]))
                    unique_wrong[key]={"condition":condition,"true_identity":source["identity"],
                        "clip_sha256":source["clip_sha256"],"frame_index":source["frame_index"],
                        "candidate_identity":str(labels[position]),"similarity":float(best[position])}
                false_unknown=accepted&~known
                ncorrect,nwrong=int(correct.sum()),int(wrong.sum())
                nunknown=int((~known).sum())
                precision=ncorrect/(ncorrect+nwrong) if ncorrect+nwrong else 1.
                far=int(false_unknown.sum())/nunknown if nunknown else 0.
                worst_precision=min(worst_precision,precision);worst_far=max(worst_far,far)
                aggregate["subsets"]+=1;aggregate["correct"]+=ncorrect;aggregate["wrong"]+=nwrong
                aggregate["known_frames"]+=int(known.sum());aggregate["unknown_frames"]+=nunknown
                aggregate["unknown_false_candidates"]+=int(false_unknown.sum())
                aggregate["subsets_with_wrong_candidate"]+=int(nwrong>0)
            aggregate.update(candidate_precision=aggregate["correct"]/(aggregate["correct"]+aggregate["wrong"]) if aggregate["correct"]+aggregate["wrong"] else None,
                unknown_false_accept_rate=aggregate["unknown_false_candidates"]/aggregate["unknown_frames"] if aggregate["unknown_frames"] else None,
                worst_subset_candidate_precision=worst_precision,worst_subset_unknown_false_accept_rate=worst_far,
                counts_are_correlated_reuses_of_same_frames=True)
            checks[str(count)]=aggregate
        result[condition]=checks
    passed=all(v["candidate_precision"] is not None and v["candidate_precision"]>=.99 and v["unknown_false_accept_rate"]<=.01
               for condition in result.values() for v in condition.values())
    record={"verified_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu CPU",
        "policy_sha256":hashlib.sha256((public/"face-policy-frozen.json").read_bytes()).hexdigest(),
        "profile_count_checks":result,"sparse_and_dense_gallery_checks_pass":passed,
        "distinct_false_candidate_frame_conditions":list(unique_wrong.values()),
        "model_inference_repeated":False,"policy_adjusted_from_these_results":False,
        "automatic_confirmation_enabled":False,"production_verified":False}
    (public/"face-policy-gallery-audit.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))


if __name__=="__main__":
    main()
