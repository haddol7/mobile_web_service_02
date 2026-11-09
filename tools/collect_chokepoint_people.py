"""Fetch the official enrollment stills without changing any model or server."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import tarfile

from expand_chokepoint_walk import download_archive,file_hash

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence/private/cctv-walking/people"
URL="https://zenodo.org/records/815657/files/Still.tar.xz?download=1"
MD5="2efcd4010d19e811cce144a614ea82a2"


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    OUT.mkdir(parents=True,exist_ok=True)
    archive=OUT/"Still.tar.xz"
    if not archive.exists():
        download_archive(URL,archive,MD5)
    assert file_hash(archive,"md5")==MD5
    names=[]
    with tarfile.open(archive) as bundle:
        for member in bundle:
            if not member.isfile() or not member.name.lower().endswith((".jpg",".jpeg",".png")):
                continue
            assert member.size<20*1024**2
            parts=Path(member.name).parts
            assert not Path(member.name).is_absolute() and ".." not in parts
            target=OUT/"stills"/Path(*parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():
                target.write_bytes(bundle.extractfile(member).read())
            names.append({"member":member.name,"path":target.relative_to(ROOT).as_posix()})
    assert names,"The official still archive must contain enrollment images"
    proof={"pass":True,"verified_utc":datetime.now(timezone.utc).isoformat(),"source":URL,"official_md5":MD5,
           "sha256":file_hash(archive),"bytes":archive.stat().st_size,"images":names,"actual_paid_api_calls":0}
    (OUT/"stills-collection.json").write_text(json.dumps(proof,indent=2)+"\n")
    print(json.dumps({"pass":True,"images":len(names),"first_members":[row["member"] for row in names[:35]]}),flush=True)


if __name__=="__main__":
    main()
