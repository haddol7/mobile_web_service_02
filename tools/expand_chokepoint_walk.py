"""Collect four official portal recordings, run real local models, and prepare private observations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time
from uuid import NAMESPACE_URL, uuid5

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/private/cctv-walking/expanded"
ORIGINAL = ROOT / "evidence/private/cctv-walking/chokepoint"
CASES = [
    {"sequence":"P1E_S2", "camera":"P1E_S2_C2", "md5":"bc58ad9ef36ceb92da592cb092353d55", "label":"출입구 1 / 입장 보행 / 구간 2"},
    {"sequence":"P1L_S1", "camera":"P1L_S1_C1", "md5":"5673a77c62b4e70d0f6871d1635df367", "label":"출입구 1 / 퇴장 보행 / 구간 1"},
    {"sequence":"P2E_S5", "camera":"P2E_S5_C2", "md5":"e6bca312e40ebebdfb709f2315eebf80", "label":"출입구 2 / 혼잡 입장 / 구간 5"},
    {"sequence":"P2L_S5", "camera":"P2L_S5_C2", "md5":"14b28f3d83a75b62d3aa6ad5ee117843", "label":"출입구 2 / 혼잡 퇴장 / 구간 5"},
]
NOTICE = "NICTA ChokePoint; Wong et al., CVPRW 2011. Reconstructed available JPEGs at 30 fps; replay times are not capture timestamps."


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")


def emit(**value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def file_hash(path, algorithm="sha256"):
    result = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            result.update(block)
    return result.hexdigest()


def download_archive(url,archive,expected):
    part=archive.with_suffix(".part")
    start=part.stat().st_size if part.exists() else 0
    probe=requests.get(url,headers={"Range":f"bytes={start}-{start}"},timeout=(15,30))
    probe.raise_for_status()
    match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",probe.headers.get("Content-Range",""))
    assert probe.status_code==206 and match and int(match[1])==start and len(probe.content)==1
    total=int(match[3]);assert start<total<1100*1024**2
    ranges=[(offset,min(total-1,offset+16*1024**2-1)) for offset in range(start,total,16*1024**2)]

    def segment(bounds):
        left,right=bounds
        target=archive.with_name(archive.name+f".range-{left}-{right}")
        if target.exists() and target.stat().st_size==right-left+1:
            return target
        for attempt in range(2):
            try:
                response=requests.get(url,headers={"Range":f"bytes={left}-{right}"},timeout=(15,30))
                response.raise_for_status()
                assert response.status_code==206 and response.headers.get("Content-Range")==f"bytes {left}-{right}/{total}"
                assert len(response.content)==right-left+1
                target.write_bytes(response.content)
                emit(stage="range_download",file=archive.name,start=left,bytes=len(response.content))
                return target
            except requests.RequestException:
                if attempt:
                    raise
                time.sleep(1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        segments=list(pool.map(segment,ranges))
    with part.open("ab" if start else "wb") as target:
        for source in segments:
            with source.open("rb") as incoming:
                import shutil
                shutil.copyfileobj(incoming,target,1024*1024)
    assert part.stat().st_size==total and file_hash(part,"md5")==expected
    part.replace(archive)


def collect_case(case):
    folder = OUT / case["camera"]
    folder.mkdir(parents=True, exist_ok=True)
    archive = OUT / (case["sequence"]+".tar.xz")
    url = "https://zenodo.org/records/815657/files/"+archive.name+"?download=1"
    if not archive.exists():
        if archive.with_suffix(".part").exists():
            download_archive(url,archive,case["md5"])
    if not archive.exists():
        part = archive.with_suffix(".part")
        start = part.stat().st_size if part.exists() else 0
        with requests.get(url, headers={"Range":f"bytes={start}-"} if start else {}, stream=True, timeout=(15,90)) as response:
            response.raise_for_status()
            append = start > 0 and response.status_code == 206
            if not append:
                start = 0
            total = start
            last = total//(64*1024**2)
            with part.open("ab" if append else "wb") as target:
                for block in response.iter_content(1024*1024):
                    total += len(block)
                    assert total < 1100*1024**2, "Unexpected archive size"
                    target.write(block)
                    if total//(64*1024**2) > last:
                        last = total//(64*1024**2)
                        emit(stage="download", sequence=case["sequence"], megabytes=round(total/1024**2))
        assert file_hash(part,"md5") == case["md5"], "Official archive checksum mismatch"
        part.replace(archive)
    assert file_hash(archive,"md5") == case["md5"]
    cached=folder/"collection.json"
    if cached.exists():
        record=json.loads(cached.read_text())
        assert record["official_md5_verified"] and file_hash(ROOT/record["video"])==record["video_sha256"]
        emit(stage="collection_reused",camera=case["camera"])
        return record
    nested = folder / (case["camera"]+".tar.xz")
    if not nested.exists():
        with tarfile.open(archive) as bundle:
            selected = [member for member in bundle if member.isfile() and Path(member.name).name == nested.name]
            assert len(selected) == 1
            with bundle.extractfile(selected[0]) as source, nested.open("wb") as target:
                import shutil
                shutil.copyfileobj(source,target,1024*1024)
    images = folder / "images"
    images.mkdir(exist_ok=True)
    names = []
    with tarfile.open(nested) as bundle:
        for member in bundle:
            if not member.isfile() or not member.name.lower().endswith(".jpg"):
                continue
            name = Path(member.name).name
            assert name[:-4].isdigit() and member.size < 2*1024**2
            raw = bundle.extractfile(member).read()
            assert len(raw) == member.size
            destination = images/name
            if not destination.exists():
                destination.write_bytes(raw)
            assert destination.read_bytes() == raw
            names.append(name)
    names.sort()
    assert len(names) == len(set(names)) and len(names)>100
    truth_archive = ORIGINAL / "groundtruth.tar.xz"
    assert file_hash(truth_archive,"md5") == "5c9d4d38a1c614905fe48da48ecdf06c"
    with tarfile.open(truth_archive) as bundle:
        selected = [member for member in bundle if member.isfile() and Path(member.name).name == case["camera"]+".xml"]
        assert len(selected)<=1
        if selected:
            assert selected[0].size < 4*1024**2
            (folder/"groundtruth.xml").write_bytes(bundle.extractfile(selected[0]).read())
        else:
            # The official groundtruth archive has no S5 crowd annotations.
            assert case["sequence"] in {"P2E_S5","P2L_S5"}
        ground_truth_available=bool(selected)
    video = folder / (case["camera"]+".mp4")
    if not video.exists():
        writer = cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*"mp4v"),30,(800,600))
        assert writer.isOpened()
        for index,name in enumerate(names):
            image = cv2.imread(str(images/name))
            assert image is not None and image.shape[:2] == (600,800)
            writer.write(image)
            if index in {len(names)//4,len(names)//2,3*len(names)//4}:
                assert cv2.imwrite(str(folder/f"preview-{index}.jpg"),image)
        writer.release()
    capture = cv2.VideoCapture(str(video))
    count = 0
    while True:
        ok,image = capture.read()
        if not ok:
            break
        assert image.shape[:2] == (600,800)
        count += 1
    capture.release()
    assert count == len(names)
    record = {**case, "url":url, "archive_bytes":archive.stat().st_size, "archive_sha256":file_hash(archive),
              "official_md5_verified":True, "video":video.relative_to(ROOT).as_posix(), "video_sha256":file_hash(video),
              "images":names, "frames":count, "fps":30, "size":[800,600], "full_decode_pass":True,
              "ground_truth_available":ground_truth_available,
              "capture_date_known":False, "derivative_notice":NOTICE}
    save(folder/"collection.json",record)
    emit(stage="collected",camera=case["camera"],frames=count)
    return record


def collect():
    OUT.mkdir(parents=True, exist_ok=True)
    # Two independent archive transfers; original publisher checksums remain mandatory.
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(collect_case,CASES))
    proof = {"pass":True,"verified_utc":stamp(),"environment":"WSL Ubuntu","source":"https://zenodo.org/records/815657",
             "new_recordings":4,"independent_camera_views_counted_as_recordings":False,
             "total_archive_bytes":sum(row["archive_bytes"] for row in records),
             "cases":[{key:value for key,value in row.items() if key!="images"} for row in records],
             "model_training_performed":False,"actual_paid_api_calls":0}
    save(ROOT/"evidence/history/chokepoint-expanded-collection.json",proof)


def analyze(camera=None):
    references = ROOT/"evidence/private/public-figure-demo/references.json"
    assert len(json.loads(references.read_text())["profiles"]) == 5
    records = []
    for case in CASES:
        if camera and case["camera"] != camera:
            continue
        folder = OUT/case["camera"]
        info = json.loads((folder/"collection.json").read_text())
        stride = max(10,math.ceil(info["frames"]/180))
        completed = folder/"inference.json"
        if completed.exists():
            record = json.loads(completed.read_text())
            assert record["video_sha256"] == file_hash(ROOT/info["video"])
            records.append(record)
            continue
        command = [sys.executable,str(ROOT/"tools/run_edge.py"),"--source",str(ROOT/info["video"]),"--device","cpu",
                   "--classes","0","--person-tracking","--face-references",str(references),"--face-stride","1",
                   "--vid-stride",str(stride),"--project",str(folder),"--name","analysis","--exist-ok","--nosave"]
        emit(stage="inference_started",camera=case["camera"],video_stride=stride)
        with (folder/"model.log").open("w") as output:
            result = subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,timeout=900)
        assert result.returncode == 0, "Inspect private model.log"
        logs = list((folder/"analysis/person-analysis").glob("*.jsonl"))
        assert len(logs) == 1
        rows = [json.loads(line) for line in logs[0].read_text().splitlines()]
        assert rows and len({row["frame_index"] for row in rows}) == len(rows)
        faces = [face for row in rows for face in row["faces"]]
        linked = [face for face in faces if face["body_track_id"] is not None]
        candidates = [face for face in faces if face["candidate_profile_id"]]
        record = {"camera":case["camera"],"video_sha256":info["video_sha256"],"frames_analyzed":len(rows),
                  "faces_detected":len(faces),"linked_faces":len(linked),"candidate_faces":len(candidates),
                  "distinct_body_tracks":len({track["track_id"] for row in rows for track in row["tracks"]}),
                  "video_stride":stride,"log":logs[0].relative_to(ROOT).as_posix(),"references_compared":5,
                  "no_training":True,"capture_date_known":False,"verified_utc":stamp()}
        save(completed,record)
        records.append(record)
        emit(stage="inference_finished",**record)
    records = [json.loads((OUT/case["camera"]/"inference.json").read_text()) for case in CASES
               if (OUT/case["camera"]/"inference.json").exists()]
    if len(records)!=4:
        emit(stage="partial_inference",recordings_complete=len(records))
        return
    save(ROOT/"evidence/history/chokepoint-expanded-inference.json",{
        "pass":True,"verified_utc":stamp(),"environment":"WSL Ubuntu CPU","cases":records,
        "frames_analyzed":sum(row["frames_analyzed"] for row in records),
        "faces_detected":sum(row["faces_detected"] for row in records),
        "actual_embedding_api_calls":0,"actual_llm_api_calls":0})


def prepare():
    references = json.loads((ROOT/"evidence/private/public-figure-demo/references.json").read_text())
    profiles = [{"id":profile["id"],"name":profile["name"]} for profile in references["profiles"]]
    entries = []
    cases = []
    licence = (ROOT/"docs/testing/licenses/ChokePoint.txt").read_bytes()
    (OUT/"CHOKEPOINT_LICENSE.txt").write_bytes(licence)
    for case in CASES:
        folder = OUT/case["camera"]
        (folder/"CHOKEPOINT_LICENSE.txt").write_bytes(licence)
        info = json.loads((folder/"collection.json").read_text())
        analysis = json.loads((folder/"inference.json").read_text())
        rows = [json.loads(line) for line in (ROOT/analysis["log"]).read_text().splitlines()]
        # Do not quietly publish a face that the model confused with a registered reference.
        useful = [row for row in rows if row["tracks"] and not any(face["candidate_profile_id"] for face in row["faces"])]
        assert len(useful)>=6, "Not enough genuine unresolved observations"
        faced = [row for row in useful if any(face["body_track_id"] is not None for face in row["faces"])]
        if len(faced)>=6:
            useful = faced
        selected = {useful[round((len(useful)-1)*n/9)]["frame_index"] for n in range(10)}
        faced = [row for row in useful if any(face["body_track_id"] is not None for face in row["faces"])]
        for n in range(min(8,len(faced))):
            selected.add(faced[round((len(faced)-1)*n/max(1,min(8,len(faced))-1))]["frame_index"])
        session = uuid5(NAMESPACE_URL,"chokepoint-expanded-v1/"+info["video_sha256"]).hex
        config = {"id":session,"source_label":case["label"],"source_kind":"video","recording_started_at":None,
                  "model_versions":{"yolov5":"7.0","face_model":"buffalo_l","face_policy":"candidate-2",
                                    "demo_provenance":"NICTA ChokePoint, Wong et al. CVPRW 2011; available-frame reconstruction"},
                  "profiles":profiles,"purpose":"demo","source_reference":"ChokePoint/"+case["camera"]+"/available-frames"}
        image_folder = folder/"observations"
        image_folder.mkdir(exist_ok=True)
        mapping = []
        for row in useful:
            if row["frame_index"] not in selected:
                continue
            original_index = round(row["video_seconds"]*30)
            name = info["images"][original_index]
            image = cv2.imread(str(folder/"images"/name))
            assert image is not None
            frame = {key:row[key] for key in ("frame_index","video_seconds","processed_at_utc","tracks","faces","crossings","image_size")}
            assert not frame["crossings"]
            frame["captured_at"] = None
            packet = {"schema_version":1,"session":config,"frame":frame,"post_id":None}
            key = hashlib.sha256(f'{session}:{row["frame_index"]}'.encode()).hexdigest()
            path = image_folder/(key+".jpg")
            assert cv2.imwrite(str(path),image,[cv2.IMWRITE_JPEG_QUALITY,85])
            entries.append({"id":key,"packet":packet,"image":path.relative_to(ROOT).as_posix(),"original_image":name})
            mapping.append({"analyzed_frame_index":row["frame_index"],"replay_seconds":row["video_seconds"],"original_image":name})
        cases.append({"camera":case["camera"],"session":session,"label":case["label"],"selected_frames":len(mapping),
                      "selection":"time-spread linked-face scenes when available; not an accuracy sample",
                      "full_inference_candidate_faces":analysis["candidate_faces"],"published_frames_have_registered_candidates":False,
                      "mapping":mapping})
    save(OUT/"packets.json",{"cases":cases,"entries":entries,"derivative_notice":NOTICE})
    emit(stage="prepared",new_sessions=len(cases),selected_images=len(entries))


def main():
    assert os.environ.get("WSL_DISTRO_NAME"), "Use the WSL project virtualenv"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["collect","analyze","prepare"])
    parser.add_argument("--camera",choices=[case["camera"] for case in CASES])
    args = parser.parse_args()
    if args.stage=="analyze":
        analyze(args.camera)
    else:
        {"collect":collect,"prepare":prepare}[args.stage]()


if __name__ == "__main__":
    main()
