"""Check the saved evaluation and separate enrollment coverage from matching recall."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import platform

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT/"evidence/person-libraries"


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside WSL.")
    result = json.loads((PUBLIC/"expanded-face-validation.json").read_text())
    collection = json.loads((ROOT/"evidence/private/face-validation/collection.json").read_text())
    directory = ROOT/result["private_directory"]
    protocol = json.loads((directory/"protocol.json").read_text())
    manifest = json.loads((directory/"references.json").read_text())
    rows = [json.loads(line) for line in (directory/"predictions.jsonl").read_text().splitlines()]
    registered = {p["id"] for p in manifest["profiles"]}
    assert result["protocol"] == protocol
    assert (protocol["threshold"],protocol["profile_margin"]) == (.55,.08)
    assert len(rows) == 1296 and len({r["clip_sha256"] for r in rows}) == 36
    assert len({(r["clip_sha256"],r["frame_index"]) for r in rows}) == 432
    assert len({r["identity"] for r in rows}) == 18
    assert not set(collection["excluded_previous_identities"]) & {r["identity"] for r in rows}
    assert len({(r["clip_sha256"],r["frame_index"],r["condition"]) for r in rows}) == len(rows)
    for identity in collection["enrolled_identities"]:
        refs = {c["source_video_id"] for c in collection["clips"] if c["identity"]==identity and c["role"]=="reference"}
        queries = {c["source_video_id"] for c in collection["clips"] if c["identity"]==identity and c["role"]=="query"}
        assert len(refs)==1 and len(queries)==2 and not refs & queries
    for row in rows:
        assert row["candidate_profile"] is None or row["candidate_profile"] in registered
        if not row["enrolled"]:
            assert row["expected_profile"] is None
    for name,digest in result["source_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
    assert hashlib.sha256((ROOT/result["chart"]).read_bytes()).hexdigest() == result["chart_sha256"]
    adjusted = {}
    for condition in protocol["conditions"]:
        known = [r for r in rows if r["condition"]==condition and r["enrolled"]]
        enrolled = [r for r in known if r["expected_profile"] in registered]
        correct = sum(r["outcome"]=="correct_candidate" for r in enrolled)
        held = [r for r in enrolled if r["outcome"]=="unresolved"]
        scores = sorted(r["similarity"] for r in enrolled if r["similarity"] is not None)
        adjusted[condition] = {
            "intended_known_frames":len(known), "successfully_enrolled_known_frames":len(enrolled),
            "frames_of_unenrollable_people":len(known)-len(enrolled), "correct_candidates":correct,
            "recall_for_successfully_enrolled_people":correct/len(enrolled) if enrolled else None,
            "recall_including_enrollment_failures":sum(r["outcome"]=="correct_candidate" for r in known)/len(known),
            "enrolled_unresolved_frames":len(held),
            "unresolved_below_similarity_threshold":sum(r["similarity"]<.55 for r in held),
            "unresolved_below_profile_margin":sum(r["margin"]<.08 for r in held),
            "unresolved_failing_both":sum(r["similarity"]<.55 and r["margin"]<.08 for r in held),
            "top_similarity_min":min(scores) if scores else None,
            "top_similarity_median":scores[len(scores)//2] if scores else None,
            "top_similarity_max":max(scores) if scores else None}
    diagnosis = directory/"reference-rejection-diagnosis.json"
    rejection = json.loads(diagnosis.read_text()) if diagnosis.exists() else []
    audit = {"audited_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu",
        "data_and_scoring_consistency_pass":True,"protocol_unchanged":True,
        "old_three_identity_ids_excluded":True,"different_reference_query_source_ids":True,
        "known_people_intended":12,"known_people_successfully_enrolled":len(registered),
        "registration_failures":[r for r in result["registration"] if not r["enrollable"]],
        "registration_rejection_diagnosis":rejection,"enrollment_adjusted_metrics":adjusted,
        "independent_people":18,"query_clips":36,"distinct_sampled_frames":432,
        "frame_conditions_are_independent_people":False,"source_hashes_current":True,
        "yolo_body_tracking_retested_in_this_accuracy_batch":False,
        "capture_dates_or_cross_day_identity_proven":False,"production_verified":False}
    (PUBLIC/"expanded-face-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    print(json.dumps(audit,indent=2))


if __name__ == "__main__":
    main()
