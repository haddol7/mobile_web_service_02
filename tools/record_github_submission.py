"""Verify an actual push and public report bytes without reading authentication material."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx"


def git(*args):
    return subprocess.check_output(["git",*args],cwd=ROOT).decode("utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    commit = git("rev-parse","HEAD")
    remote = git("ls-remote","origin","refs/heads/main").split()[0]
    assert commit == remote, "Remote branch does not match local commit"
    assert not git("status","--porcelain"), "Working tree differs from pushed snapshot"
    url = "https://raw.githubusercontent.com/haddol7/mobile_web_service_02/"+commit+"/"+quote(REPORT.name)
    with urlopen(Request(url,headers={"User-Agent":"Common02-Submission-Verification"}),timeout=90) as response:
        actual = response.read()
    digest = hashlib.sha256(REPORT.read_bytes()).hexdigest()
    assert hashlib.sha256(actual).hexdigest() == digest, "Remote report bytes differ"
    for name in ("PhotoBlogServer/blog/history_api.py","PhotoViewer/app/src/main/java/com/haddol7/photoviewer/MainActivity.java","YOLOv5/face_policy.json"):
        blob = subprocess.check_output(["git","show",commit+":"+name],cwd=ROOT)
        assert blob == (ROOT/name).read_bytes(), "Committed source differs: "+name
    proof = {"verified_utc":datetime.now(timezone.utc).isoformat(),
             "repository":"https://github.com/haddol7/mobile_web_service_02", "commit":commit,"remote_head":remote,
             "remote_head_matches_commit":True,"latest_source_and_report_verified":True,
             "report_path":REPORT.name,"report_sha256":digest,"remote_report_bytes":len(actual),
             "verification_method":"git ls-remote, committed source byte comparison and public raw DOCX SHA256",
             "paid_api_calls":0}
    target = ROOT/("evidence/private/submission-final-20261110/remote-final-verification.json" if args.final else "evidence/github-upload.json")
    target.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(proof,ensure_ascii=False))


if __name__ == "__main__":
    main()
