"""Actual CPU video -> history HTTP -> SQLite -> grounded question verification in WSL."""
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
from threading import Thread
from wsgiref.simple_server import make_server, WSGIRequestHandler

import requests

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT/"evidence/history"
PRIVATE = ROOT/"evidence/private/history"


class Quiet(WSGIRequestHandler):
    def log_message(self, *_):
        pass


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in the project WSL virtualenv.")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    directory = PRIVATE/stamp
    directory.mkdir(parents=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    os.environ.update(DJANGO_SETTINGS_MODULE="photoblog.settings", DJANGO_DEBUG="true",
        DJANGO_DB_PATH=str(directory/"db.sqlite3"), DJANGO_MEDIA_ROOT=str(directory/"media"),
        HISTORY_MEDIA_ROOT=str(directory/"history-images"), BLOG_OWNER_USERNAME="daejinha")
    sys.path.insert(0, str(ROOT/"PhotoBlogServer"))
    import django
    django.setup()
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    from django.core.wsgi import get_wsgi_application
    from django.db import connections
    from rest_framework.authtoken.models import Token
    from blog.models import TrackingSession, TrackingFrame, PersonTrack, PassageEvent, Post
    call_command("migrate", interactive=False, verbosity=0)
    password = secrets.token_urlsafe(30)
    owner = get_user_model().objects.create_user("daejinha", password=password)
    token = Token.objects.create(user=owner).key
    # Store credentials only in this ignored, isolated local fixture for the device harness.
    (directory/"test-auth.json").write_text(json.dumps({"username": owner.username, "password": password}))
    application = get_wsgi_application()
    lost_response = {"injected": False, "duplicate_replays": 0}
    def middleware(environ, start_response):
        if environ["PATH_INFO"] != "/api/v1/history/ingest/":
            return application(environ, start_response)
        saved = {}
        def capture(status, headers, exc_info=None):
            saved.update(status=status, headers=headers)
        response = application(environ, capture)
        try:
            body = b"".join(response)
        finally:
            if hasattr(response, "close"):
                response.close()
        if saved["status"].startswith("201") and not lost_response["injected"]:
            lost_response["injected"] = True
            start_response("503 Service Unavailable", [("Content-Type", "application/json")])
            return [b'{"detail":"simulated response loss after commit"}']
        if saved["status"].startswith("200"):
            lost_response["duplicate_replays"] += 1
        start_response(saved["status"], saved["headers"])
        return [body]
    server = make_server("127.0.0.1", 0, middleware, handler_class=Quiet)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    auth = {"Authorization": "Token "+token}
    runs = []
    try:
        collection = json.loads((ROOT/"evidence/tracking-samples/collection.json").read_text())
        sequence = next(s for s in collection["sequences"] if s["id"] == "TUD-Campus")
        fixture = ROOT/"evidence/private/person-libraries/face-fixture"
        oracle = json.loads((fixture/"oracle.json").read_text())
        face = next(row for row in oracle if row["expected"] is not None)
        inputs = [("pedestrian", ROOT/sequence["video"]["path"], []),
                  ("face", Path(face["path"]), ["--face-references", str(fixture/"references.json"), "--face-stride", "1"])]
        for name, source, extra in inputs:
            output = directory/name
            command = [sys.executable, str(ROOT/"tools/run_edge.py"), "--source", str(source),
                "--device", "cpu", "--person-history", "--count-line", ".5", "0", ".5", "1",
                "--server", origin, "--history-source-label", "공개 보행자 검증 영상" if name=="pedestrian" else "공개 얼굴 검증 영상",
                "--project", str(directory), "--name", name, *extra]
            result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, YOLO_API_TOKEN=token),
                                    capture_output=True, text=True, timeout=300)
            (directory/(name+".txt")).write_text(result.stdout+result.stderr)
            assert result.returncode == 0, f"Inspect private {name}.txt"
            logs = list((output/"person-analysis").glob("*.jsonl"))
            assert len(logs) == 1
            records = [json.loads(line) for line in logs[0].read_text().splitlines()]
            retry = subprocess.run([sys.executable, str(ROOT/"tools/retry_person_history.py"),
                "--server", origin, "--outbox", str(output/"history-outbox")], cwd=ROOT,
                env=dict(os.environ, YOLO_API_TOKEN=token), capture_output=True, text=True, timeout=180)
            assert retry.returncode == 0, "History outbox replay failed"
            assert not list((output/"history-outbox").rglob("*.json"))
            runs.append({"input": name, "frames_analyzed": len(records),
                         "crossings_in_local_log": sum(len(row["crossings"]) for row in records),
                         "face_candidates_in_local_log": sum(bool(f["candidate_profile_id"]) for row in records for f in row["faces"]),
                         "pending_packets_after_replay": 0})
        connections.close_all()
        assert lost_response["injected"] and lost_response["duplicate_replays"] >= 1
        assert TrackingSession.objects.count() == 2
        assert PassageEvent.objects.count() == sum(row["crossings_in_local_log"] for row in runs)
        assert PersonTrack.objects.filter(candidate__isnull=False).exists()
        assert not PersonTrack.objects.filter(confirmed__isnull=False).exists()
        assert not TrackingFrame.objects.filter(observed_at__isnull=False).exists()
        # Compare the actual persisted private snapshot with a clean decoded source frame.
        # This catches diagnostics being burnt over the face before the upload boundary.
        import cv2
        from PIL import Image, ImageOps
        selected_face = TrackingFrame.objects.filter(session__source_label="공개 얼굴 검증 영상").order_by("-frame_index").first()
        capture = cv2.VideoCapture(str(Path(face["path"])))
        capture.set(cv2.CAP_PROP_POS_FRAMES, selected_face.frame_index-1)
        readable, decoded = capture.read(); capture.release()
        assert readable
        height, width = decoded.shape[:2]; scale = min(1, 640/max(height, width))
        preview = cv2.resize(decoded, (max(1, round(width*scale)), max(1, round(height*scale))))
        encoded, raw = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 80]); assert encoded
        with Image.open(BytesIO(raw.tobytes())) as source_image:
            clean = ImageOps.exif_transpose(source_image).convert("RGB"); clean.thumbnail((1280,1280))
            expected = BytesIO(); clean.save(expected, "JPEG", quality=85)
        with selected_face.image.open("rb") as stored_image:
            assert hashlib.sha256(stored_image.read()).hexdigest()==hashlib.sha256(expected.getvalue()).hexdigest(), "History evidence contains an overlay or differs from the original video frame"
        frames = requests.get(origin+"/api/v1/history/frames/", headers=auth, timeout=15)
        assert frames.status_code == 200 and frames.json()["results"]
        photo = next(f for f in frames.json()["results"] if f["image_url"])
        image = requests.get(origin+photo["image_url"], headers=auth, timeout=15)
        assert image.status_code == 200
        assert requests.get(origin+photo["image_url"], timeout=15).status_code == 401
        assert requests.get(origin+"/history/", timeout=15, allow_redirects=False).status_code == 302
        answer = requests.post(origin+"/api/v1/history/ask/", headers=auth,
            json={"question": "언제 나타났고 몇 번 통과했어?"}, timeout=15)
        assert answer.status_code == 200
        facts = answer.json()["facts"]
        assert facts["passages"] == PassageEvent.objects.count()
        assert facts["observed_tracks"] == PersonTrack.objects.count()
        assert facts["unknown_date_frames"] == TrackingFrame.objects.count()
        assert facts["dates"] == []
        assert answer.json()["mode"] == "records" and answer.json()["evidence"]
        selected = PersonTrack.objects.filter(candidate__isnull=False).first()
        url = origin+f"/api/v1/history/tracks/{selected.pk}/"
        review = requests.patch(url, headers=auth, json={"revision": 1, "profile": selected.candidate_id}, timeout=15)
        assert review.status_code == 200
        assert requests.patch(url, headers=auth, json={"revision": 1, "profile": None}, timeout=15).status_code == 409
        assert requests.patch(url, headers=auth, json={"revision": 2, "profile": None}, timeout=15).status_code == 200
        # Restore the disposable fixture's unreviewed state after the review API round trip.
        selected.refresh_from_db()
        selected.reviewed_at = None
        selected.save(update_fields=["reviewed_at"])
        posts = requests.get(origin+"/api_root/Post/", timeout=15).json()
        assert posts and all(set(row)=={"id","author","title","text","created_date","published_date","image"} for row in posts)
        verification = {"verified_utc": datetime.now(timezone.utc).isoformat(), "environment": "WSL Ubuntu CPU",
            "runs": runs, "sessions": TrackingSession.objects.count(), "frames_stored": TrackingFrame.objects.count(),
            "tracks_stored": PersonTrack.objects.count(), "passages_stored": PassageEvent.objects.count(),
            "candidate_tracks": PersonTrack.objects.filter(candidate__isnull=False).count(),
            "automatic_confirmation_enabled": False, "unknown_capture_dates_preserved": True,
            "response_loss_after_commit_injected": True, "idempotent_replays_received": lost_response["duplicate_replays"],
            "private_snapshot_auth_verified": True, "manual_review_and_revision_verified": True,
            "canonical_question_counts_match_db": True, "question_evidence_verified": True,
            "required_post_api_seven_fields_preserved": True, "posts_uploaded": len(posts),
            "actual_llm_generation_verified": False, "production_verified": False,
            "raw_history_snapshot_verified": True,
            "face_policy": json.loads((ROOT/"YOLOv5/face_policy.json").read_text()) if (ROOT/"YOLOv5/face_policy.json").exists() else None,
            "fixture": str(directory.relative_to(ROOT)), "pass": True,
            "source_sha256": {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for folder in [ROOT/"PhotoBlogServer/blog", ROOT/"YOLOv5"] for p in folder.glob("*history*.py")}}
        (PUBLIC/"verification.json").write_text(json.dumps(verification, indent=2)+"\n")
        (PUBLIC/"latest-fixture.json").write_text(json.dumps({"fixture":str(directory.relative_to(ROOT))},indent=2)+"\n")
        print(json.dumps(verification, indent=2))
    finally:
        server.shutdown(); server.server_close(); connections.close_all()


if __name__ == "__main__":
    main()
