"""Run three bounded real LLM calls against the existing disposable history fixture."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run inside the project WSL environment.")
    latest = json.loads((ROOT / "evidence/history/latest-fixture.json").read_text())
    fixture = (ROOT / latest["fixture"]).resolve()
    if not fixture.is_relative_to((ROOT / "evidence/private/history").resolve()):
        raise SystemExit("Invalid disposable fixture path.")
    os.environ.update(DJANGO_SETTINGS_MODULE="photoblog.settings", DJANGO_DEBUG="true",
        DJANGO_DB_PATH=str(fixture / "db.sqlite3"), BLOG_OWNER_USERNAME="daejinha")
    sys.path.insert(0, str(ROOT / "PhotoBlogServer"))
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.cache import cache
    from rest_framework.test import APIClient
    if settings.HISTORY_LLM_PROVIDER != "openai" or not settings.HISTORY_LLM_API_KEY:
        raise SystemExit("OpenAI private configuration is required.")
    api = APIClient(HTTP_HOST="localhost")
    api.force_authenticate(get_user_model().objects.get(username="daejinha"))
    calls = []
    def observed_open(request, **kwargs):
        call = {"endpoint": request.full_url, "http_status": None}
        calls.append(call)
        try:
            response = urlopen(request, **kwargs)
            call["http_status"] = response.status
            original_read = response.read
            def observed_read(amount):
                raw = original_read(amount)
                try:
                    payload = json.loads(raw)
                    (private / f"provider-{len(calls)}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n")
                    usage = payload.get("usage", {})
                    call["total_tokens"] = usage.get("total_tokens")
                except (ValueError, TypeError):
                    pass
                return raw
            response.read = observed_read
            return response
        except HTTPError as error:
            call["http_status"] = error.code
            try:
                code = json.loads(error.read(65536)).get("error", {}).get("code")
                if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", code):
                    call["error_code"] = code
            except (ValueError, TypeError, AttributeError):
                pass
            raise
    cases = []
    private = ROOT / "evidence/private/history-llm" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    private.mkdir(parents=True, exist_ok=True)
    questions = ["선 통과는 몇 건이며, 서로 다른 사람 수로 볼 수 있어?",
                 "촬영 날짜를 알 수 있는 기록이 있어? 모르면 모른다고 해줘.",
                 "2020-01-01에 사람이 없었어?"]
    for index, question in enumerate(questions):
        cache.clear()
        with patch("blog.history_llm.urlopen", side_effect=observed_open):
            response = api.post("/api/v1/history/ask/", {"question": question, "generate": True}, format="json")
        result = response.json()
        (private / f"case-{index+1}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
        generated = result.get("llm", {})
        allowed = {item["id"] for item in result.get("evidence", [])}
        passed = (response.status_code == 200 and result.get("mode") == "rag"
                  and generated.get("status") == "generated"
                  and set(generated.get("evidence_ids", [])) <= allowed)
        cases.append({"question": question, "http_status": response.status_code, "mode": result.get("mode"),
            "llm_status": generated.get("status"), "answer": generated.get("text"),
            "facts": result.get("facts"), "citation_count": len(generated.get("evidence_ids", [])), "pass": passed})
        if not passed:
            break
    sources = ["PhotoBlogServer/blog/history_llm.py", "PhotoBlogServer/photoblog/llm_config.py",
               "PhotoBlogServer/photoblog/settings.py", "tools/verify_history_llm.py"]
    record = {"verified_utc": datetime.now(timezone.utc).isoformat(), "environment": "WSL Ubuntu",
        "provider": settings.HISTORY_LLM_PROVIDER, "model": settings.HISTORY_LLM_MODEL,
        "actual_llm_generation_verified": len(cases) == 3 and all(c["pass"] for c in cases),
        "production_verified": False, "key_in_source_tree": False, "media_sent_to_provider": False,
        "canonical_db_answer_preserved": True, "calls": calls, "cases": cases,
        "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}}
    record["pass"] = record["actual_llm_generation_verified"]
    (ROOT / "evidence/history/llm-verification.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"pass": record["pass"], "provider": record["provider"], "model": record["model"],
                      "calls": calls, "cases": cases}, ensure_ascii=False))
    if not record["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
