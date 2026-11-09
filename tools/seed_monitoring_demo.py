"""Add explicitly labelled, resumable demonstration history through the owner API.

Real detections retain unknown recording dates. Synthetic timelines use diagram
images and no fabricated face scores. Existing posts and records are preserved.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import UUID, uuid5, NAMESPACE_URL

from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/private/cloud-demo/v1"
REPORT = ROOT / "evidence/history/cloud-demo.json"
ORIGIN = "https://daejinha.pythonanywhere.com"


def digest(value):
    return sha256(value).hexdigest()


def identifier(session, frame):
    return digest(f"{UUID(session).hex}:{frame}".encode())


def diagrams(person, timestamp, direction):
    image = Image.new("RGB", (640, 400), "#eef3f7")
    draw = ImageDraw.Draw(image)
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    regular = ImageFont.truetype(font, 19)
    heading = ImageFont.truetype(font, 27)
    color = {"A": "#176b71", "B": "#345d99", "C": "#95651b"}[person]
    draw.rectangle((0, 0, 640, 58), fill="#173349")
    draw.text((22, 15), "SIMULATED OBSERVATION", font=heading, fill="white")
    draw.rectangle((28, 84, 612, 300), outline="#c3d0dc", width=2)
    draw.line((320, 85, 320, 298), fill="#91a5b6", width=3)
    x = 230 if direction == "in" else 410
    draw.ellipse((x-25, 117, x+25, 167), fill=color)
    draw.rounded_rectangle((x-33, 177, x+33, 257), radius=16, fill=color)
    draw.text((45, 97), f"PERSON {person} / {direction.upper()}", font=regular, fill="#173349")
    draw.text((30, 318), timestamp.strftime("%Y-%m-%d %H:%M KST"), font=heading, fill="#173349")
    draw.text((30, 361), "Demo timeline. No camera inference or face matching.", font=regular, fill="#607485")
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def prepare():
    manifest = OUT / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    fixture = ROOT / json.loads((ROOT / "evidence/history/latest-fixture.json").read_text())["fixture"]
    assert fixture.resolve().is_relative_to((ROOT / "evidence/private/history").resolve())
    db = sqlite3.connect("file:" + str(fixture / "db.sqlite3") + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    logs = {}
    for path in fixture.glob("*/person-analysis/*.jsonl"):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            logs[(UUID(row["session_id"]).hex, row["frame_index"])] = row
    configurations = {}
    for row in db.execute("SELECT id,configuration FROM blog_trackingsession"):
        config = json.loads(row["configuration"])
        config["id"] = uuid5(NAMESPACE_URL, "monitoring-demo-v1/actual/" + row["id"]).hex
        face = bool(config["profiles"])
        config["source_label"] = "[모델검증] 얼굴 영상 / 촬영일 미상" if face else "[모델검증] 보행자 영상 / 촬영일 미상"
        config["model_versions"]["demo_provenance"] = "actual_inference_replay_v1"
        profile_map = {p["id"]: "sample-v1-" + p["id"] for p in config["profiles"]}
        for index, profile in enumerate(config["profiles"], 1):
            profile.update(id=profile_map[profile["id"]], name=f"[검증] 등록 인물 {index}")
        configurations[row["id"]] = (config, profile_map)
    entries = []
    for row in db.execute("SELECT session_id,frame_index,image FROM blog_trackingframe ORDER BY processed_at,frame_index"):
        original = logs[(row["session_id"], row["frame_index"])]
        config, profile_map = configurations[row["session_id"]]
        frame = {key: original[key] for key in ("frame_index", "video_seconds", "processed_at_utc", "tracks", "faces", "crossings")}
        frame = json.loads(json.dumps(frame))
        frame["captured_at"] = None
        for face in frame["faces"]:
            if face["candidate_profile_id"]:
                face["candidate_profile_id"] = profile_map[face["candidate_profile_id"]]
        for event in frame["crossings"]:
            event["event_id"] = digest(f'{config["id"]}:{event["track_id"]}:{frame["frame_index"]}:{event["direction"]}'.encode())
        key = identifier(config["id"], frame["frame_index"])
        source = (fixture / "history-images" / row["image"]).resolve()
        assert source.is_relative_to((fixture / "history-images").resolve())
        (OUT / (key + ".jpg")).write_bytes(source.read_bytes())
        entries.append({"id": key, "kind": "actual_model_validation", "packet": {"schema_version": 1, "session": config, "frame": frame, "post_id": None}})
    db.close()
    assert len(entries) == 37
    korea = timezone(timedelta(hours=9))
    cases = [(5, 9, 10, "A", "confirmed"), (5, 14, 20, "B", "confirmed"),
             (6, 10, 5, "A", "confirmed"), (6, 15, 30, "C", "unreviewed"),
             (7, 11, 15, "B", "confirmed"), (7, 16, 40, "A", "confirmed"),
             (8, 9, 25, "C", "confirmed"), (8, 17, 50, "A", "unknown")]
    profiles = [{"id": "demo-v1-person-" + p.lower(), "name": "[시연] 인물 " + p} for p in "ABC"]
    now = datetime.now(timezone.utc)
    for index, (day, hour, minute, person, review) in enumerate(cases):
        session_id = uuid5(NAMESPACE_URL, f"monitoring-demo-v1/timeline/{index}").hex
        start = datetime(2026, 11, day, hour, minute, tzinfo=korea)
        config = {"id": session_id, "source_label": f"[시연] 날짜 조회 {start:%m.%d %H:%M}", "source_kind": "video",
                  "recording_started_at": start.isoformat(), "profiles": profiles,
                  "model_versions": {"pipeline": "diagram_timeline_simulation_v1", "inference": "not_executed"}}
        for frame_index, seconds, direction in [(1, 0, "in"), (2, 120, "out")]:
            key = identifier(session_id, frame_index)
            frame = {"frame_index": frame_index, "video_seconds": seconds,
                "processed_at_utc": (now + timedelta(milliseconds=index*2+frame_index)).isoformat(), "captured_at": None,
                "tracks": [{"track_id": 1, "bbox": [190, 105, 460, 270]}], "faces": [],
                "crossings": [{"event_id": digest(f"{session_id}:1:{frame_index}:{direction}".encode()), "track_id": 1, "direction": direction}]}
            (OUT / (key + ".jpg")).write_bytes(diagrams(person, start + timedelta(seconds=seconds), direction))
            entries.append({"id": key, "kind": "labelled_simulation", "review": review, "profile": "demo-v1-person-" + person.lower(),
                            "packet": {"schema_version": 1, "session": config, "frame": frame, "post_id": None}})
    manifest.write_text(json.dumps({"version": 1, "entries": entries}, ensure_ascii=False, indent=2) + "\n")
    return {"version": 1, "entries": entries}


def run():
    raise SystemExit("Retired: diagram records obscured real faces. Use tools/repair_history_demo.py to restore actual video evidence; do not re-seed the simulated timeline.")
    if not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in the project WSL virtualenv.")
    sys.path.insert(0, str(ROOT / "tools/deployment"))
    import pythonanywhere_auth as auth
    credentials = json.loads(auth.private_read(Path.home() / ".config/mobile-web-service/common02/edge-auth.json"))
    assert credentials["base_url"] == ORIGIN and credentials["username"] == "daejinha"
    data = prepare()
    state_path = OUT / "import-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"accepted": [], "reviews": [], "baseline": None}
    session = requests.Session()
    session.headers.update(Authorization="Token " + credentials["token"])
    def call(method, path, **kwargs):
        response = session.request(method, ORIGIN + path, timeout=(5, 30), allow_redirects=False, **kwargs)
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Demo API {method} {path} returned {response.status_code}; no existing data was deleted.")
        return response.json()
    def checkpoint():
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(state_path)
    def posts():
        return call("GET", "/api_root/Post/")
    if state["baseline"] is None:
        before = posts()
        image_hashes = {}
        for post in before:
            assert post["image"].startswith(ORIGIN + "/")
            response = session.get(post["image"], timeout=(5, 30), allow_redirects=False)
            assert response.status_code == 200
            image_hashes[str(post["id"])] = digest(response.content)
        state["baseline"] = {"posts": before, "images": image_hashes, "overview": call("GET", "/api/v1/history/overview/")}
        checkpoint()
    for index, entry in enumerate(data["entries"], 1):
        if entry["id"] in state["accepted"]:
            continue
        raw = (OUT / (entry["id"] + ".jpg")).read_bytes()
        result = call("POST", "/api/v1/history/ingest/", data={"packet": json.dumps(entry["packet"], ensure_ascii=False)},
                      files={"image": ("observation.jpg", raw, "image/jpeg")})
        assert result["id"] == entry["id"]
        state["accepted"].append(entry["id"]); checkpoint()
        if index % 8 == 0:
            print(json.dumps({"uploaded": index, "total": len(data["entries"])}), flush=True)
    all_frames = []
    page = 1
    while page:
        result = call("GET", f"/api/v1/history/frames/?page={page}&limit=24")
        all_frames.extend(result["results"]); page = result["next_page"]
    by_id = {row["id"]: row for row in all_frames}
    imported = {entry["id"] for entry in data["entries"]}
    assert imported <= set(by_id)
    reviewed = set()
    for entry in data["entries"]:
        if entry["kind"] != "labelled_simulation" or entry["review"] == "unreviewed":
            continue
        track = by_id[entry["id"]]["tracks"][0]
        if track["id"] in reviewed:
            continue
        reviewed.add(track["id"])
        if track["id"] in state["reviews"]:
            continue
        profile = entry["profile"] if entry["review"] == "confirmed" else None
        call("PATCH", f'/api/v1/history/tracks/{track["id"]}/', json={"revision": track["revision"], "profile": profile})
        state["reviews"].append(track["id"]); checkpoint()
    after = posts()
    assert after == state["baseline"]["posts"], "Existing public posts changed during import"
    for post in after:
        assert post["image"].startswith(ORIGIN + "/")
        response = session.get(post["image"], timeout=(5, 30), allow_redirects=False)
        assert response.status_code == 200 and digest(response.content) == state["baseline"]["images"][str(post["id"]) ]
    overview = call("GET", "/api/v1/history/overview/")
    before = state["baseline"]["overview"]["facts"]
    expected = {"sampled_frames": 53, "observed_tracks": 31, "passages": 22, "sessions": 10, "profiles": 5, "confirmed_tracks": 6, "pending_tracks": 1, "unknown_date_frames": 37}
    for key, value in expected.items():
        assert overview["facts"][key] == before[key] + value, f"Unexpected imported total: {key}"
    assert all(by_id[e["id"]]["observed_at"] is None for e in data["entries"] if e["kind"] == "actual_model_validation")
    questions = []
    for value in [
        {"question": "언제 나타났고 몇 번 통과했어?"},
        {"question": "몇 번 통과했어?", "profile": "demo-v1-person-a"},
        {"question": "어제 몇 번 통과했어?", "start": "2026-11-07", "end": "2026-11-07"},
        {"question": "기록을 확인해줘", "start": "2026-11-09", "end": "2026-11-09"},
    ]:
        answer = call("POST", "/api/v1/history/ask/", json=value)
        questions.append({"request": value, "facts": answer["facts"], "evidence_ids": [e["id"] for e in answer["evidence"]]})
    assert questions[0]["facts"]["passages"] == before["passages"] + 22
    assert questions[1]["facts"]["observed_tracks"] == 3 and questions[1]["facts"]["passages"] == 6
    assert questions[2]["facts"]["passages"] == 4 and questions[2]["facts"]["unknown_date_frames"] == 0
    assert questions[3]["facts"]["sampled_frames"] == 0
    actual_frame = next(e for e in data["entries"] if e["kind"] == "actual_model_validation")
    replay = call("POST", "/api/v1/history/ingest/", data={"packet": json.dumps(actual_frame["packet"], ensure_ascii=False)},
                  files={"image": ("observation.jpg", (OUT / (actual_frame["id"] + ".jpg")).read_bytes(), "image/jpeg")})
    assert replay["created"] is False
    image_ids = [data["entries"][0]["id"], data["entries"][-1]["id"]]
    images = []
    for frame_id in image_ids:
        target = ORIGIN + by_id[frame_id]["image_url"]
        response = session.get(target, timeout=(5, 30), allow_redirects=False)
        assert response.status_code == 200
        with Image.open(BytesIO(response.content)) as image:
            image.verify()
        anonymous = requests.get(target, timeout=(5, 20), allow_redirects=False)
        assert anonymous.status_code in (401, 403)
        images.append({"frame_id": frame_id, "sha256": digest(response.content), "anonymous_denied": True})
    result = {"verified_utc": datetime.now(timezone.utc).isoformat(), "origin": ORIGIN,
        "actual_model_records_added": 37, "labelled_simulation_records_added": 16, "simulation_sessions": 8,
        "confirmed_simulation_tracks": 6, "production_verified": True, "existing_posts_and_photos_preserved": True,
        "unknown_dates_preserved": True, "duplicate_replay_did_not_add_records": True,
        "facts": overview["facts"], "profiles": overview["profiles"], "questions": questions,
        "private_images_verified": images, "paid_llm_calls": 0, "pass": True}
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("pass", "actual_model_records_added", "labelled_simulation_records_added", "facts", "existing_posts_and_photos_preserved")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    run()
