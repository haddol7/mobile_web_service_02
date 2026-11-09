"""Use the downloaded Obama clips in the actual YOLOv5/InsightFace pipeline."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "evidence/person-libraries"
SOURCES = ROOT / "evidence/private/hf-video-candidates"
PRIVATE = ROOT / "evidence/private/person-libraries/obama"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decoded_hash(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def inspect_and_preview(path, expected_frames, preview_index, target):
    capture = cv2.VideoCapture(str(path))
    count = 0
    preview = None
    while True:
        ok, image = capture.read()
        if not ok:
            break
        if count == preview_index:
            preview = image
        count += 1
    capture.release()
    assert count == expected_frames, "Annotated output was not completely decoded"
    assert preview is not None and cv2.imwrite(str(target), preview)


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run this test in the project WSL virtualenv.")
    verified = json.loads((SOURCES / "download-verification.json").read_text())
    for item in verified["samples"]:
        filename = Path(item["member"]).name if "hdtf" in item["dataset"] else "_".join(Path(item["member"]).parts[-3:])
        assert sha(SOURCES / filename) == item["sha256"], "Downloaded source integrity differs"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    folder = PRIVATE / stamp
    folder.mkdir(parents=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    reference_video = SOURCES / "BarackObama_001.mp4"
    query_video = SOURCES / "BarackObama_044.mp4"
    capture = cv2.VideoCapture(str(reference_video))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    reference_indices = [0, total // 2, total - 1]
    ref_paths, ref_decoded_hashes = [], []
    for index in reference_indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, image = capture.read()
        assert ok
        name = f"reference-obama-{index}.jpg"
        assert cv2.imwrite(str(folder/name), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        ref_paths.append(name)
        ref_decoded_hashes.append(decoded_hash(image))
    capture.release()
    old_fixture = ROOT / "evidence/private/person-libraries/face-fixture"
    previous = json.loads((old_fixture/"references.json").read_text())
    profiles = [{"id": "public-obama", "name": "Barack Obama", "images": ref_paths}]
    for profile in previous["profiles"]:
        for name in profile["images"]:
            shutil.copyfile(old_fixture/name, folder/name)
        profiles.append(profile)
    manifest = folder/"references.json"
    manifest.write_text(json.dumps({"schema_version":1, "profiles":profiles}, indent=2)+"\n")
    # Preserve two competing enrolled profiles and one unknown person. Labels below are
    # only used for scoring; queries are passed to the model as opaque hashed filenames.
    oracle = json.loads((old_fixture/"oracle.json").read_text())
    cases = [{"case":"obama_other_clip", "source":query_video, "expected":"public-obama",
              "same_original_recording_possible":True}]
    for index, entry in enumerate(oracle):
        items = [item for item in verified["samples"] if "VoxCeleb2" in item["dataset"]
                 and Path(item["member"]).parts[-2] == entry["source_video_id"]]
        assert len(items) == 1
        source = SOURCES/"_".join(Path(items[0]["member"]).parts[-3:])
        cases.append({"case":f"other_person_{index+1}", "source":source,
                      "expected":entry["expected"], "same_original_recording_possible":False})
    query_overlap = 0
    check = cv2.VideoCapture(str(query_video))
    while True:
        ok, image = check.read()
        if not ok:
            break
        query_overlap += int(decoded_hash(image) in ref_decoded_hashes)
    check.release()
    results = []
    for number, case in enumerate(cases):
        opaque = folder/(sha(case["source"])[:20]+".mp4")
        shutil.copyfile(case["source"], opaque)
        name = f"query-{number}"
        command = [sys.executable, str(ROOT/"tools/run_edge.py"), "--source", str(opaque),
            "--device", "cpu", "--classes", "0", "--person-tracking",
            "--face-references", str(manifest), "--face-model", "buffalo_l", "--face-legacy", "--face-stride", "1",
            "--project", str(folder), "--name", name]
        started = time.perf_counter()
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=600)
        elapsed = time.perf_counter()-started
        (folder/(name+".txt")).write_text(run.stdout+run.stderr, encoding="utf-8")
        assert run.returncode == 0, f"Inspect ignored local {name}.txt"
        output = folder/name
        logs = list((output/"person-analysis").glob("*.jsonl"))
        assert len(logs) == 1
        records = [json.loads(line) for line in logs[0].read_text().splitlines()]
        source_capture = cv2.VideoCapture(str(case["source"]))
        expected_count = int(source_capture.get(cv2.CAP_PROP_FRAME_COUNT))
        source_capture.release()
        assert len(records) == expected_count
        faces = [face for row in records for face in row["faces"]]
        primary = [max(row["faces"], key=lambda f:(f["bbox"][2]-f["bbox"][0])*(f["bbox"][3]-f["bbox"][1]))
                   for row in records if row["faces"]]
        accepted = [f for f in primary if f["candidate_profile_id"] is not None]
        correct = [f for f in accepted if case["expected"] and f["candidate_profile_id"] == case["expected"]]
        videos = list(output.glob("*.mp4"))
        assert len(videos) == 1
        preview = output/"preview.jpg"
        inspect_and_preview(videos[0], expected_count, expected_count//2, preview)
        scores = [f["similarity"] for f in primary]
        result = {"case":case["case"], "source_sha256":sha(case["source"]), "frames":len(records),
            "primary_face_frames":len(primary), "no_face_frames":len(records)-len(primary),
            "all_face_detections":len(faces), "correct_primary_candidates":len(correct),
            "wrong_primary_candidates":len(accepted)-len(correct), "unresolved_primary_faces":len(primary)-len(accepted),
            "primary_obama_candidates":sum(f["candidate_profile_id"]=="public-obama" for f in primary),
            "all_obama_candidates":sum(f["candidate_profile_id"]=="public-obama" for f in faces),
            "minimum_primary_similarity":min(scores,default=None),
            "maximum_primary_similarity":max(scores,default=None),
            "primary_similarity_median":float(np.median(scores)) if scores else None,
            "faces_associated_to_one_yolo_track":sum(f["body_track_id"] is not None for f in faces),
            "fully_decoded_output_video":True, "elapsed_seconds":elapsed}
        results.append(result)
        print(json.dumps(result), flush=True)
    # Analysis figure uses actual reference and annotated query frames, with no synthetic faces.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.5), dpi=150)
    reference = cv2.imread(str(folder/ref_paths[1]))
    query = cv2.imread(str(folder/"query-0/preview.jpg"))
    for axis, image, title in zip(axes, [reference, query], ["Registered clip 001", "Compared clip 044"]):
        axis.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        axis.set_title(title, fontsize=13)
        axis.axis("off")
    positive = results[0]
    fig.suptitle(f'Buffalo L: {positive["correct_primary_candidates"]}/{positive["primary_face_frames"]} primary faces matched',
                 fontsize=16)
    fig.text(.5, .025, "Actual CPU inference. Same original recording possible. Threshold 0.55, profile margin 0.08.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=[0,.05,1,.93])
    figure = folder/"obama-comparison.png"
    fig.savefig(figure)
    plt.close(fig)
    result = {"verified_utc":datetime.now(timezone.utc).isoformat(), "environment":"WSL Ubuntu CPU",
        "model":"buffalo_l", "threshold":.55, "profile_margin":.08,
        "registration_clip":"BarackObama_001.mp4", "query_clip":"BarackObama_044.mp4",
        "registration_frames":reference_indices, "registered_profiles":3, "registered_images":9,
        "exact_decoded_reference_frame_matches_in_query":query_overlap,
        "same_original_recording_possible":True, "independent_recording_accuracy_established":False,
        "scoring_policy":"Largest detected face per frame is primary; all-face Obama matches also reported.",
        "runs":results, "total_frames_processed":sum(r["frames"] for r in results),
        "unknown_people_count":1, "threshold_changed_for_this_test":False,
        "training_performed":False, "production_verified":False,
        "automatic_confirmation_enabled":False,
        "comparison_image":str(figure.relative_to(ROOT)), "comparison_image_sha256":sha(figure),
        "private_run_directory":str(folder.relative_to(ROOT)),
        "pipeline_execution_pass":True,
        "same_recording_obama_smoke_pass":positive["correct_primary_candidates"]>0 and positive["wrong_primary_candidates"]==0,
        "other_people_false_obama_candidates":sum(r["all_obama_candidates"] for r in results[1:]),
        "source_sha256":{name:sha(ROOT/name) for name in [
            "tools/verify_obama_identity.py", "YOLOv5/person_tracking.py", "YOLOv5/detect.py", "tools/run_edge.py"]}}
    (PUBLIC/"obama-identity.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({"complete":True, "record":str((PUBLIC/"obama-identity.json").relative_to(ROOT)),
                      "comparison_image":str(figure.relative_to(ROOT))}), flush=True)


if __name__ == "__main__":
    main()
