"""Build a current-source laptop bundle, excluding machine credentials and live databases."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "mobile_web_service/common02/"
EXCLUDED_DIRS = {".git", ".gradle", ".idea", ".local", ".venv", "venv", "__pycache__", "node_modules",
                 "build", "htmlcov", "staticfiles", "media", "private_tracking", "runs", "history-outbox", "private", "evidence", "dist"}
EXCLUDED_NAMES = {"local.properties", "production.json", ".coverage"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".keystore", ".sqlite3", ".zip", ".apk", ".log", ".bundle"}


def allowed(relative):
    relative = Path(relative)
    if relative.parts[:2] in (("laptop", "models"), ("laptop", "data")) or relative.as_posix() == "laptop/MANIFEST.json":
        return False
    return (not any(p in EXCLUDED_DIRS for p in relative.parts)
            and relative.name not in EXCLUDED_NAMES
            and not relative.name.startswith((".env", "db.sqlite3", "~$"))
            and relative.suffix.lower() not in EXCLUDED_SUFFIXES)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models", type=Path, default=Path.home() / ".insightface/models/buffalo_l")
    args = parser.parse_args()
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run with the WSL project virtualenv")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit("Output already exists; choose a new name")
    entries = {}
    for directory in ("PhotoBlogServer", "PhotoViewer", "YOLOv5", "tools", "docs", "web-tests", "laptop"):
        for folder, directories, files in os.walk(ROOT / directory, followlinks=False):
            directories[:] = [name for name in directories if name not in EXCLUDED_DIRS and not (Path(folder)/name).is_symlink()]
            for name in files:
                source = Path(folder) / name
                relative = source.relative_to(ROOT)
                if source.is_symlink() or not allowed(relative):
                    continue
                entries[relative.as_posix()] = source
    for name in ("README.md", ".gitignore", "모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx"):
        entries[name] = ROOT / name
    for name in ("report-review.json", "report-layout-review.json", "report-content-review.json"):
        entries["evidence/" + name] = ROOT / "evidence" / name
    # Include assessed runtime artifacts, not any Windows virtualenv or WSL home configuration.
    apk = ROOT / "PhotoViewer/app/build/outputs/apk/debug/app-debug.apk"
    if not apk.is_file():
        raise SystemExit("Build the Android APK first")
    entries["laptop/PhotoViewer-02.apk"] = apk
    models = sorted(args.models.glob("*.onnx"))
    if not {"det_10g.onnx", "w600k_r50.onnx"} <= {p.name for p in models}:
        raise SystemExit("Expected verified Buffalo L model files missing")
    for source in models:
        entries["laptop/models/buffalo_l/" + source.name] = source
    # Rewrite the explicit gallery into relative paths valid under any Windows username.
    gallery_path = ROOT / "evidence/private/cctv-walking/people/references.json"
    gallery = json.loads(gallery_path.read_text(encoding="utf-8"))
    portable = {"schema_version": 1, "profiles": []}
    reference_manifest = []
    for profile in gallery["profiles"]:
        images = []
        for i, entry in enumerate(profile["images"]):
            name = entry if isinstance(entry, str) else entry["image"]
            source = (gallery_path.parent / name).resolve()
            if not source.is_relative_to(ROOT.resolve()) or not source.is_file() or source.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                raise ValueError("Reference must be a project image")
            output = "references/" + profile["id"] + "-" + str(i) + source.suffix.lower()
            if "/" in profile["id"] or "\\" in profile["id"] or ".." in profile["id"]:
                raise ValueError("Invalid reference identity")
            entries["laptop/data/" + output] = source
            images.append(output if isinstance(entry, str) else {**entry, "image": output})
            reference_manifest.append({"profile_id": profile["id"], "image": output, "sha256": sha(source)})
        portable["profiles"].append({"id": profile["id"], "name": profile["name"], "images": images})
    video = ROOT / "evidence/private/cctv-walking/chokepoint/P1E_S1_C1-first1200.mp4"
    entries["laptop/data/walking.mp4"] = video
    license_path = ROOT / "evidence/private/cctv-walking/expanded/CHOKEPOINT_LICENSE.txt"
    entries["laptop/data/CHOKEPOINT_LICENSE.txt"] = license_path
    entries["../AGENTS.md"] = ROOT.parent / "AGENTS.md"
    # The only intentionally parent-level entry is the workspace rules file above the project.
    manifest = []
    with ZipFile(args.output, "x", compression=ZIP_DEFLATED, compresslevel=3, allowZip64=True) as archive:
        for name, source in sorted(entries.items()):
            destination = "mobile_web_service/AGENTS.md" if name == "../AGENTS.md" else PREFIX + name
            archive.write(source, destination, compress_type=ZIP_STORED if source.suffix == ".apk" else ZIP_DEFLATED)
            if name != "../AGENTS.md":
                manifest.append({"path": name, "bytes": source.stat().st_size, "sha256": sha(source)})
        payload = (json.dumps(portable, ensure_ascii=False, indent=2) + "\n").encode()
        archive.writestr(PREFIX + "laptop/data/references.json", payload)
        manifest.append({"path": "laptop/data/references.json", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        metadata = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                    "purpose": "Personal Windows x64 laptop migration of current working source",
                    "server": "https://daejinha.pythonanywhere.com", "files": manifest,
                    "gallery_profiles": len(portable["profiles"]), "reference_images": len(reference_manifest),
                    "models_included": [p.name for p in models], "credentials_included": False,
                    "live_database_included": False, "production_data_location": "Existing PythonAnywhere deployment",
                    "paid_api_calls_during_build": 0}
        archive.writestr(PREFIX + "laptop/MANIFEST.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    with ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP checksum verification failed")
        for row in manifest:
            with archive.open(PREFIX + row["path"]) as stream:
                value = hashlib.file_digest(stream, "sha256").hexdigest()
            if value != row["sha256"]:
                raise RuntimeError("Archived bytes differ from manifest")
    digest = sha(args.output)
    args.output.with_suffix(".zip.sha256").write_text(digest + "  " + args.output.name + "\n")
    summary = {"archive": str(args.output), "bytes": args.output.stat().st_size, "sha256": digest,
               "verified_files": len(manifest), "gallery_profiles": len(portable["profiles"]),
               "reference_images": len(reference_manifest), "archive_verified": True}
    args.output.with_suffix(".zip.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
