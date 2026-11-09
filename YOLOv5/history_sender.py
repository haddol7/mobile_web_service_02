"""Send sampled history alongside the required class-appearance photo upload."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import cv2
import requests


class HistoryUploadError(RuntimeError):
    pass


class HistorySender:
    def __init__(self, uploader, tracker, directory, *, source_label, source_kind,
                 recording_started_at=None, interval=10):
        if interval <= 0:
            raise ValueError("History interval must be positive")
        if recording_started_at:
            parsed = datetime.fromisoformat(recording_started_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Recording start requires an explicit timezone")
            recording_started_at = parsed.isoformat()
        self.uploader, self.interval = uploader, interval
        self.directory = Path(directory) / "history-outbox" / tracker.session_id
        self.directory.mkdir(parents=True, exist_ok=True)
        versions = {name: importlib.metadata.version(name) for name in ["norfair", "supervision"]}
        versions["yolov5"] = "7.0"
        profiles = []
        if tracker.faces:
            versions["insightface"] = importlib.metadata.version("insightface")
            versions["face_model"] = tracker.faces.model
            versions["face_policy"] = tracker.faces.policy["version"]
            versions["face_embedding"] = tracker.faces.embedding_mode
            profiles = [{"id": key, "name": name} for key, name in tracker.faces.profile_labels.items()]
        self.config = {"id": tracker.session_id, "source_label": source_label[:80],
                       "source_kind": source_kind, "recording_started_at": recording_started_at,
                       "model_versions": versions, "profiles": profiles}
        self.seen = set()
        self.candidates = {}
        self.last_sample = None
        self.retry_after = 0
        self.sent = 0

    def consider(self, record, image, *, post_id=None, captured_at=None):
        ids = {track["track_id"] for track in record["tracks"]}
        candidates = {face["body_track_id"]: face["candidate_profile_id"] for face in record["faces"]
                      if face.get("body_track_id") is not None and face.get("candidate_profile_id")}
        clock = record["video_seconds"] if record["video_seconds"] is not None else time.monotonic()
        due = self.last_sample is None or clock - self.last_sample >= self.interval
        changed = any(self.candidates.get(key) != value for key, value in candidates.items())
        if (ids and (due or ids-self.seen or changed)) or record["crossings"] or post_id:
            frame = {key: record[key] for key in ["frame_index", "video_seconds", "processed_at_utc",
                                                 "tracks", "faces", "crossings"]}
            if self.config["source_kind"] == "video" and frame["video_seconds"] is None:
                frame["video_seconds"] = 0.0
            frame["captured_at"] = captured_at
            if "image_size" in record:
                frame["image_size"] = record["image_size"]
            packet = {"schema_version": 1, "session": self.config, "frame": frame, "post_id": post_id}
            key = hashlib.sha256(f'{self.config["id"]}:{record["frame_index"]}'.encode()).hexdigest()
            if len(list(self.directory.glob("*.json"))) >= 500:
                raise HistoryUploadError("History outbox is full; retained analysis logs require review")
            height, width = image.shape[:2]
            scale = min(1, 640 / max(height, width))
            preview = cv2.resize(image, (max(1, round(width*scale)), max(1, round(height*scale))))
            ok, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                raise HistoryUploadError("Could not encode history evidence")
            (self.directory / (key+".jpg")).write_bytes(encoded.tobytes())
            temporary = self.directory / (key+".tmp")
            temporary.write_text(json.dumps({"server": self.uploader.base_url, "packet": packet},
                                            allow_nan=False), encoding="utf-8")
            temporary.replace(self.directory / (key+".json"))
            self.last_sample = clock
            self.seen.update(ids)
            self.candidates.update(candidates)
        if time.monotonic() >= self.retry_after:
            pending = sorted(self.directory.glob("*.json"))
            if pending:
                try:
                    self.send_file(self.uploader, pending[0])
                    self.sent += 1
                except (HistoryUploadError, requests.RequestException):
                    self.retry_after = time.monotonic() + 30
                    raise HistoryUploadError("History upload failed; pending packet retained") from None

    @staticmethod
    def send_file(uploader, path):
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["server"] != uploader.base_url:
            raise HistoryUploadError("Outbox server differs from the selected authenticated server")
        packet = saved["packet"]
        expected = hashlib.sha256(f'{packet["session"]["id"]}:{packet["frame"]["frame_index"]}'.encode()).hexdigest()
        image = path.with_suffix(".jpg")
        with image.open("rb") as photo:
            response = uploader.session.post(uploader.base_url + "/api/v1/history/ingest/",
                data={"packet": json.dumps(packet, allow_nan=False)},
                files={"image": ("frame.jpg", photo, "image/jpeg")},
                headers={"Authorization": "Token " + uploader.token, "Accept": "application/json"},
                timeout=(5, 20), allow_redirects=False)
        if response.status_code not in (200, 201) or response.json().get("id") != expected:
            raise HistoryUploadError("History registration was rejected")
        path.unlink()
        image.unlink(missing_ok=True)
