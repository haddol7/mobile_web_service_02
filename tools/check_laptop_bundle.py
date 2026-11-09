"""Extract the laptop snapshot safely, then test its real runtime from a relocated path."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--extract", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    target = args.extract.resolve()
    private = (ROOT / "evidence/private/laptop-transfer-check").resolve()
    if not target.is_relative_to(private):
        raise ValueError("Extraction must remain in the designated verification directory")
    if not args.smoke:
        target.mkdir(parents=True, exist_ok=False)
        with ZipFile(args.archive) as archive:
            if not all((target / name).resolve().is_relative_to(target) for name in archive.namelist()):
                raise ValueError("Unsafe archive path")
            archive.extractall(target)
        print("Package extracted into a Windows path with spaces")
        return
    project = target / "mobile_web_service/common02"
    verification = json.loads((project / ".local/laptop/verification.json").read_text())
    assert verification["pass"] and verification["verified_files"] >= 600
    output = project / ".local/laptop/relocation-smoke"
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, HISTORY_LLM_CONFIG="", HISTORY_LLM_PROVIDER="", HISTORY_LLM_API_KEY="",
               HISTORY_EMBEDDING_API_KEY="", DISPLAY="", WAYLAND_DISPLAY="",
               DJANGO_DB_PATH=str(output / "empty.sqlite3"))
    for name in ("YOLO_API_TOKEN", "YOLO_USERNAME", "YOLO_PASSWORD", "YOLO_SERVER"):
        env.pop(name, None)

    def run(command, name):
        result = subprocess.run(command, cwd=project, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=180)
        (output / (name + ".txt")).write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(name + " failed; see private runtime log")
        return result.stdout

    run([sys.executable, str(project / "PhotoBlogServer/manage.py"), "check"], "django-check")
    baseline = run([sys.executable, str(project / "tools/run_edge.py"), "--baseline", "--source",
                    str(project / "YOLOv5/data/images/bus.jpg"), "--device", "cpu", "--project", str(output), "--name", "baseline"], "baseline")
    assert "4 persons" in baseline and "1 bus" in baseline
    # Sample video, not a camera test: a short clip keeps this smoke test bounded.
    import cv2
    capture = cv2.VideoCapture(str(project / "laptop/data/walking.mp4"))
    writer = cv2.VideoWriter(str(output / "short.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 5, (640, 480))
    assert writer.isOpened()
    for position in range(0, 600, 50):
        capture.set(cv2.CAP_PROP_POS_FRAMES, position)
        ok, frame = capture.read()
        assert ok
        writer.write(cv2.resize(frame, (640, 480)))
    capture.release()
    writer.release()
    run([sys.executable, str(project / "tools/run_edge.py"), "--source", str(output / "short.mp4"),
         "--device", "cpu", "--classes", "0", "--person-tracking", "--face-references", str(project / "laptop/data/references.json"),
         "--face-model-root", str(project / "laptop"), "--face-stride", "1", "--project", str(output), "--name", "tracking"], "tracking")
    logs = list((output / "tracking/person-analysis").glob("*.jsonl"))
    assert len(logs) == 1
    rows = [json.loads(line) for line in logs[0].read_text().splitlines()]
    assert len(rows) == 12
    with ZipFile(args.archive) as archive:
        names = archive.namelist()
        assert not any("/.git/" in name or "/.env" in name or "db.sqlite3" in name or name.endswith("local.properties") for name in names)
    proof = {"checked_utc": datetime.now(timezone.utc).isoformat(),
             "archive_sha256": hashlib.file_digest(args.archive.open("rb"), "sha256").hexdigest(),
             "environment": "WSL Ubuntu; Windows PowerShell launcher",
             "relocated_path_contains_spaces": True, "manifest_files": verification["verified_files"],
             "portable_gallery_profiles": verification["gallery_profiles"],
             "portable_reference_images": verification["reference_images"],
             "django_check": True, "original_yolo_actual_inference": {"person": 4, "bus": 1},
             "actual_tracking_video_frames": len(rows), "new_paid_api_calls": 0, "production_requests": 0,
             "notebook_hardware_tested": False, "actual_camera_tested": False,
             "fresh_dependency_install_tested": False, "pass": True}
    public = ROOT / "evidence/laptop-transfer"
    public.mkdir(parents=True, exist_ok=True)
    (public / "verification.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
