"""Preview stored real observations locally without running inference or remote APIs."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PhotoBlogServer"))
from blog.history_annotations import render_overlay


def main():
    assert os.environ.get("WSL_DISTRO_NAME"), "Use WSL"
    data = json.loads((ROOT / "evidence/private/cctv-walking/people/packets.json").read_text())
    entry = max(data["entries"], key=lambda row: sum(face["body_track_id"] is not None for face in row["packet"]["frame"]["faces"]))
    packet = entry["packet"]
    names = {row["id"]: row["name"] for row in packet["session"]["profiles"]}
    frame = packet["frame"]
    observations = []
    for body in frame["tracks"]:
        matches = [face for face in frame["faces"] if face["body_track_id"] == body["track_id"]]
        face = matches[0] if len(matches) == 1 else None
        key = face["candidate_profile_id"] if face else None
        observations.append(SimpleNamespace(bbox=body["bbox"], face_bbox=face["bbox"] if face else None,
            candidate_id=key, candidate=SimpleNamespace(display_name=names.get(key)),
            similarity=face["similarity"] if face else None,
            track=SimpleNamespace(track_id=body["track_id"], confirmed_id=None, reviewed_at=None)))
    with Image.open(ROOT / entry["image"]) as image:
        rendered, count = render_overlay(image, frame["image_size"], observations,
            [face for face in frame["faces"] if face["body_track_id"] is None])
    output = ROOT / "evidence/private/detection-boxes"
    output.mkdir(parents=True, exist_ok=True)
    rendered.save(output / "preview.jpg", quality=95)
    print(json.dumps({"pass": True, "boxes": count, "size": list(rendered.size), "paid_api_calls": 0}))


if __name__ == "__main__":
    main()
