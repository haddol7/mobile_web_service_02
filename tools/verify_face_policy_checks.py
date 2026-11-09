"""Record regression, immutable baseline, default policy and actual HTTP integration checks."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if platform.system()!="Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside WSL.")
    public=ROOT/"evidence/person-libraries"
    policy=json.loads((ROOT/"YOLOv5/face_policy.json").read_text())
    frozen=public/"face-policy-frozen.json"
    assert sha(frozen)==sha(ROOT/"YOLOv5/face_policy.json")
    final=json.loads((public/"face-improvement-evaluation.json").read_text())
    gallery=json.loads((public/"face-policy-gallery-audit.json").read_text())
    pipeline=json.loads((ROOT/"evidence/history/verification.json").read_text())
    assert final["adoption_checks_pass"] and gallery["sparse_and_dense_gallery_checks_pass"]
    assert pipeline["pass"] and pipeline["face_policy"]==policy
    assert f'Face matching policy: {policy["version"]}' in (ROOT/pipeline["fixture"]/"face.txt").read_text()
    upstream=json.loads((ROOT/"docs/upstream/provenance.json").read_text())
    assert sha(ROOT/"YOLOv5/baseline/detect.py")==upstream["detect_sha256"]
    command=[sys.executable,"-m","unittest","discover","-s","tests","-v"]
    test=subprocess.run(command,cwd=ROOT/"YOLOv5",capture_output=True,text=True,timeout=90)
    output=test.stdout+test.stderr
    (public/"face-improvement-unit-tests.txt").write_text(output)
    assert test.returncode==0 and "\nOK\n" in output
    count=int(re.search(r"Ran (\d+) tests",output).group(1))
    unique={(r["clip_sha256"],r["frame_index"]) for r in gallery["distinct_false_candidate_frame_conditions"]}
    result={"verified_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu CPU",
        "unit_test_command":command,"unit_test_count":count,"unit_tests_pass":True,
        "default_policy_applied":True,"default_policy_sha256":sha(ROOT/"YOLOv5/face_policy.json"),
        "recognizer_sha256":policy["recognizer_sha256"],"baseline_detector_unchanged":True,
        "actual_yolo_http_history_pipeline_pass":True,"pipeline_frames":sum(r["frames_analyzed"] for r in pipeline["runs"]),
        "pipeline_evidence":"evidence/history/verification.json",
        "sparse_gallery_checks_pass":True,"sparse_gallery_distinct_false_source_frames":len(unique),
        "final_held_out_identity_count":final["final_identity_count"],
        "training_performed":False,"automatic_confirmation_enabled":False,"production_verified":False,"pass":True,
        "source_sha256":{name:sha(ROOT/name) for name in ["YOLOv5/person_tracking.py","YOLOv5/face_features.py",
            "YOLOv5/detect.py","YOLOv5/history_sender.py","tools/verify_face_policy_checks.py"]}}
    (public/"face-improvement-checks.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
