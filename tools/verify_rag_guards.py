"""Record RAG regression outputs in WSL using mocked transport and an isolated DB."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PhotoBlogServer"))
os.chdir(ROOT / "PhotoBlogServer")
temporary = tempfile.TemporaryDirectory(prefix="rag-guard-proof-")
os.environ.update(DJANGO_SETTINGS_MODULE="photoblog.settings", HISTORY_LLM_CONFIG="",
                  HISTORY_LLM_API_KEY="", HISTORY_EMBEDDING_API_KEY="", SECURITY_STATE_ROOT=temporary.name)
import django
django.setup()
from django.conf import settings
from django.core.cache import cache
from django.test.utils import get_runner
from blog.tests.test_embeddings import EmbeddingRetrievalTests
from blog.tests.test_history_llm import HistoryLLMTests
from blog.models import PersonTrack

cases = []


class DateGuardProof(HistoryLLMTests):
    def test_record_calendar_validation(self):
        self.retrieved["facts"].update(date_basis="processed", dates=["2026-11-10"])
        for label, answer, expected in (
            ("correct_date", "분석 날짜는 2026년 11월 10일입니다.", "generated"),
            ("swapped_month_day", "분석 날짜는 2026년 10월 11일입니다.", "unavailable"),
            ("partial_swapped_date", "분석 날짜는 10월 11일입니다.", "unavailable"),
            ("recording_date_relabelled", "촬영 날짜는 11월 10일입니다.", "unavailable")):
            result = self.generated(self.response(answer))
            self.assertEqual(result["status"], expected)
            cases.append({"case": label, "facts_dates": ["2026-11-10"], "mock_provider_answer": answer,
                          "expected": expected, "actual": result, "pass": True})


class ScopeGuardProof(EmbeddingRetrievalTests):
    def ask(self, question):
        cache.clear()
        with patch("blog.history_api.generate") as generated:
            result = self.api.post("/api/v1/history/ask/", {"question": question, "semantic": True,
                "generate": True, "date_basis": "processed"}, format="json").json()
            generated.assert_not_called()
        self.transport.assert_not_called()
        return result

    def test_record_query_scope(self):
        self.configure_self_sources()
        for question in ("모자를 착용하지 않은 촬영을 찾아줘", "모자 쓴 촬영은 제외해줘"):
            result = self.ask(question)
            self.assertEqual(result["retrieval"]["condition_status"], "needs_clarification")
            self.assertEqual(result["facts"]["source_count"], 0)
            cases.append({"case": "negative_condition", "question": question, "actual": result, "pass": True})
        track = PersonTrack.objects.get(session_id=self.ids[0])
        track.confirmed = track.candidate
        track.save()
        for stage in ("index_stale_after_review", "index_missing"):
            if stage == "index_missing":
                from blog.history_embeddings import index_path
                index_path().unlink()
            result = self.ask("모자 착용 촬영을 찾아줘")
            self.assertEqual(result["facts"]["source_count"], 1)
            self.assertEqual(result["sources"][0]["label"], "본인 모자 착용 웹캠 인식 확인")
            cases.append({"case": stage, "question": "모자 착용 촬영을 찾아줘", "actual": result, "pass": True})


if __name__ == "__main__":
    runner = get_runner(settings)(verbosity=2, interactive=False)
    failures = runner.run_tests(["__main__.DateGuardProof.test_record_calendar_validation",
                                "__main__.ScopeGuardProof.test_record_query_scope"])
    result = {"environment": "WSL Ubuntu project virtualenv", "scope": "mock provider and isolated Django test database",
              "real_provider_calls": 0, "production_requests": 0, "failures": failures,
              "checks": cases, "pass": failures == 0 and len(cases) == 8,
              "limitations": "Regression of supported date and metadata expressions; not a paid model accuracy benchmark."}
    output = ROOT / "evidence/history/rag-guard-improvement-20261110.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checks": len(cases), "pass": result["pass"], "real_provider_calls": 0}))
    temporary.cleanup()
    raise SystemExit(not result["pass"])
