"""Send newly appearing object classes to the assessed Django photo API."""
from datetime import datetime, timezone
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import requests


class UploadError(RuntimeError):
    pass


class ChangeDetection:
    def __init__(self, names, *, base_url=None, session=None, token=None):
        self.names = dict(enumerate(names)) if isinstance(names, (list, tuple)) else dict(names)
        if sorted(self.names) != list(range(len(self.names))):
            raise ValueError("Class IDs must be consecutive integers starting at zero")
        self.base_url = (base_url or os.environ.get("YOLO_SERVER", "")).rstrip("/")
        parsed = urlparse(self.base_url)
        local = parsed.hostname in {"127.0.0.1", "localhost", "10.0.2.2", "::1"}
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Provide an HTTP(S) server URL without credentials or a query")
        if parsed.scheme == "http" and not local:
            raise ValueError("Remote servers must use HTTPS")
        self.session = session or requests.Session()
        self.token = token or os.environ.get("YOLO_API_TOKEN")
        self._previous = {}
        if not self.token:
            user, password = os.environ.get("YOLO_USERNAME"), os.environ.get("YOLO_PASSWORD")
            if not user or not password:
                raise ValueError("Set YOLO_API_TOKEN or YOLO_USERNAME and YOLO_PASSWORD privately")
            response = self.session.post(self.base_url + "/api-token-auth/", data={"username": user, "password": password}, timeout=(5, 20), allow_redirects=False)
            if response.status_code != 200:
                raise UploadError(f"Authentication failed (HTTP {response.status_code})")
            self.token = response.json().get("token")
            if not isinstance(self.token, str) or not self.token:
                raise UploadError("The server did not return an authentication token")

    def add(self, names, detected_current, save_dir, image, *, stream_id="default"):
        current = tuple(int(bool(value)) for value in detected_current)
        if len(current) != len(self.names):
            raise ValueError("Detection vector size does not match class names")
        previous = self._previous.get(stream_id, (0,) * len(current))
        appeared = [i for i, value in enumerate(current) if value and not previous[i]]
        self._previous[stream_id] = current
        if not appeared:
            return None
        return self.send(save_dir, image, appeared)

    def send(self, save_dir, image, appeared):
        import cv2

        now = datetime.now(timezone.utc)
        folder = Path(save_dir) / "detected" / now.strftime("%Y/%m/%d")
        folder.mkdir(parents=True, exist_ok=True)
        filename = folder / (now.strftime("%H%M%S") + "-" + uuid4().hex + ".jpg")
        if not cv2.imwrite(str(filename), cv2.resize(image, (320, 240), interpolation=cv2.INTER_AREA)):
            raise UploadError("Could not save the detected frame")
        labels = [self.names[i] for i in appeared]
        fields = {"title": ("YOLO: " + ", ".join(labels))[:200],
                  "text": "New objects: " + ", ".join(labels) + "\nDetected at " + now.isoformat()}
        with filename.open("rb") as photo:
            response = self.session.post(self.base_url + "/api_root/Post/", data=fields,
                                         files={"image": (filename.name, photo, "image/jpeg")},
                                         headers={"Authorization": "Token " + self.token, "Accept": "application/json"},
                                         timeout=(5, 25), allow_redirects=False)
        if response.status_code != 201:
            raise UploadError(f"Photo registration failed (HTTP {response.status_code}); frame retained locally")
        record = response.json()
        if not isinstance(record, dict) or not isinstance(record.get("id"), int):
            raise UploadError("Unexpected photo registration response")
        return {"post_id": record["id"], "classes": labels, "local_image": str(filename)}
