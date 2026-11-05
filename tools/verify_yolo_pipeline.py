"""Verify upstream inference and real YOLO -> HTTP -> Django photo registration in WSL."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import subprocess
import sys
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

import cv2
import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
YOLO = ROOT / "YOLOv5"
EVIDENCE = ROOT / "evidence/yolo-pipeline"
PRIVATE = ROOT / "evidence/private/local"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_detector(script, source, name, *, base_url=None, password=None):
    env = dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1", MPLBACKEND="Agg", PYTHONPATH=str(YOLO))
    command = [sys.executable, str(script), "--weights", str(YOLO / "yolov5s.pt"),
               "--data", str(YOLO / "data/coco128.yaml"), "--source", str(source),
               "--device", "cpu", "--project", str(EVIDENCE), "--name", name, "--exist-ok", "--save-txt", "--save-conf"]
    if base_url:
        command += ["--server", base_url]
        env.update(YOLO_USERNAME="daejinha", YOLO_PASSWORD=password)
        env.pop("YOLO_API_TOKEN", None)
    result = subprocess.run(command, cwd=YOLO, env=env, capture_output=True, text=True, timeout=180)
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout + result.stderr)
    (EVIDENCE / (name + ".txt")).write_text("Command: " + " ".join(command) + "\n\n" + output + f"\nExit code: {result.returncode}\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"Detector failed; inspect evidence/yolo-pipeline/{name}.txt")
    print(output, flush=True)


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_):
        pass


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run this verification in the dedicated WSL environment.")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    upstream = json.loads((ROOT / "docs/upstream/provenance.json").read_text())
    original = YOLO / "baseline/detect.py"
    assert digest(original) == upstream["detect_sha256"], "Upstream baseline was modified"
    run_detector(original, YOLO / "data/images/bus.jpg", "original-image")
    labels = (EVIDENCE / "original-image/labels/bus.txt").read_text().splitlines()
    original_classes = [int(line.split()[0]) for line in labels]
    assert original_classes.count(0) == 4 and original_classes.count(5) == 1

    # Keep verification storage separate from both assessment 01 and ordinary local development.
    os.environ.update(DJANGO_SETTINGS_MODULE="photoblog.settings", DJANGO_DB_PATH=str(PRIVATE / "db.sqlite3"),
                      DJANGO_MEDIA_ROOT=str(PRIVATE / "media"), BLOG_OWNER_USERNAME="daejinha", DJANGO_DEBUG="true")
    sys.path.insert(0, str(ROOT / "PhotoBlogServer"))
    import django
    django.setup()
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    from django.core.wsgi import get_wsgi_application
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from blog.models import Post
    call_command("migrate", interactive=False, verbosity=0)
    password = secrets.token_urlsafe(32)
    user, _ = get_user_model().objects.get_or_create(username="daejinha")
    user.is_staff = user.is_superuser = user.is_active = True
    user.set_password(password)
    user.save()

    fixtures = PRIVATE / "frames"
    fixtures.mkdir(exist_ok=True)
    bus = cv2.imread(str(YOLO / "data/images/bus.jpg"))
    for name, frame in [("01-bus.jpg", bus), ("02-bus.jpg", bus),
                        ("03-empty.jpg", np.full_like(bus, 128)), ("04-bus.jpg", bus)]:
        assert cv2.imwrite(str(fixtures / name), frame)
    initial = set(Post.objects.values_list("pk", flat=True))
    server = make_server("127.0.0.1", 0, StaticFilesHandler(get_wsgi_application()), handler_class=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        run_detector(YOLO / "detect.py", fixtures, "server-registration", base_url=base_url, password=password)
        posts = requests.get(base_url + "/api_root/Post/", timeout=20).json()
        added = [row for row in posts if row["id"] not in initial]
        assert len(added) == 2, f"Expected two appearance events, got {len(added)}"
        saved = []
        for row in added:
            assert set(row) == {"id", "author", "title", "text", "created_date", "published_date", "image"}
            assert row["title"] == "YOLO: person, bus"
            response = requests.get(row["image"], timeout=20)
            assert response.status_code == 200
            local = Post.objects.get(pk=row["id"]).image.path
            assert hashlib.sha256(response.content).hexdigest() == digest(local)
            image = cv2.imdecode(np.frombuffer(response.content, dtype=np.uint8), cv2.IMREAD_COLOR)
            assert image.shape[:2] == (240, 320)
            assert requests.get(base_url + f"/post/{row['id']}/", timeout=20).status_code == 200
            saved.append({"id": row["id"], "title": row["title"], "image_sha256": digest(local), "size": [320, 240]})
        assert requests.get(base_url + "/", timeout=20).status_code == 200
        assert requests.get(base_url + "/api_root/", timeout=20).status_code == 200
        record = {"verified_utc": datetime.now(timezone.utc).isoformat(), "environment": "WSL Ubuntu",
                  "python": sys.executable, "original_detect_sha256": digest(original),
                  "modified_detect_sha256": digest(YOLO / "detect.py"), "weights_sha256": digest(YOLO / "yolov5s.pt"),
                  "baseline": {"source": "official bus.jpg", "person": 4, "bus": 1},
                  "real_pipeline": {"input_frames": ["bus", "bus", "empty", "bus"], "uploads": saved,
                                    "persistent_frame_skipped": True, "empty_frame_skipped": True, "reappearance_uploaded": True,
                                    "api_shape": "seven-field array", "public_image_bytes_match": True},
                  "webcam_tested": False, "pass": True}
        (EVIDENCE / "verification.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        # No reusable verification password is stored or printed.
        user.set_unusable_password()
        user.save(update_fields=["password"])


if __name__ == "__main__":
    main()
