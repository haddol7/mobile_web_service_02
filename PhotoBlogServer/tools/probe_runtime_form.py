"""Compare one harmless empty form request with fresh source, without exposing auth."""
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import platform
import re
import sys
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
BASE_URL = "http://127.0.0.1:8000"
OUTPUT = PROJECT_ROOT / "evidence" / "baseline" / "runtime-form-probe.json"


def csrf(html):
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^\"]+)"', html)
    if not match:
        raise RuntimeError("Local form did not contain a CSRF field.")
    return match.group(1)


def snapshot(Post, media_root):
    return {
        "post_count": Post.objects.count(),
        "post_ids": list(Post.objects.order_by("id").values_list("id", flat=True)),
        "media_files": sorted(str(path.relative_to(media_root)) for path in media_root.rglob("*") if path.is_file()),
    }


def form_observation(html):
    return {
        "errorlist_count": html.count('class="errorlist"'),
        "shows_required_field_errors": 'class="errorlist"' in html,
    }


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run the single local backend probe inside WSL.")
    sys.path.insert(0, str(SERVER_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photoblog.settings")
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory
    from blog.models import Post
    from blog.views import post_new

    media_root = Path(settings.MEDIA_ROOT)
    before = snapshot(Post, media_root)
    credentials = json.loads((PROJECT_ROOT / "evidence" / "private" / "local-author.json").read_text())
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    with opener.open(BASE_URL + "/accounts/login/", timeout=10) as response:
        login_html = response.read().decode("utf-8")
    login_body = urlencode({"username": credentials["username"], "password": credentials["password"], "csrfmiddlewaretoken": csrf(login_html)}).encode()
    login_request = Request(BASE_URL + "/accounts/login/", data=login_body, headers={"Referer": BASE_URL + "/accounts/login/"}, method="POST")
    with opener.open(login_request, timeout=10) as response:
        if response.geturl().rstrip("/") != BASE_URL:
            raise RuntimeError("Local fixture login failed; credentials are not printed.")
        response.read()
    with opener.open(BASE_URL + "/post/new/", timeout=10) as response:
        new_html = response.read().decode("utf-8")
    empty_post = Request(BASE_URL + "/post/new/", data=urlencode({"csrfmiddlewaretoken": csrf(new_html)}).encode(), headers={"Referer": BASE_URL + "/post/new/"}, method="POST")
    with opener.open(empty_post, timeout=10) as response:
        status = response.status
        runtime_html = response.read().decode("utf-8")
    # Freshly imported source, same local author, no session/DB mutation.
    source_request = RequestFactory().post("/post/new/", {}, HTTP_HOST="127.0.0.1:8000")
    source_request.user = get_user_model().objects.get(username=credentials["username"])
    source_response = post_new(source_request)
    source_html = source_response.content.decode("utf-8")
    logout_request = Request(BASE_URL + "/accounts/logout/", data=urlencode({"csrfmiddlewaretoken": csrf(runtime_html)}).encode(), headers={"Referer": BASE_URL + "/post/new/"}, method="POST")
    with opener.open(logout_request, timeout=10) as response:
        response.read()
    after = snapshot(Post, media_root)
    runtime = form_observation(runtime_html)
    source = form_observation(source_html)
    result = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "environment": "WSL " + os.environ["WSL_DISTRO_NAME"],
        "scope": "Single authenticated empty POST /post/new/ with valid CSRF, no photo/title/text submitted.",
        "side_effects": "Local fixture authentication/session lifecycle only; logged out after probe. No photo post or image change.",
        "runtime_http_status": status,
        "runtime_observation": runtime,
        "fresh_source_http_status": source_response.status_code,
        "fresh_source_observation": source,
        "runtime_matches_fresh_source": status == source_response.status_code and runtime == source,
        "actual_behavior_drift_proven": source["shows_required_field_errors"] and not runtime["shows_required_field_errors"],
        "before": before, "after": after,
        "photo_data_unchanged": before == after,
        "credentials_or_csrf_tokens_printed": False,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Actual single-request runtime comparison: {OUTPUT}")
    if before != after:
        raise SystemExit("Unexpected photo-data change; do not restart blindly.")


if __name__ == "__main__":
    main()
