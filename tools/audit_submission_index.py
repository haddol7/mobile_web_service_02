"""Inspect exact staged bytes for private files, oversized blobs and credential patterns."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "openai_key": rb"(?<![A-Za-z0-9_])sk-(?:proj-)?[A-Za-z0-9_-]{24,}",
    "github_token": rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "aws_key": rb"(?<![A-Za-z0-9_])AKIA[A-Z0-9]{16}(?![A-Za-z0-9_])",
    "private_key": rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
    "literal_auth_token": rb"Authorization[\"']?\s*[:=]\s*[\"'](?:Token|Bearer) [A-Za-z0-9_-]{24,}",
}


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    problems = []
    files = []
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for name in filter(None, paths):
            parts = Path(name).parts
            if any(p in {".local", "private", "private_tracking", ".venv", "node_modules"} for p in parts) or Path(name).name.startswith("db.sqlite3") or (Path(name).name.startswith(".env") and not name.endswith(".env.example")) or Path(name).name == "local.properties":
                problems.append({"file":name,"kind":"private_path"})
            process.stdin.write((":"+name+"\n").encode("utf-8"))
            process.stdin.flush()
            header = process.stdout.readline().decode().strip().split()
            if len(header) != 3 or header[1] != "blob":
                raise RuntimeError("Expected staged blob")
            size = int(header[2])
            data = process.stdout.read(size)
            assert len(data) == size and process.stdout.read(1) == b"\n"
            if size >= 95 * 1024 * 1024:
                problems.append({"file":name,"kind":"oversized_blob","bytes":size})
            content = [data]
            if name.endswith(".docx"):
                with ZipFile(BytesIO(data)) as archive:
                    content = [archive.read(p) for p in archive.namelist() if p.endswith(".xml")]
            for label, pattern in PATTERNS.items():
                if any(re.search(pattern, value) for value in content):
                    problems.append({"file":name,"kind":label})
            files.append({"path":name,"bytes":size,"sha256":hashlib.sha256(data).hexdigest()})
    finally:
        process.stdin.close()
        process.stdout.close()
        process.wait()
    result = {"files_checked":len(files), "total_bytes":sum(row["bytes"] for row in files),
              "problems":problems,"pass":not problems, "files":files}
    target = ROOT/"evidence/private/submission-final-20261110/index-audit.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "files"},ensure_ascii=False))
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
