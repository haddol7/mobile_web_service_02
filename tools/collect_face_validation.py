"""Collect a fixed, new-identity cross-video fixture from a pinned public ZIP."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import struct
import time
from urllib.parse import quote
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
import zlib

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "evidence/private/face-validation"
PUBLIC = ROOT / "evidence/person-libraries"
REPO = "mortal9826/VoxCeleb2-test-data"
REVISION = "50ece5fc887f7ca39c41503534e70a3368386f5b"
ARCHIVE_SIZE = 8906971319
URL = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/vox2_test_mp4.zip"
EXCLUDE = {"id00017", "id00061", "id00081"}


def fetch_range(start, size):
    if not 0 < size <= 8*1024**2:
        raise ValueError("Invalid bounded range")
    for attempt in range(3):
        try:
            response = requests.get(URL+"?download=true&range_probe="+str(time.time_ns()),
                headers={"Range":f"bytes={start}-{start+size-1}", "Accept-Encoding":"identity"},
                timeout=(15, 60))
            if response.status_code != 206:
                raise RuntimeError(f"Public archive range HTTP {response.status_code}")
            if not response.headers.get("Content-Range", "").startswith(f"bytes {start}-"):
                raise ValueError("Archive range was not honored")
            if len(response.content) != size:
                raise ValueError("Incomplete archive range")
            return response.content
        except (requests.RequestException, RuntimeError, ValueError):
            if attempt == 2:
                raise RuntimeError("Bounded public archive download failed") from None
            time.sleep(attempt+1)


class RangeReader(io.RawIOBase):
    def __init__(self):
        self.position, self.downloaded = 0, 0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position+offset if whence == 1 else ARCHIVE_SIZE+offset
        if not 0 <= self.position <= ARCHIVE_SIZE:
            raise ValueError("Invalid ZIP index seek")
        return self.position
    def read(self, size=-1):
        if size < 0: size = ARCHIVE_SIZE-self.position
        size = min(size, ARCHIVE_SIZE-self.position)
        if not size: return b""
        if self.downloaded+size > 12*1024**2:
            raise ValueError("ZIP index budget exceeded")
        result = fetch_range(self.position, size)
        self.position += size
        self.downloaded += size
        return result


def decode(path):
    cap = cv2.VideoCapture(str(path))
    assert cap.isOpened()
    expected = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    count, shape = 0, None
    while True:
        ok, frame = cap.read()
        if not ok: break
        shape = frame.shape[:2]
        count += 1
    cap.release()
    assert count == expected and count >= 3 and fps > 0
    return {"frames":count, "fps":fps, "width":shape[1], "height":shape[0], "full_decode_pass":True}


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in the project WSL virtualenv.")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    metadata_path = PRIVATE/"collection.json"
    if metadata_path.exists():
        saved = json.loads(metadata_path.read_text())
        for item in saved["clips"]:
            assert hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest() == item["sha256"]
        print(json.dumps({"reused_verified_fixture":True,"clips":len(saved["clips"])}))
        return
    reader = RangeReader()
    people = defaultdict(lambda:defaultdict(list))
    with ZipFile(reader) as archive:
        for item in archive.infolist():
            parts = Path(item.filename).parts
            if item.filename.endswith(".mp4") and len(parts) >= 3 and parts[-3] not in EXCLUDE and item.file_size <= 2*1024**2:
                people[parts[-3]][parts[-2]].append(item)
    eligible = sorted(identity for identity, groups in people.items() if len(groups) >= 3)
    assert len(eligible) >= 18
    known, unknown = eligible[:12], eligible[12:18]
    selected = []
    for identity in known+unknown:
        sources = sorted(people[identity])
        for index, source in enumerate(sources[:3] if identity in known else sources[:2]):
            item = min(people[identity][source], key=lambda m:(m.file_size,m.filename))
            selected.append({"identity":identity, "source_video_id":source,
                "role":"reference" if identity in known and index==0 else "query",
                "enrolled":identity in known, "member":item.filename, "header_offset":item.header_offset,
                "compressed_size":item.compress_size, "bytes":item.file_size,
                "crc":item.CRC, "compression":item.compress_type})
    assert len(selected) == 48
    planned = sum(item["compressed_size"]+4096 for item in selected)+reader.downloaded
    assert planned <= 64*1024**2
    (PRIVATE/"selection.json").write_text(json.dumps({"known":known, "unknown":unknown, "clips":selected},indent=2)+"\n")
    def download(item):
        requested = min(item["compressed_size"]+4096, ARCHIVE_SIZE-item["header_offset"])
        blob = fetch_range(item["header_offset"], requested)
        header = struct.unpack("<4s5H3I2H", blob[:30])
        assert header[0] == b"PK\x03\x04" and not header[2]&1
        offset = 30+header[-2]+header[-1]
        compressed = blob[offset:offset+item["compressed_size"]]
        assert len(compressed) == item["compressed_size"]
        if item["compression"] == ZIP_STORED: raw = compressed
        elif item["compression"] == ZIP_DEFLATED: raw = zlib.decompress(compressed,-15)
        else: raise ValueError("Unsupported archive compression")
        assert len(raw) == item["bytes"] and (zlib.crc32(raw)&0xffffffff) == item["crc"]
        filename = hashlib.sha256(raw).hexdigest()+".mp4"
        destination = PRIVATE/filename
        destination.write_bytes(raw)
        return {**item, "path":str(destination.relative_to(ROOT)), "sha256":filename[:-4],
                "decode":decode(destination), "range_bytes_read":requested}
    clips = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download,item) for item in selected]
        for future in as_completed(futures):
            clips.append(future.result())
            print(json.dumps({"downloaded":len(clips), "selected":len(selected)}),flush=True)
    clips.sort(key=lambda x:(x["identity"],x["role"],x["source_video_id"]))
    assert len({c["sha256"] for c in clips}) == len(clips), "Duplicate video content in split"
    result = {"collected_utc":datetime.now(timezone.utc).isoformat(), "environment":"WSL Ubuntu",
        "dataset":REPO, "revision":REVISION, "archive":"vox2_test_mp4.zip",
        "source":"https://huggingface.co/datasets/"+REPO,
        "original_project":"https://www.robots.ox.ac.uk/~vgg/data/voxceleb/",
        "selection_policy":"First 18 sorted identities with at least 3 source-video IDs and small clips, excluding all 3 earlier identities.",
        "excluded_previous_identities":sorted(EXCLUDE), "enrolled_identities":known, "unknown_identities":unknown,
        "clips":clips, "clip_count":len(clips), "identity_count":18,
        "query_clip_count":sum(c["role"]=="query" for c in clips),
        "total_source_frames_decoded":sum(c["decode"]["frames"] for c in clips),
        "archive_bytes_read":reader.downloaded+sum(c["range_bytes_read"] for c in clips),
        "full_archive_downloaded":False, "login_required":False, "training_performed":False,
        "capture_dates_known":False, "different_source_video_ids_verified":True,
        "different_recording_sessions_proven":False, "identity_matching_measured":False}
    metadata_path.write_text(json.dumps(result,indent=2)+"\n")
    public = {k:v for k,v in result.items() if k not in ["clips","enrolled_identities","unknown_identities"]}
    public["source_video_groups"] = [{"identity":identity,"enrolled":identity in known,
        "reference_sources":[c["source_video_id"] for c in clips if c["identity"]==identity and c["role"]=="reference"],
        "query_sources":[c["source_video_id"] for c in clips if c["identity"]==identity and c["role"]=="query"]}
        for identity in known+unknown]
    (PUBLIC/"expanded-face-collection.json").write_text(json.dumps(public,indent=2)+"\n")
    print(json.dumps({"complete":True,"people":18,"clips":48,"source_frames":result["total_source_frames_decoded"],
                     "bytes_read":result["archive_bytes_read"]}),flush=True)


if __name__ == "__main__":
    main()
