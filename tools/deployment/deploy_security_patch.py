"""Deploy the tested security controls with backups, hash checks and no paid calls."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit
from zipfile import ZipFile, ZIP_DEFLATED

import requests
import pythonanywhere_auth as auth
from pythonanywhere_deploy import API, BASE, HOME, DOMAIN, WORKSPACE, SERVER, DeploymentError, build_package, verify_frontend, assert_source_unchanged, wait_request_slot

ADDED = {"blog/auth_limits.py", "blog/request_limits.py", "blog/templates/registration/rate_limited.html",
         "blog/tests/test_request_limits.py", "tools/verify_security.py", "blog/history_access.py", "blog/tests/test_public_access.py"}
ALLOWED = ADDED | {"blog/history_embeddings.py", "blog/history_llm.py", "blog/history_api.py", "blog/api_v1_urls.py",
    "blog/static/blog/chat.mjs", "blog/templates/blog/chat.html", "photoblog/settings.py", "deploy/production.py", "tools/verify_baseline.py",
    "blog/tests/test_chat.py", "blog/tests/test_configuration.py", "blog/tests/test_embeddings.py", "blog/tests/test_history_llm.py",
    "blog/views.py", "blog/chat_api.py", "blog/templates/blog/base.html", "blog/static/blog/ui.css",
    "blog/tests/test_monitoring.py", "blog/tests/test_history.py", "blog/tests/test_history_annotations.py", "blog/tests/test_person_experience.py", "blog/tests/test_content_web.py"}
OUT = WORKSPACE / "evidence/security"


def sha(value):
    return hashlib.sha256(value).hexdigest()


def public_get(url, **kwargs):
    wait_request_slot()
    return requests.get(url, **kwargs)


def changed_files(previous, current):
    old = {r["path"]:r["sha256"] for r in previous["files"]}
    new = {r["path"]:r["sha256"] for r in current["files"]}
    changed = {key for key in new if new[key] != old.get(key)}
    assert set(old) <= set(new) and set(new)-set(old) <= ADDED
    assert changed and changed <= ALLOWED, "Unexpected change outside the security patch"
    return old, new, changed


def fresh_checks():
    assert sys.platform.startswith("linux") and __import__("os").environ.get("WSL_DISTRO_NAME"), "Use WSL Ubuntu"
    verify_frontend()
    sys.path.insert(0, str(SERVER / "tools"))
    from verify_baseline import source_hashes
    checked = json.loads((WORKSPACE / "evidence/content/server/verification.json").read_text())
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(checked["finished_utc"])).total_seconds()
    assert checked["pass"] and checked["environment"] == "WSL Ubuntu" and 0 <= age < 900
    assert checked["source_sha256"] == source_hashes() and not checked["source_changed_during_validation"]


def verify_remote(api, active, release, new):
    origin = "https://" + DOMAIN
    for path in sorted(path for path in new if path.startswith("blog/static/") and path in ALLOWED):
        url = origin + "/static/" + path.split("/static/", 1)[1] + "?v=" + release
        response = public_get(url, timeout=(5,20), allow_redirects=False)
        assert response.status_code == 200 and sha(response.content) == new[path]
    config = json.loads(auth.private_read(auth.secure_directory(Path.home()/".config/mobile-web-service/common02")/"edge-auth.json"))
    headers = {"Authorization": "Token " + config["token"]}
    response = public_get(origin+"/api/v1/history/usage/", headers=headers, timeout=(5,20))
    assert response.status_code == 200
    usage = response.json()
    assert usage["timezone"] == "Asia/Seoul" and usage["login"]["trusted_platform_ip"] is True
    assert usage["daily"]["generation"]["limit"] == 10 and usage["daily"]["embedding"]["limit"] == 100
    assert usage["login"]["enabled"] is False
    assert usage["login"]["pair_failures"] == 5 and usage["login"]["ip_failures"] == 20
    anonymous = public_get(origin+"/api/v1/history/usage/", timeout=(5,20), allow_redirects=False)
    assert anonymous.status_code in (401,403)
    for path in ("/", "/people/", "/questions/", "/api/v1/history/frames/?limit=1", "/api_root/"):
        assert public_get(origin+path, timeout=(5,20), allow_redirects=False).status_code == 200
    post = public_get(origin+"/api_root/Post/8/", timeout=(5,20))
    assert post.status_code == 200
    image = post.json()["image"]
    assert urlsplit(image).netloc == DOMAIN and urlsplit(image).scheme == "https"
    response = public_get(image, timeout=(5,20))
    old = json.loads((WORKSPACE/"evidence/cloud/verification.json").read_text())["new_post"]["image_sha256"]
    assert response.status_code == 200 and sha(response.content) == old
    return usage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    fresh_checks()
    OUT.mkdir(exist_ok=True, parents=True)
    release, package, manifest_path, manifest = build_package()
    assert_source_unchanged(manifest)
    assert sha(package.read_bytes()) == manifest["sha256"]
    known = json.loads((WORKSPACE/"evidence/ui-audit/detection-boxes-deployment.json").read_text())["release"]
    known_manifest = json.loads((WORKSPACE/"dist"/("pythonanywhere-auto-"+known+".json")).read_text())
    _, _, planned = changed_files(known_manifest, manifest)
    preparation = {"phase":"prepared", "release":release, "manifest":str(manifest_path.relative_to(WORKSPACE)),
        "package_sha256":manifest["sha256"], "cloud_deployed":False, "paid_api_calls":0,
        "last_known_parent":known, "changed_files":sorted(planned),
        "checked_utc":datetime.now(timezone.utc).isoformat()}
    (OUT/"deployment-preparation.json").write_text(json.dumps(preparation, indent=2)+"\n")
    if args.prepare_only:
        print(json.dumps(preparation))
        return
    lock = (auth.DEFAULT_DIR/"deployment.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    api = API(auth.load_credentials())
    applied = []
    try:
        active_raw = api.file(BASE+"/active.json")
        active = json.loads(active_raw)
        assert active["phase"] == "verified"
        prior = active.get("verified_patch", active.get("frontend_overlay", {})).get("release", active["release"])
        previous = json.loads((WORKSPACE/"dist"/("pythonanywhere-auto-"+prior+".json")).read_text())
        old, new, changed = changed_files(previous, manifest)
        backup = BytesIO()
        writes = []
        with ZipFile(backup, "w", ZIP_DEFLATED) as archive:
            archive.writestr("active.json", active_raw)
            archive.writestr("added-files.json", json.dumps(sorted(set(new)-set(old))))
            for path in sorted(changed):
                print("Backing up " + path, flush=True)
                content = (SERVER/path).read_bytes()
                remote = active["source"]+"/"+path
                before = api.file(remote, missing_ok=path in ADDED)
                assert sha(content) == new[path] and (sha(before) if before is not None else None) == old.get(path)
                if before is not None:
                    archive.writestr("source/"+path, before)
                writes.append((remote, before, content))
                if path.startswith("blog/static/"):
                    target = active["static"]+"/"+path.split("/static/", 1)[1]
                    before = api.file(target)
                    assert sha(before) == old[path]
                    archive.writestr("static/"+path, before)
                    writes.append((target, before, content))
        backup_path = HOME+"/.config/mobile-web-service/common02/security-backup-"+release+".zip"
        api.file(backup_path, backup.getvalue())
        assert sha(api.file(backup_path)) == sha(backup.getvalue())
        for path, before, content in writes:
            print("Applying " + path.rsplit("/",1)[-1], flush=True)
            api.file(path, content)
            applied.append((path, before))
            assert sha(api.file(path)) == sha(content)
        api.request("POST", f"/webapps/{DOMAIN}/reload/", {})
        usage = verify_remote(api, active, release, new)
        assert_source_unchanged(manifest)
        patch = {"release":release,"parent_release":prior,"base_release":active["release"],
                 "backup":backup_path,"changed_files":sorted(changed),"phase":"verified",
                 "verified_utc":datetime.now(timezone.utc).isoformat()}
        active["verified_patch"] = patch
        api.file(BASE+"/active.json", json.dumps(active).encode())
        result = {"pass":True,"production_verified":True,"release":release,"changed_files":sorted(changed),
            "backup_verified":True,"original_media_preserved":True,"console_used":False,
            "django_schema_or_dependencies_changed":False,"paid_api_calls":0,
            "usage":usage,"verified_utc":patch["verified_utc"]}
    except Exception as error:
        for path, before in reversed(applied):
            if before is None:
                api.request("DELETE", "/files/path"+quote(path, safe="/"))
            else:
                api.file(path, before)
        if applied:
            api.request("POST", f"/webapps/{DOMAIN}/reload/", {})
        result = {"pass":False,"production_verified":False,"phase":"rolled_back" if applied else "not_activated",
                  "release":release,"failure_type":type(error).__name__,"production_files_changed":False,
                  "paid_api_calls":0,"checked_utc":datetime.now(timezone.utc).isoformat()}
        if isinstance(error, DeploymentError):
            result["reason"] = str(error)  # This class already withholds credentials and response bodies.
        (OUT/"deployment.json").write_text(json.dumps(result, indent=2)+"\n")
        print(json.dumps(result))
        raise SystemExit(1) from None
    (OUT/"deployment.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
