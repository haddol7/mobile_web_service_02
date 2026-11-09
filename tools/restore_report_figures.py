"""Restore the report's source figures from its embedded original bytes after a Git clone."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx"


def main():
    records = json.loads((ROOT/"docs/report-figures.json").read_text(encoding="utf-8"))
    with ZipFile(REPORT) as archive:
        images = {hashlib.sha256(archive.read(name)).hexdigest(): archive.read(name)
                  for name in archive.namelist() if name.startswith("word/media/")}
    restored = 0
    for item in records:
        path = (ROOT/item["path"]).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("Figure path outside project")
        if path.is_file():
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Existing figure differs: " + item["path"])
            continue
        data = images.get(item["sha256"])
        if data is None:
            raise ValueError("Expected image missing from report")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        restored += 1
    print(json.dumps({"figures": len(records), "restored": restored, "pass": True}))


if __name__ == "__main__":
    main()
