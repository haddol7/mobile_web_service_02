"""Console-free official API deployment, restricted to the five verified UI files."""
from datetime import datetime,timezone
import fcntl
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import time
from zipfile import ZipFile,ZIP_DEFLATED
import requests
import pythonanywhere_auth as auth
from pythonanywhere_deploy import API,BASE,DOMAIN,HOME,WORKSPACE,SERVER,assert_source_unchanged,verify_frontend

ALLOWED={"blog/static/blog/people.css","blog/static/blog/person.mjs","blog/templates/blog/base.html",
         "blog/templates/blog/people.html","blog/templates/blog/person_detail.html"}


def sha(value):return hashlib.sha256(value).hexdigest()


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    release=sys.argv[1];assert len(release)==20 and release.isalnum()
    verify_frontend()
    path=WORKSPACE/"dist"/("pythonanywhere-auto-"+release+".json")
    manifest=json.loads(path.read_text());assert_source_unchanged(manifest)
    package=path.with_suffix(".zip");assert sha(package.read_bytes())==manifest["sha256"]
    lock=(auth.DEFAULT_DIR/"deployment.lock").open("w");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    api=API(auth.load_credentials());active_raw=api.file(BASE+"/active.json");active=json.loads(active_raw)
    assert active["phase"]=="verified" and not active.get("frontend_overlay"),"Inspect existing overlay before replacing it"
    previous=json.loads((WORKSPACE/"dist"/("pythonanywhere-auto-"+active["release"]+".json")).read_text())
    old={r["path"]:r["sha256"] for r in previous["files"]};new={r["path"]:r["sha256"] for r in manifest["files"]}
    assert set(old)==set(new),"File additions/removals require the full deployment workflow"
    changed={key for key in new if old[key]!=new[key]}
    assert changed==ALLOWED,"Backend or unexpected file changes require the full deployment workflow"
    writes=[];backup=BytesIO()
    with ZipFile(backup,"w",ZIP_DEFLATED) as archive:
        archive.writestr("active.json",active_raw)
        for relative in sorted(changed):
            content=(SERVER/relative).read_bytes();assert sha(content)==new[relative]
            remote=active["source"]+"/"+relative;before=api.file(remote);assert sha(before)==old[relative]
            archive.writestr("source/"+relative,before);writes.append((remote,before,content))
            if relative.startswith("blog/static/"):
                static=active["static"]+"/"+relative.split("/static/",1)[1]
                before_static=api.file(static);assert sha(before_static)==old[relative]
                archive.writestr("static/"+relative,before_static);writes.append((static,before_static,content))
    remote_backup=HOME+"/.config/mobile-web-service/common02/frontend-backup-"+release+".zip"
    api.file(remote_backup,backup.getvalue());assert sha(api.file(remote_backup))==sha(backup.getvalue())
    applied=[]
    try:
        for remote,before,content in sorted(writes,key=lambda row:("/templates/" in row[0],row[0])):
            api.file(remote,content);applied.append((remote,before));assert sha(api.file(remote))==sha(content)
        api.request("POST",f"/webapps/{DOMAIN}/reload/",{})
        origin="https://"+DOMAIN
        for relative in ("blog/static/blog/people.css","blog/static/blog/person.mjs"):
            url=origin+"/static/"+relative.split("/static/",1)[1]+"?v="+release
            for attempt in range(10):
                response=requests.get(url,timeout=(5,20),allow_redirects=False)
                if response.status_code==200 and sha(response.content)==new[relative]:break
                time.sleep(2)
            else:raise RuntimeError("Public asset does not match the verified source")
        response=requests.get(origin+"/",timeout=(5,20),allow_redirects=False)
        assert response.status_code==200 and "people-2" in response.text
        assert_source_unchanged(manifest)
        overlay={"release":release,"base_release":active["release"],"verified_utc":datetime.now(timezone.utc).isoformat(),
                 "package_sha256":manifest["sha256"],"changed_files":sorted(changed),"backup":remote_backup,"phase":"verified"}
        active["frontend_overlay"]=overlay
        api.file(BASE+"/active.json",json.dumps(active).encode())
    except Exception:
        for remote,before in reversed(applied):api.file(remote,before)
        api.request("POST",f"/webapps/{DOMAIN}/reload/",{})
        raise
    proof={"pass":True,"production_verified":True,"environment":"WSL client / official PythonAnywhere Files and Webapps API",
           "release":release,"base_release":active["release"],"changed_files":sorted(changed),"database_changed":False,
           "python_changed":False,"console_used":False,"backup_verified":True,"public_asset_hashes_verified":True,
           "reload_verified":True,"verified_utc":overlay["verified_utc"]}
    (WORKSPACE/"evidence/ui-audit/people-frontend-deployment.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=="__main__":main()
