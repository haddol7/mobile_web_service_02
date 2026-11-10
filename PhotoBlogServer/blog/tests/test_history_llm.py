import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from blog.history_llm import generate
from photoblog.llm_config import load_llm_config


@override_settings(HISTORY_LLM_PROVIDER="openai", HISTORY_LLM_API_KEY="isolated-openai-test-key",
                   HISTORY_LLM_MODEL="gpt-4o-mini")
class HistoryLLMTests(SimpleTestCase):
    def setUp(self):
        # Response-validation cases use isolated counters; daily limits have dedicated tests.
        self.limit_folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.limit_folder.cleanup)
        limits = override_settings(SECURITY_STATE_ROOT=self.limit_folder.name, HISTORY_LLM_DAILY_LIMIT=50)
        limits.enable()
        self.addCleanup(limits.disable)
        self.retrieved = {"facts": {"passages": 2, "unknown_date_frames": 1},
            "interpretation": {"profile": None}, "evidence": [{"id": "frame-a", "source": "test",
                "observed_at": None, "video_seconds": 2.5, "time_basis": "unknown_recording_date",
                "image_url": "/private/test.jpg", "tracks": [{"candidate": "private-profile"}]}]}

    @staticmethod
    def response(answer="선 통과는 2건입니다.", ids=None, **choice):
        return json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"answer": answer, "evidence_ids": ["frame-a"] if ids is None else ids})},
            **choice}]}).encode()

    def generated(self, raw):
        with patch("blog.history_llm.urlopen") as mocked:
            mocked.return_value.__enter__.return_value.read.return_value = raw
            return generate("몇 번 통과했어?", self.retrieved)

    def test_openai_request_uses_strict_schema_and_only_retrieved_text(self):
        with patch("blog.history_llm.urlopen") as mocked:
            mocked.return_value.__enter__.return_value.read.return_value = self.response()
            self.assertEqual(generate("몇 번?", self.retrieved)["status"], "generated")
            request = mocked.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
            self.assertTrue(request.get_header("Authorization").startswith("Bearer "))
            self.assertFalse(body["store"])
            self.assertTrue(body["response_format"]["json_schema"]["strict"])
            citations = body["response_format"]["json_schema"]["schema"]["properties"]["evidence_ids"]
            self.assertEqual(citations["minItems"], 1)
            self.assertEqual(citations["items"]["enum"], ["frame-a"])
            self.assertEqual(body["max_completion_tokens"], 900)
            for private in ("image_url", "private-profile", "isolated-openai-test-key"):
                self.assertNotIn(private, request.data.decode())

    def test_invented_numbers_unknown_or_missing_citations_are_rejected(self):
        for raw in (self.response("선 통과는 999건입니다."), self.response(ids=["not-retrieved"]),
                    self.response(ids=[]), self.response(ids=[True]),
                    self.response("서로 다른 사람 수는 1명입니다."), self.response("두 명입니다.")):
            with self.subTest(raw=raw):
                self.assertEqual(self.generated(raw)["status"], "unavailable")

    def test_source_position_cannot_be_described_as_clip_length_or_dwell_time(self):
        for answer in ("영상의 길이는 2.5초입니다.","2.5초 동안 머물렀습니다."):
            self.assertEqual(self.generated(self.response(answer))["status"],"unavailable")
        self.assertEqual(self.generated(self.response("영상의 2.5초 지점에서 관측되었습니다."))["status"],"generated")

    def test_known_number_from_another_fact_cannot_be_used_as_passage_count(self):
        self.retrieved["facts"].update(observed_tracks=23, passages=6, source_count=3, candidate_tracks=4)
        for answer in ("선 통과는 23건입니다.", "추적 기록은 6개입니다.", "영상 출처는 4개입니다.", "얼굴 후보는 세 개입니다."):
            with self.subTest(answer=answer):
                self.assertEqual(self.generated(self.response(answer))["status"], "unavailable")
        for answer in ("추적 기록은 23개이고 선 통과는 6건입니다.", "영상 출처는 세 개입니다.", "3개의 영상에서 발견됐습니다.", "얼굴 후보는 4개입니다."):
            with self.subTest(answer=answer):
                self.assertEqual(self.generated(self.response(answer))["status"], "generated")

    def test_more_specific_confirmed_track_label_is_not_treated_as_all_tracks(self):
        self.retrieved["facts"].update(observed_tracks=4, confirmed_tracks=1, candidate_tracks=3)
        self.assertEqual(self.generated(self.response("확인된 추적 기록은 4개입니다."))["status"], "unavailable")
        self.assertEqual(self.generated(self.response("확인된 추적 기록은 1개이고 후보는 3개입니다."))["status"], "generated")

    def test_visit_counts_and_unlabelled_counts_are_not_supported(self):
        self.retrieved["facts"].update(observed_tracks=3, source_count=3)
        for answer in ("방문 횟수는 3회입니다.", "세 번 방문했습니다.", "총 3개입니다."):
            self.assertEqual(self.generated(self.response(answer))["status"], "unavailable")

    def test_recorded_two_source_answer_is_rejected_after_headwear_scope_has_one_source(self):
        self.retrieved["facts"].update(source_count=1,observed_tracks=1,dates=["2026-11-10"])
        recorded=("하대진의 모자 착용 촬영은 두 개의 출처에서 확인되었습니다. "
                  "첫 번째 출처는 '본인 모자 착용 웹캠 인식 확인'이며, "
                  "두 번째 출처는 '본인 웹캠 화면 이탈과 재진입 확인'입니다.")
        result=self.generated(self.response(recorded))
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["diagnostic"]["category"],"unsupported_count_or_date")

    def test_processing_date_cannot_be_relabelled_as_recording_date(self):
        self.retrieved["facts"].update(date_basis="processed", dates=["2026-11-10"])
        self.assertEqual(self.generated(self.response("촬영 날짜는 2026년 11월 10일입니다."))["status"], "unavailable")
        self.assertEqual(self.generated(self.response("분석 날짜는 2026년 11월 10일입니다. 촬영일은 알 수 없습니다."))["status"], "generated")

    def test_internal_evidence_ids_stay_out_of_answer_prose(self):
        key="a"*64;self.retrieved["evidence"][0]["id"]=key
        self.assertEqual(self.generated(self.response("근거 ID는 "+key+"입니다.",ids=[key]))["status"],"unavailable")

    def test_refusal_and_truncated_generation_are_not_accepted(self):
        for raw in (self.response(finish_reason="length"),
                    self.response(message={"refusal": "no", "content": None})):
            self.assertEqual(self.generated(raw)["status"], "unavailable")

    def test_http_failures_do_not_expose_provider_responses_or_credentials(self):
        for status in (401, 429, 500):
            with patch("blog.history_llm.urlopen", side_effect=HTTPError(
                    "https://api.openai.com/", status, "private provider message", None, None)):
                result = generate("기록", self.retrieved)
                self.assertEqual(result["status"], "unavailable")
                self.assertIsNone(result["text"])
                self.assertEqual(result["evidence_ids"], [])
                self.assertEqual(result["diagnostic"]["category"], "provider_http")
                self.assertEqual(result["diagnostic"]["http_status"], status)
                self.assertNotIn("private provider message", json.dumps(result))

    def test_timeout_preserves_unavailable_contract(self):
        with patch("blog.history_llm.urlopen", side_effect=TimeoutError):
            result = generate("기록", self.retrieved)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(result["diagnostic"]["category"], "provider_connection")

    def test_malformed_oversized_or_secret_output_is_rejected(self):
        for raw in (b"not-json", b"x"*65537, b"{}", self.response("isolated-openai-test-key")):
            self.assertEqual(self.generated(raw)["status"], "unavailable")

    def test_invalid_settings_never_make_a_network_request(self):
        for config in ({"HISTORY_LLM_PROVIDER": "unknown"}, {"HISTORY_LLM_API_KEY": ""},
                       {"HISTORY_LLM_API_KEY": "bad\nkey"}, {"HISTORY_LLM_MODEL": "../../invalid"}):
            with override_settings(**config), patch("blog.history_llm.urlopen") as mocked:
                self.assertEqual(generate("기록", self.retrieved)["status"], "not_configured")
                mocked.assert_not_called()

    def test_previous_messages_help_context_but_do_not_authorize_old_numbers(self):
        self.retrieved["conversation_context"]=[{"role":"user","content":"과거에는 999건이었어"}]
        self.assertEqual(self.generated(self.response("선 통과는 999건입니다."))["status"],"unavailable")
        with patch("blog.history_llm.urlopen") as mocked:
            mocked.return_value.__enter__.return_value.read.return_value=self.response()
            self.assertEqual(generate("그다음은?",self.retrieved)["status"],"generated")
            payload=json.loads(json.loads(mocked.call_args.args[0].data)["messages"][1]["content"])
            self.assertEqual(payload["conversation"][0]["role"],"user")


    def test_calendar_date_order_and_values_must_match_fact_dates(self):
        self.retrieved["facts"].update(date_basis="processed", dates=["2026-11-10"])
        for answer in ("분석 날짜는 2026년 10월 11일입니다.",
                       "분석 날짜는 2026-10-11입니다.", "분석 날짜는 10월 11일입니다."):
            with self.subTest(answer=answer):
                result = self.generated(self.response(answer))
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["diagnostic"]["category"], "unsupported_count_or_date")

    def test_known_calendar_dates_accept_iso_korean_and_partial_formats(self):
        self.retrieved["facts"].update(date_basis="processed", dates=["2026-11-10"])
        for label in ("2026년 11월 10일", "2026-11-10", "2026/11/10", "2026.11.10", "11월 10일"):
            with self.subTest(label=label):
                self.assertEqual(self.generated(self.response("분석 날짜는 " + label + "입니다."))["status"], "generated")

    def test_calendar_date_is_not_authorized_by_other_context_numbers(self):
        self.retrieved["facts"].update(date_basis="processed", dates=["2026-11-10"])
        self.retrieved["evidence"][0]["observed_at"] = "2026-11-11T00:00:00Z"
        self.assertEqual(self.generated(self.response("분석 날짜는 2026년 11월 11일입니다."))["status"], "unavailable")

    def test_invalid_calendar_day_and_date_without_known_facts_are_rejected(self):
        self.retrieved["facts"].update(date_basis="processed", dates=["2026-02-03"], observed_tracks=30)
        self.assertEqual(self.generated(self.response("분석 날짜는 2026년 2월 30일입니다."))["status"], "unavailable")
        self.retrieved["facts"]["dates"] = []
        self.assertEqual(self.generated(self.response("분석 날짜는 2026년 2월 3일입니다."))["status"], "unavailable")

    def test_partial_date_cannot_relabel_analysis_as_recording(self):
        self.retrieved["facts"].update(date_basis="processed", dates=["2026-11-10"])
        self.assertEqual(self.generated(self.response("촬영 날짜는 11월 10일입니다."))["status"], "unavailable")
        self.retrieved["facts"]["date_basis"] = "recorded"
        self.assertEqual(self.generated(self.response("촬영 날짜는 11월 10일입니다."))["status"], "generated")


class HistoryLLMConfigurationTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.location = self.home / ".config/mobile-web-service/common02/llm.json"

    def configure(self, raw):
        self.location.parent.mkdir(parents=True, exist_ok=True)
        self.location.write_text(raw)

    def test_missing_configuration_is_optional(self):
        self.assertEqual(load_llm_config({}, self.home), {"provider": "gemini", "api_key": "", "model": ""})

    def test_private_configuration_and_explicit_environment_override(self):
        self.configure(json.dumps({"provider": "openai", "api_key": "private-test-key", "model": "gpt-4o-mini"}))
        self.assertEqual(load_llm_config({}, self.home)["provider"], "openai")
        self.assertEqual(load_llm_config({"HISTORY_LLM_API_KEY": "", "HISTORY_LLM_MODEL": "other"}, self.home),
                         {"provider": "openai", "api_key": "", "model": "other"})

    def test_explicit_disable_does_not_read_private_configuration(self):
        self.configure("invalid private-test-key")
        self.assertEqual(load_llm_config({"HISTORY_LLM_CONFIG": ""}, self.home)["api_key"], "")

    def test_invalid_private_configuration_has_a_generic_error(self):
        for raw in ('{"api_key": 123}', "private-test-key", '[]', "x"*65537):
            self.configure(raw)
            with self.assertRaisesMessage(ImproperlyConfigured, "Cannot load the private history LLM configuration."):
                load_llm_config({}, self.home)
