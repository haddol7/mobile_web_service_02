"""Portable WSL entry points. Verification never requests paid APIs or writes to production."""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SERVER = "https://daejinha.pythonanywhere.com"
YOLO_HASH = "8b3b748c1e592ddd8868022e8732fde20025197328490623cc16c6f24d0782ee"


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_manifest(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "laptop/MANIFEST.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Package path missing or outside package: " + row["path"])
        if path.stat().st_size != row["bytes"] or sha(path) != row["sha256"]:
            raise ValueError("Package file changed: " + row["path"])
    return len(manifest["files"])


def verify(root=ROOT):
    import cv2
    import torch
    root = Path(root)
    count = validate_manifest(root)
    if sha(root / "YOLOv5/yolov5s.pt") != YOLO_HASH:
        raise ValueError("YOLO release weights mismatch")
    baseline = json.loads((root / "docs/upstream/provenance.json").read_text())
    if sha(root / "YOLOv5/baseline/detect.py") != baseline["detect_sha256"]:
        raise ValueError("Upstream detect.py changed")
    sys.path.insert(0, str(root / "YOLOv5"))
    from person_tracking import create_face_app
    from face_features import load_policy, verify_policy_model
    model_root = root / "laptop"
    if not (model_root / "models/buffalo_l/det_10g.onnx").is_file():
        raise ValueError("Bundled face models missing; no automatic download in Verify")
    app = create_face_app(root=model_root)
    verify_policy_model(app, load_policy("buffalo_l"))
    assert set(app.models) >= {"recognition", "detection"}
    assert all(model.session.get_providers() == ["CPUExecutionProvider"] for model in app.models.values())
    references = json.loads((root / "laptop/data/references.json").read_text())
    reference_count = 0
    for profile in references["profiles"]:
        for item in profile["images"]:
            filename = item if isinstance(item, str) else item["image"]
            image = cv2.imread(str(root / "laptop/data" / filename))
            if image is None:
                raise ValueError("Unreadable portable reference")
            reference_count += 1
    result = {"checked_utc": datetime.now(timezone.utc).isoformat(),
              "environment": "WSL Ubuntu", "python": platform.python_version(),
              "source": str(root), "verified_files": count,
              "torch_cpu": float((torch.ones(2) + 1).sum()),
              "gallery_profiles": len(references["profiles"]), "reference_images": reference_count,
              "face_model_loaded": True, "camera_devices": [str(p) for p in Path("/dev").glob("video*")],
              "paid_api_calls": 0, "production_requests": 0, "pass": True}
    output = root / ".local/laptop"
    output.mkdir(parents=True, exist_ok=True)
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def check_camera(source):
    if not source.isdigit():
        raise ValueError("Webcam source must be the actual camera device index")
    path = Path("/dev/video" + source)
    if not path.exists():
        raise RuntimeError("WSL cannot see " + str(path) + ". See laptop/START_HERE.md camera section. No video-file fallback is used.")
    import cv2
    capture = cv2.VideoCapture(int(source))
    try:
        valid = capture.isOpened() and capture.read()[0]
    finally:
        capture.release()
    if not valid:
        raise RuntimeError("Camera exists but no real frame could be read. Check camera permissions and USB attachment.")


def command(action, source, root=ROOT):
    root = Path(root)
    cmd = [sys.executable, str(root / "tools/run_edge.py")]
    if action == "webcam":
        cmd += ["--baseline"]
    if action == "sample":
        source = str(root / "laptop/data/walking.mp4")
    cmd += ["--source", source, "--device", "cpu", "--project", str(root / ".local/laptop/runs"), "--name", action]
    if action != "webcam":
        cmd += ["--classes", "0", "--person-tracking", "--face-references", str(root / "laptop/data/references.json"),
                "--face-model-root", str(root / "laptop"), "--face-stride", "5"]
    if action == "sample":
        cmd += ["--vid-stride", "5"]
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        cmd += ["--view-img"]
    if action in {"monitor", "video"}:
        cmd += ["--server", SERVER, "--person-history", "--history-source-label", "노트북 웹캠" if action == "monitor" else Path(source).stem]
    return cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["verify", "sample", "webcam", "monitor", "video"])
    parser.add_argument("--source", default="0")
    args = parser.parse_args()
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in WSL2 Ubuntu using START.cmd")
    if args.action == "verify":
        verify()
        return
    if args.action in {"webcam", "monitor"}:
        check_camera(args.source)
    if args.action == "video" and not Path(args.source).is_file():
        raise SystemExit("Video file not found")
    env = dict(os.environ)
    # Local demos never inherit production auth or use any generative API.
    for key in ("YOLO_API_TOKEN", "YOLO_USERNAME", "YOLO_PASSWORD", "YOLO_SERVER"):
        env.pop(key, None)
    if args.action in {"monitor", "video"}:
        import requests
        print("Register new observations at " + SERVER + "; no embedding or LLM calls are made by this launcher.")
        username = input("Operator username [daejinha]: ").strip() or "daejinha"
        password = getpass.getpass("Operator password (not saved): ")
        response = requests.post(SERVER + "/api-token-auth/", data={"username": username, "password": password},
                                 timeout=(5, 20), allow_redirects=False)
        password = None
        if response.status_code != 200:
            raise SystemExit("Login failed: HTTP " + str(response.status_code))
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise SystemExit("Unexpected login response")
        env["YOLO_API_TOKEN"] = token
    started = time.monotonic()
    result = subprocess.call(command(args.action, args.source), cwd=ROOT, env=env)
    evidence = {"action": args.action, "finished_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.monotonic() - started, 2), "exit_code": result,
                "actual_camera_input": args.action in {"webcam", "monitor"},
                "baseline": args.action == "webcam", "paid_api_calls": 0}
    out = ROOT / ".local/laptop"
    out.mkdir(parents=True, exist_ok=True)
    (out / (args.action + "-run.json")).write_text(json.dumps(evidence, indent=2) + "\n")
    raise SystemExit(result)


if __name__ == "__main__":
    main()
