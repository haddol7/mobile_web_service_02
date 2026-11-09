"""Collect identity-disjoint final videos before choosing an improved face policy."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
from zipfile import ZipFile, ZIP_STORED, ZIP_DEFLATED
import zlib

from collect_face_validation import ROOT, REPO, REVISION, ARCHIVE_SIZE, RangeReader, fetch_range, decode

PRIVATE = ROOT/"evidence/private/face-improvement/holdout"
PUBLIC = ROOT/"evidence/person-libraries"


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside WSL.")
    PRIVATE.mkdir(parents=True,exist_ok=True)
    if (PRIVATE/"collection.json").exists():
        saved=json.loads((PRIVATE/"collection.json").read_text())
        for item in saved["clips"]:
            assert hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest()==item["sha256"]
        print(json.dumps({"verified_existing_holdout":True,"clips":len(saved["clips"])}))
        return
    development=json.loads((ROOT/"evidence/private/face-validation/collection.json").read_text())
    excluded=set(development["enrolled_identities"]+development["unknown_identities"]+development["excluded_previous_identities"])
    reader=RangeReader()
    people=defaultdict(lambda:defaultdict(list))
    with ZipFile(reader) as archive:
        for item in archive.infolist():
            parts=Path(item.filename).parts
            if item.filename.endswith(".mp4") and len(parts)>=3 and parts[-3] not in excluded and item.file_size<=2*1024**2:
                people[parts[-3]][parts[-2]].append(item)
    eligible=sorted(identity for identity,groups in people.items() if len(groups)>=3)
    assert len(eligible)>=24
    known,unknown=eligible[:12],eligible[12:24]
    selected=[]
    for identity in known+unknown:
        for index,source in enumerate(sorted(people[identity])[:3] if identity in known else sorted(people[identity])[:2]):
            item=min(people[identity][source],key=lambda m:(m.file_size,m.filename))
            selected.append({"identity":identity,"source_video_id":source,
                "role":"reference" if identity in known and index==0 else "query","enrolled":identity in known,
                "member":item.filename,"header_offset":item.header_offset,"compressed_size":item.compress_size,
                "bytes":item.file_size,"crc":item.CRC,"compression":item.compress_type})
    assert len(selected)==60
    assert sum(c["compressed_size"]+4096 for c in selected)+reader.downloaded<=64*1024**2
    (PRIVATE/"frozen-selection.json").write_text(json.dumps(selected,indent=2)+"\n")
    def download(item):
        size=min(item["compressed_size"]+4096,ARCHIVE_SIZE-item["header_offset"])
        data=fetch_range(item["header_offset"],size)
        header=struct.unpack("<4s5H3I2H",data[:30])
        assert header[0]==b"PK\x03\x04" and not header[2]&1
        offset=30+header[-2]+header[-1]
        blob=data[offset:offset+item["compressed_size"]]
        raw=blob if item["compression"]==ZIP_STORED else zlib.decompress(blob,-15) if item["compression"]==ZIP_DEFLATED else None
        assert raw and len(raw)==item["bytes"] and zlib.crc32(raw)&0xffffffff==item["crc"]
        digest=hashlib.sha256(raw).hexdigest()
        path=PRIVATE/(digest+".mp4");path.write_bytes(raw)
        return {**item,"path":str(path.relative_to(ROOT)),"sha256":digest,"decode":decode(path),"range_bytes_read":size}
    clips=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(download,c) for c in selected]):
            clips.append(future.result())
            print(json.dumps({"holdout_clips_downloaded":len(clips),"selected":60}),flush=True)
    clips.sort(key=lambda c:(c["identity"],c["role"],c["source_video_id"]))
    assert len({c["sha256"] for c in clips})==60
    result={"collected_utc":datetime.now(timezone.utc).isoformat(),"dataset":REPO,"revision":REVISION,
        "environment":"WSL Ubuntu","enrolled_identities":known,"unknown_identities":unknown,
        "excluded_previous_identities":sorted(excluded),"clips":clips,"identity_count":24,
        "query_clip_count":48,"total_source_frames_decoded":sum(c["decode"]["frames"] for c in clips),
        "source_bytes_read":reader.downloaded+sum(c["range_bytes_read"] for c in clips),
        "selection_before_improved_policy_evaluation":True,"training_performed":False}
    (PRIVATE/"collection.json").write_text(json.dumps(result,indent=2)+"\n")
    (PUBLIC/"face-improvement-holdout-collection.json").write_text(json.dumps({
        k:v for k,v in result.items() if k!="clips"},indent=2)+"\n")
    print(json.dumps({"complete":True,"identities":24,"clips":60,"queries":48}),flush=True)


if __name__=="__main__":
    main()
