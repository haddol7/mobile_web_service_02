"""Deploy stored detection boxes without calling model APIs via official APIs with hash checks and rollback."""
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
from pythonanywhere_deploy import API,BASE,HOME,DOMAIN,WORKSPACE,SERVER,build_package,verify_frontend,assert_source_unchanged

ALLOWED={"blog/history_api.py","blog/history_queries.py","blog/history_annotations.py","blog/templates/blog/history.html","blog/static/blog/history.css","blog/static/blog/history.mjs","blog/tests/test_history_annotations.py","blog/fonts/PretendardVariable.ttf","blog/fonts/Pretendard-LICENSE.txt"}
ADDITIONS={"blog/history_annotations.py","blog/tests/test_history_annotations.py","blog/fonts/PretendardVariable.ttf","blog/fonts/Pretendard-LICENSE.txt"}

def sha(value):return hashlib.sha256(value).hexdigest()


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    lock=(auth.DEFAULT_DIR/"deployment.lock").open("w");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    verify_frontend()
    sys.path.insert(0,str(SERVER/"tools"))
    from verify_baseline import source_hashes
    checked=json.loads((WORKSPACE/"evidence/content/server/verification.json").read_text())
    assert checked["pass"] and checked["environment"]=="WSL Ubuntu"
    assert not checked["source_changed_during_validation"] and checked["source_sha256"]==source_hashes()
    assert 0<=(datetime.now(timezone.utc)-datetime.fromisoformat(checked["finished_utc"])).total_seconds()<900
    release,package,manifest_path,manifest=build_package();assert_source_unchanged(manifest)
    assert sha(package.read_bytes())==manifest["sha256"]
    api=API(auth.load_credentials());active_raw=api.file(BASE+"/active.json");active=json.loads(active_raw)
    assert active["phase"]=="verified"
    prior=active.get("verified_patch",active.get("frontend_overlay",{})).get("release",active["release"])
    previous=json.loads((WORKSPACE/"dist"/("pythonanywhere-auto-"+prior+".json")).read_text())
    old={r["path"]:r["sha256"] for r in previous["files"]};new={r["path"]:r["sha256"] for r in manifest["files"]}
    assert set(old)<=set(new) and set(new)-set(old)<=ADDITIONS
    changed={key for key in new if new[key]!=old.get(key)};assert changed and changed<=ALLOWED
    assert not any("migration" in path or path.endswith("models.py") or path.endswith("requirements.txt") for path in changed)
    backup=BytesIO();writes=[]
    with ZipFile(backup,"w",ZIP_DEFLATED) as archive:
        archive.writestr("active.json",active_raw)
        archive.writestr("added-files.json",json.dumps(sorted(set(new)-set(old))))
        for relative in sorted(changed):
            content=(SERVER/relative).read_bytes();assert sha(content)==new[relative]
            remote=active["source"]+"/"+relative;before=api.file(remote,missing_ok=relative in ADDITIONS);assert (sha(before) if before is not None else None)==old.get(relative)
            if before is not None:archive.writestr("source/"+relative,before)
            writes.append((remote,before,content))
            if relative.startswith("blog/static/"):
                static=active["static"]+"/"+relative.split("/static/",1)[1]
                original=api.file(static,missing_ok=relative in ADDITIONS);assert (sha(original) if original is not None else None)==old.get(relative)
                if original is not None:archive.writestr("static/"+relative,original)
                writes.append((static,original,content))
    backup_path=HOME+"/.config/mobile-web-service/common02/detection-boxes-backup-"+release+".zip"
    api.file(backup_path,backup.getvalue());assert sha(api.file(backup_path))==sha(backup.getvalue())
    applied=[]
    try:
        for remote,before,content in writes:
            api.file(remote,content);applied.append((remote,before));assert sha(api.file(remote))==sha(content)
        api.request("POST",f"/webapps/{DOMAIN}/reload/",{})
        for relative in sorted(path for path in changed if path.startswith("blog/static/")):
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
        headers={"Authorization":"Token "+app["token"]}
        calendar=requests.get("https://"+DOMAIN+"/api/v1/history/sessions/",params={"date_basis":"processed"},headers=headers,timeout=(5,20))
        assert calendar.status_code==200
        days=calendar.json()["days"];assert days and all(day["date_key"] for day in days)
        first=days[0]["date_key"]
        chosen=requests.get("https://"+DOMAIN+"/api/v1/history/sessions/",params={"date_basis":"processed","start":first,"end":first},headers=headers,timeout=(5,20))
        assert chosen.status_code==200 and all(row["date_key"]==first for row in chosen.json()["results"])
        assert chosen.json()["days"]==days
        frames=requests.get("https://"+DOMAIN+"/api/v1/history/sessions/",params={"date_basis":"processed","profile":"chokepoint-0005","include_candidates":"true"},headers=headers,timeout=(5,30))
        assert frames.status_code==200
        row=next(frame for card in frames.json()["results"] for frame in card["frames"] if frame["image_url"] and frame["tracks"])
        assert row["image_url"].endswith("?boxes=1")
        boxed=requests.get("https://"+DOMAIN+row["image_url"],headers=headers,timeout=(5,30))
        assert boxed.status_code==200 and boxed.headers["X-Detection-Overlay"]=="1"
        assert int(boxed.headers["X-Detection-Boxes"])>0 and boxed.headers["Cache-Control"]=="private, no-store"
        raw=requests.get("https://"+DOMAIN+row["image_url"].split("?")[0],headers=headers,timeout=(5,30))
        assert raw.status_code==200 and sha(raw.content)!=sha(boxed.content)
        denied=requests.get("https://"+DOMAIN+row["image_url"],timeout=(5,30),allow_redirects=False)
        assert denied.status_code in (401,403)
        capture=WORKSPACE/"evidence/private/detection-boxes"
        capture.mkdir(parents=True,exist_ok=True)
        (capture/"production-annotated.jpg").write_bytes(boxed.content)
        anonymous=requests.get("https://"+DOMAIN+"/",timeout=(5,20),allow_redirects=False)
        assert anonymous.status_code==200 and "workspace-1" in anonymous.text
        assert "운영자 로그인" in anonymous.text and 'id="history-grid"' not in anonymous.text
        for path in ("/detections/","/history/","/people/","/questions/"):
            private_page=requests.get("https://"+DOMAIN+path,timeout=(5,20),allow_redirects=False)
            assert private_page.status_code==302 and private_page.headers["Location"].startswith("/accounts/login/")
        corpus=requests.get("https://"+DOMAIN+"/api/v1/history/embedding-documents/",headers=headers,timeout=(5,30),allow_redirects=False)
        assert corpus.status_code==200 and corpus.json()["dimensions"]==512
        anonymous_corpus=requests.get("https://"+DOMAIN+"/api/v1/history/embedding-documents/",timeout=(5,20),allow_redirects=False)
        assert anonymous_corpus.status_code in (401,403)
        corpus_path=WORKSPACE/"evidence/private/embeddings/corpus.json"
        corpus_path.parent.mkdir(exist_ok=True,parents=True,mode=0o700)
        descriptor=os.open(corpus_path,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(descriptor,"w") as output:json.dump(corpus.json(),output,ensure_ascii=False)
        assert response.json()["retrieval"]["api_requests"]==0
        assert_source_unchanged(manifest)
        patch={"release":release,"parent_release":prior,"base_release":active["release"],"backup":backup_path,
               "changed_files":sorted(changed),"verified_utc":datetime.now(timezone.utc).isoformat(),"phase":"verified"}
        active["verified_patch"]=patch;api.file(BASE+"/active.json",json.dumps(active).encode())
    except Exception:
        for remote,before in reversed(applied):
            if before is None:api.request("DELETE","/files/path"+__import__('urllib.parse',fromlist=['quote']).quote(remote,safe='/'))
            else:api.file(remote,before)
        api.request("POST",f"/webapps/{DOMAIN}/reload/",{});raise
    result={"pass":True,"production_verified":True,"release":release,"base_release":active["release"],
            "console_used":False,"database_or_dependencies_changed":False,"changed_files":sorted(changed),
            "backup_verified":True,"source_and_public_assets_verified":True,"record_question_verified":True,
            "actual_llm_call_in_this_step":False,"verified_utc":patch["verified_utc"]}
    result.update(calendar_days=days,day_selection_verified=True,corpus_documents=len(corpus.json()["documents"]),actual_embedding_api_calls=0)
    result.update(annotation_boxes=int(boxed.headers["X-Detection-Boxes"]),annotation_frame=row["id"],
                  annotated_image_sha256=sha(boxed.content),original_image_sha256=sha(raw.content),
                  anonymous_image_denied=True,original_media_preserved=True)
    (WORKSPACE/"evidence/ui-audit/detection-boxes-deployment.json").write_text(json.dumps(result,indent=2)+"\n")
    history_path=WORKSPACE/"evidence/ui-audit/detection-boxes-patch-history.json"
    history=json.loads(history_path.read_text()) if history_path.exists() else []
    history.append(result);history_path.write_text(json.dumps(history,indent=2)+"\n")
    print(json.dumps(result),flush=True)


if __name__=="__main__":main()
