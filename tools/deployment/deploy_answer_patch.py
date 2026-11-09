"""Deploy the verified answer-format fix via official APIs, without console access."""
from datetime import datetime,timezone
import fcntl
import hashlib
from io import BytesIO
import json
import os
import time
from zipfile import ZipFile,ZIP_DEFLATED
import requests
import pythonanywhere_auth as auth
from pythonanywhere_deploy import API,BASE,HOME,DOMAIN,WORKSPACE,SERVER,build_package,verify,assert_source_unchanged

ALLOWED={"blog/history_llm.py","blog/tests/test_history_llm.py","blog/static/blog/history.mjs",
         "blog/static/blog/history.css","blog/templates/blog/history.html"}


def sha(value):return hashlib.sha256(value).hexdigest()


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    lock=(auth.DEFAULT_DIR/"deployment.lock").open("w");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    release,package,manifest_path,manifest=build_package();verify();assert_source_unchanged(manifest)
    assert sha(package.read_bytes())==manifest["sha256"]
    api=API(auth.load_credentials());active_raw=api.file(BASE+"/active.json");active=json.loads(active_raw)
    assert active["phase"]=="verified"
    prior=active.get("verified_patch",active.get("frontend_overlay",{})).get("release",active["release"])
    previous=json.loads((WORKSPACE/"dist"/("pythonanywhere-auto-"+prior+".json")).read_text())
    old={r["path"]:r["sha256"] for r in previous["files"]};new={r["path"]:r["sha256"] for r in manifest["files"]}
    assert set(old)==set(new)
    changed={key for key in new if new[key]!=old[key]};assert changed and changed<=ALLOWED
    assert not any("migration" in path or path.endswith("models.py") or path.endswith("requirements.txt") for path in changed)
    backup=BytesIO();writes=[]
    with ZipFile(backup,"w",ZIP_DEFLATED) as archive:
        archive.writestr("active.json",active_raw)
        for relative in sorted(changed):
            content=(SERVER/relative).read_bytes();assert sha(content)==new[relative]
            remote=active["source"]+"/"+relative;before=api.file(remote);assert sha(before)==old[relative]
            archive.writestr("source/"+relative,before);writes.append((remote,before,content))
            if relative.startswith("blog/static/"):
                static=active["static"]+"/"+relative.split("/static/",1)[1]
                original=api.file(static);assert sha(original)==old[relative]
                archive.writestr("static/"+relative,original);writes.append((static,original,content))
    backup_path=HOME+"/.config/mobile-web-service/common02/answer-backup-"+release+".zip"
    api.file(backup_path,backup.getvalue());assert sha(api.file(backup_path))==sha(backup.getvalue())
    applied=[]
    try:
        for remote,before,content in writes:
            api.file(remote,content);applied.append((remote,before));assert sha(api.file(remote))==sha(content)
        api.request("POST",f"/webapps/{DOMAIN}/reload/",{})
        for relative in ("blog/static/blog/history.css","blog/static/blog/history.mjs"):
            url="https://"+DOMAIN+"/static/"+relative.split("/static/",1)[1]+"?v="+release
            for attempt in range(10):
                response=requests.get(url,timeout=(5,20),allow_redirects=False)
                if response.status_code==200 and sha(response.content)==new[relative]:break
                time.sleep(2)
            else:raise RuntimeError("Public UI does not match the verified patch")
        app=json.loads(auth.private_read(auth.secure_directory(__import__('pathlib').Path.home()/".config/mobile-web-service/common02")/"edge-auth.json"))
        response=requests.post("https://"+DOMAIN+"/api/v1/history/ask/",headers={"Authorization":"Token "+app["token"]},
            json={"question":"어떤 영상에서 발견됐어?","profile":"showcase-v2-a","include_candidates":True,"date_basis":"processed"},timeout=(5,20))
        assert response.status_code==200 and response.json()["facts"]["source_count"]==2
        assert_source_unchanged(manifest)
        patch={"release":release,"parent_release":prior,"base_release":active["release"],"backup":backup_path,
               "changed_files":sorted(changed),"verified_utc":datetime.now(timezone.utc).isoformat(),"phase":"verified"}
        active["verified_patch"]=patch;api.file(BASE+"/active.json",json.dumps(active).encode())
    except Exception:
        for remote,before in reversed(applied):api.file(remote,before)
        api.request("POST",f"/webapps/{DOMAIN}/reload/",{});raise
    result={"pass":True,"production_verified":True,"release":release,"base_release":active["release"],
            "console_used":False,"database_or_dependencies_changed":False,"changed_files":sorted(changed),
            "backup_verified":True,"source_and_public_assets_verified":True,"record_question_verified":True,
            "actual_llm_call_in_this_step":False,"verified_utc":patch["verified_utc"]}
    (WORKSPACE/"evidence/ui-audit/answer-patch-deployment.json").write_text(json.dumps(result,indent=2)+"\n")
    history_path=WORKSPACE/"evidence/ui-audit/answer-patch-history.json"
    history=json.loads(history_path.read_text()) if history_path.exists() else []
    history.append(result);history_path.write_text(json.dumps(history,indent=2)+"\n")
    print(json.dumps(result),flush=True)


if __name__=="__main__":main()
