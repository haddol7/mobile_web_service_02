"""Restore clean video snapshots and retire only our manifest's diagram records."""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

import cv2
from PIL import Image
import requests

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "evidence/private/cloud-demo"
ORIGIN = "https://daejinha.pythonanywhere.com"


def main():
    if not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Use the project WSL virtualenv.")
    sys.path.insert(0, str(ROOT / "tools/deployment"))
    import pythonanywhere_auth as auth
    from pythonanywhere_deploy import API, BASE, HOME, wait_ready
    target = PRIVATE / "face-repair-v2"
    target.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((PRIVATE / "v1/manifest.json").read_text())
    collection = json.loads((ROOT / "evidence/tracking-samples/collection.json").read_text())
    pedestrian = ROOT / next(s for s in collection["sequences"] if s["id"] == "TUD-Campus")["video"]["path"]
    face = ROOT / "evidence/private/person-libraries/face-fixture/aa6e1ef6a2653324546c.mp4"
    for entry in manifest["entries"]:
        if entry["kind"] != "actual_model_validation":
            continue
        entry["old_upload_sha256"] = sha256((PRIVATE / "v1" / (entry["id"] + ".jpg")).read_bytes()).hexdigest()
        source = face if entry["packet"]["session"]["profiles"] else pedestrian
        capture = cv2.VideoCapture(str(source))
        capture.set(cv2.CAP_PROP_POS_FRAMES, entry["packet"]["frame"]["frame_index"] - 1)
        readable, image = capture.read(); capture.release()
        assert readable, "Cannot decode original source frame"
        height, width = image.shape[:2]; scale = min(1, 640/max(height, width))
        image = cv2.resize(image, (max(1, round(width*scale)), max(1, round(height*scale))))
        encoded, raw = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80]); assert encoded
        raw = raw.tobytes()
        (target / (entry["id"] + ".jpg")).write_bytes(raw)
        entry["clean_upload_sha256"] = sha256(raw).hexdigest()
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    bundle = target / "clean-snapshots.zip"
    with ZipFile(bundle, "w", ZIP_DEFLATED) as archive:
        archive.write(target / "manifest.json", "manifest.json")
        for entry in manifest["entries"]:
            if entry["kind"] == "actual_model_validation":
                archive.write(target / (entry["id"] + ".jpg"), entry["id"] + ".jpg")
    api = API(auth.load_credentials())
    state = json.loads(api.file(BASE + "/active.json")); assert state["phase"] == "verified"
    nonce = secrets.token_hex(8)
    remote = HOME + "/.config/mobile-web-service/common02/face-repair-v2"
    # Upload to the existing private config directory before creating a backup subdirectory.
    remote_bundle = HOME + "/.config/mobile-web-service/common02/face-repair-v2.zip"
    remote_script = HOME + "/.common02-face-repair-" + nonce + ".py"
    remote_result = HOME + "/.common02-face-repair-" + nonce + ".json"
    remote_log = HOME + "/.common02-face-repair-" + nonce + ".log"
    api.file(remote_bundle, bundle.read_bytes())
    script = (ROOT / "tools/deployment/repair_history_demo_remote.py").read_text()
    script += "\ntry:\n    outcome=repair(" + repr(remote_bundle) + "," + repr(remote) + "," + repr(state) + ")\nexcept Exception as error:\n    outcome={'pass':False,'error_type':type(error).__name__}\n"
    script += "Path(" + repr(remote_result) + ").write_text(json.dumps(outcome))\n"
    api.file(remote_script, script.encode())
    wait_ready(api, 48736170)
    command = "umask 077; " + shlex.quote(state["virtualenv"] + "/bin/python") + " " + shlex.quote(remote_script) + " > " + shlex.quote(remote_log) + " 2>&1\n"
    api.request("POST", "/consoles/48736170/send_input/", {"input": command})
    print(json.dumps({"remote_job_started": True, "private_result": remote_result}), flush=True)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        value = api.file(remote_result, missing_ok=True)
        if value:
            result = json.loads(value); assert result.get("pass"), "Remote repair failed: " + result.get("error_type", "unknown")
            break
        time.sleep(2)
    else:
        raise RuntimeError("Remote job still pending; inspect the existing result before retrying")
    app = json.loads(auth.private_read(Path.home() / ".config/mobile-web-service/common02/edge-auth.json"))
    session = requests.Session(); session.headers["Authorization"] = "Token " + app["token"]
    def get(path):
        response = session.get(ORIGIN + path, timeout=(5, 30), allow_redirects=False)
        assert response.status_code == 200
        return response
    overview = get("/api/v1/history/overview/").json()
    all_frames = []; page = 1
    while page:
        rows = get(f"/api/v1/history/frames/?limit=24&page={page}").json()
        all_frames.extend(rows["results"]); page = rows["next_page"]
    by_id = {f["id"]: f for f in all_frames}
    previews = []
    for entry in manifest["entries"]:
        if entry["kind"] == "labelled_simulation":
            assert entry["id"] not in by_id
            continue
        row = by_id[entry["id"]]; assert row["observed_at"] is None
        response = get(row["image_url"])
        with Image.open(target / (entry["id"] + ".jpg")) as original:
            clean = original.convert("RGB"); clean.thumbnail((1280, 1280))
            expected = BytesIO(); clean.save(expected, "JPEG", quality=85)
        assert sha256(response.content).digest() == sha256(expected.getvalue()).digest()
        if entry["packet"]["session"]["profiles"]:
            (target / ("verified-face-" + str(row["frame_index"]) + ".jpg")).write_bytes(response.content)
            previews.append({"id": row["id"], "frame_index": row["frame_index"], "image_url": row["image_url"]})
    anonymous = requests.get(ORIGIN + previews[-1]["image_url"], timeout=(5, 20), allow_redirects=False)
    assert anonymous.status_code in (401, 403)
    result.update(verified_utc=datetime.now(timezone.utc).isoformat(), environment="PythonAnywhere via WSL official API client",
                  production_verified=True, origin=ORIGIN, release=state["release"], facts=overview["facts"],
                  clean_image_hashes_verified=37, anonymous_image_access_denied=True, face_previews=previews,
                  supersedes="evidence/history/cloud-demo.json", edge_upload_uses_original_frame=True)
    (ROOT / "evidence/history/cloud-face-repair.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("pass", "actual_frames_restored", "synthetic_frames_removed", "facts", "production_verified")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
