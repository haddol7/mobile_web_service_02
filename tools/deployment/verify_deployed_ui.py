"""Read-only verification of the activated UI release and public access boundaries."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

import requests
import pythonanywhere_auth as auth
from pythonanywhere_deploy import API, BASE, DOMAIN, SERVER, WORKSPACE


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    if not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in WSL.")
    credentials = auth.load_credentials()
    api = API(credentials)
    state = json.loads(api.file(BASE + "/active.json"))
    assert state["phase"] == "verified"
    effective_release=state.get("verified_patch",state.get("frontend_overlay",{})).get("release",state["release"])
    package = WORKSPACE / "dist" / ("pythonanywhere-auto-" + effective_release + ".zip")
    manifest = json.loads(package.with_suffix(".json").read_text())
    assert sha(package.read_bytes()) == manifest["sha256"]
    for row in manifest["files"]:
        assert sha((SERVER / row["path"]).read_bytes()) == row["sha256"], row["path"]
    private = Path.home() / ".config/mobile-web-service/common02"
    llm = json.loads(auth.private_read(private / "llm.json"))
    app = json.loads(auth.private_read(private / "edge-auth.json"))
    needles = [llm["api_key"].encode(), app["token"].encode(), credentials["token"].encode()]
    files = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=WORKSPACE
    ).decode().split("\0")
    scanned = 0
    for name in files:
        path = WORKSPACE / name
        if name and path.is_file():
            value = path.read_bytes()
            assert not any(needle in value for needle in needles), "Private configuration in source tree"
            scanned += 1
    with zipfile.ZipFile(package) as archive:
        for name in archive.namelist():
            assert not any(needle in archive.read(name) for needle in needles), "Private configuration in package"
    origin = "https://" + DOMAIN
    probes = []
    for name in ("ui.css", "monitoring.css", "people.css", "person.mjs", "history.css", "history.mjs", "history-view.mjs"):
        path = "/static/blog/" + name
        response = requests.get(origin + path, timeout=(5, 25), allow_redirects=False)
        assert response.status_code == 200 and sha(response.content) == sha((SERVER / "blog/static/blog" / name).read_bytes())
        probes.append({"path": path, "status": response.status_code, "sha256": sha(response.content), "matches_local": True})
    for path in ("/", "/photos/", "/accounts/login/", "/api_root/", "/api_root/Post/"):
        response = requests.get(origin + path, timeout=(5, 25), allow_redirects=False)
        assert response.status_code == 200
        if path == "/":
            assert "감시 시스템" in response.text and "인물 관측 시스템" in response.text and "사진 블로그" not in response.text
        probes.append({"path": path, "status": response.status_code})
    for path in ("/detections/", "/history/", "/people/", "/people/showcase-v2-a/", "/questions/", "/api/v1/history/frames/", "/api/v1/history/overview/", "/api/v1/history/sessions/", "/api/v1/history/people/showcase-v2-a/", "/api/v1/history/references/showcase-v2-a/"):
        response = requests.get(origin + path, timeout=(5, 25), allow_redirects=False)
        if not path.startswith("/api/"):
            assert response.status_code == 302 and response.headers.get("Location", "").startswith("/accounts/login/")
        else:
            assert response.status_code in (401, 403)
        probes.append({"path": path, "status": response.status_code, "anonymous_access_denied": True})
    response = requests.get(origin + "/api/v1/history/overview/", headers={"Authorization": "Token " + app["token"]}, timeout=(5,25), allow_redirects=False)
    assert response.status_code == 200
    overview = response.json()
    assert all(name in overview for name in ("facts", "profiles", "recent_frames", "last_received_at"))
    probes.append({"path": "/api/v1/history/overview/", "status": 200, "owner_authenticated": True, "facts": overview["facts"]})
    record = {
        "verified_utc": datetime.now(timezone.utc).isoformat(), "environment": "WSL against PythonAnywhere",
        "origin": origin, "release": effective_release,"base_release":state["release"],"frontend_overlay":bool(state.get("frontend_overlay")), "package": package.relative_to(WORKSPACE).as_posix(),
        "package_sha256": manifest["sha256"], "package_files": len(manifest["files"]),
        "package_phase": "activated_and_verified", "scanned_files": scanned,
        "key_in_source_tree": False, "key_in_package": False, "app_token_in_source_tree": False,
        "deployment_token_in_source_tree": False, "cloud_deployed": True, "production_verified": True,
        "source_transition_verified": True, "console_ready": True, "probes": probes, "pass": True,
    }
    (WORKSPACE / "evidence/ui-audit/deployment.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
