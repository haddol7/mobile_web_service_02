import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from blog import history_embeddings as embedding
from blog.history_queries import retrieve
from blog.models import PersonTrack, TrackingFrame, TrackingSession
from .test_history import packet


def axis(index=0):
    values = [0.] * embedding.DIMENSIONS
    values[index] = 1.
    return values


def response(vectors):
    return json.dumps({"model": embedding.MODEL, "data": [
        {"index": i, "embedding": value} for i, value in enumerate(vectors)],
        "usage": {"prompt_tokens": 12, "total_tokens": 12}}).encode()


@override_settings(HISTORY_EMBEDDING_API_KEY="isolated-embedding-key")
class EmbeddingClientTests(SimpleTestCase):
    def setUp(self):
        self.limit_folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.limit_folder.cleanup)
        limits = override_settings(SECURITY_STATE_ROOT=self.limit_folder.name)
        limits.enable()
        self.addCleanup(limits.disable)
        self.transport = patch("blog.history_embeddings.urlopen").start()
        self.addCleanup(patch.stopall)
        self.transport.side_effect = AssertionError("Tests must never call a paid API.")

    def mock_response(self, raw):
        self.transport.side_effect = None
        self.transport.return_value.__enter__.return_value.read.return_value = raw

    def test_missing_approval_does_not_touch_transport(self):
        with self.assertRaises(embedding.EmbeddingError):
            embedding.embed_texts(["출국하는 영상"])
        self.transport.assert_not_called()

    def test_batch_uses_official_endpoint_and_normalizes_in_response_index_order(self):
        raw = json.loads(response([axis(0), axis(1)]))
        raw["data"].reverse()
        self.mock_response(json.dumps(raw).encode())
        result = embedding.embed_texts(["공항 출국", "기자 회견"], approved=True)
        self.assertEqual(result["vectors"], [axis(0), axis(1)])
        request = self.transport.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/embeddings")
        self.assertEqual(json.loads(request.data), {"model": embedding.MODEL, "dimensions": 512,
                         "encoding_format": "float", "input": ["공항 출국", "기자 회견"]})
        self.assertNotIn("isolated-embedding-key", request.data.decode())
        self.transport.assert_called_once()

    def test_invalid_or_excessive_inputs_never_request(self):
        for inputs in ([], [""], [True], ["a"] * 65, ["가"] * 2 + ["a" * 6001]):
            with self.subTest(inputs=str(inputs)[:40]), self.assertRaises(embedding.EmbeddingError):
                embedding.embed_texts(inputs, approved=True)
        self.transport.assert_not_called()

    def test_bad_vectors_and_response_shapes_are_rejected(self):
        for values in ([0.] * 512, axis()[:-1], [float("nan")] * 512, [True] * 512,
                       [10**400] * 512):
            self.mock_response(response([values]))
            with self.assertRaises(embedding.EmbeddingError):
                embedding.embed_texts(["자료"], approved=True)
        for raw in (b"[]", b"{}", b"not-json", b"x" * (2 * 1024 * 1024 + 1)):
            self.mock_response(raw)
            with self.assertRaises(embedding.EmbeddingError):
                embedding.embed_texts(["자료"], approved=True)

    def test_wrong_model_duplicate_or_missing_response_positions_are_rejected(self):
        base = json.loads(response([axis(), axis(1)]))
        variants = [{**base, "model": "other"}, {**base, "data": base["data"][:1]},
                    {**base, "data": [base["data"][0], base["data"][0]]}, {**base, "usage": []}]
        for value in variants:
            self.mock_response(json.dumps(value).encode())
            with self.assertRaises(embedding.EmbeddingError):
                embedding.embed_texts(["자료1", "자료2"], approved=True)

    def test_failure_never_retries_or_exposes_provider_error(self):
        self.transport.side_effect = HTTPError("https://api.openai.com/", 429, "private provider text", None, None)
        with self.assertRaises(embedding.EmbeddingError) as caught:
            embedding.embed_texts(["자료"], approved=True)
        self.assertNotIn("private provider text", str(caught.exception))
        self.assertEqual(caught.exception.api_requests, 1)
        self.transport.assert_called_once()

    def test_missing_key_makes_no_request(self):
        with override_settings(HISTORY_EMBEDDING_API_KEY=""), self.assertRaises(embedding.EmbeddingError):
            embedding.embed_texts(["자료"], approved=True)
        self.transport.assert_not_called()

    def test_title_terms_cover_domain_synonyms_without_changing_identity_or_dates(self):
        for question, title in (("비행기를 타러 떠나는 장면", "일본 출국"),
                                ("arriving at the gate", "입국 장면"),
                                ("언론에 설명", "백악관 브리핑"), ("security summit", "나토 정상회의"),
                                ("걸어오는 사람", "정면 보행"), ("signed documents", "서명 행사")):
            with self.subTest(question=question, title=title):
                self.assertGreater(embedding.title_match(question, title), 0)
        self.assertEqual(embedding.title_match("비행기를 타러 떠나는 장면", "보행자 영상"), 0)
        self.transport.assert_not_called()


class EmbeddingBuildTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        source = Path(settings.BASE_DIR).parent / "tools/build_embedding_index.py"
        spec = importlib.util.spec_from_file_location("embedding_build_test", source)
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name) / "index.json"
        self.doc = {"id": str(uuid4()), "text": "공항에서 비행기를 타고 출국하는 영상"}
        self.doc["sha256"] = embedding.digest(self.doc["text"])
        self.corpus = {**embedding.header(), "documents": [self.doc]}

    def test_dry_run_and_unapproved_apply_have_zero_calls_and_no_files(self):
        with patch.object(self.tool, "embed_texts") as mocked:
            plan = self.tool.build(self.corpus, self.output, ["출발하는 장면"])
            self.assertEqual((plan["api_requests_required"], plan["actual_api_calls"]), (1, 0))
            self.assertFalse(self.output.exists())
            for kwargs in ({"apply": True}, {"apply": True, "allow_paid_api": True, "max_api_calls": 0}):
                with self.assertRaises(embedding.EmbeddingError):
                    self.tool.build(self.corpus, self.output, **kwargs)
            mocked.assert_not_called()

    def test_documents_and_seed_queries_share_one_batch_and_rebuild_is_free(self):
        with patch.object(self.tool, "embed_texts", return_value={"vectors": [axis(), axis(1)], "usage": {}}) as mocked:
            result = self.tool.build(self.corpus, self.output, ["출발하는 장면"],
                                     apply=True, allow_paid_api=True, max_api_calls=1)
            self.assertEqual(result["actual_api_calls"], 1)
            self.assertEqual(mocked.call_args.args[0], [self.doc["text"], "출발하는 장면"])
            self.assertEqual(len(embedding.read_index(self.output)), 1)
            again = self.tool.build(self.corpus, self.output, ["출발하는 장면"], apply=True)
            self.assertEqual(again["actual_api_calls"], 0)
            mocked.assert_called_once()

    def test_changed_content_is_detected_and_invalid_corpus_is_not_sent(self):
        with patch.object(self.tool, "embed_texts") as mocked:
            self.corpus["documents"].append(self.doc)
            with self.assertRaises(embedding.EmbeddingError):
                self.tool.build(self.corpus, self.output, apply=True, allow_paid_api=True, max_api_calls=1)
            mocked.assert_not_called()

    def test_changed_document_is_the_only_pending_input(self):
        embedding.atomic_json(self.output, {**embedding.header(), "documents": [
            {"id": self.doc["id"], "sha256": self.doc["sha256"], "vector": axis()}]})
        self.doc["text"] = "기자회견 영상으로 수정"
        self.doc["sha256"] = embedding.digest(self.doc["text"])
        with patch.object(self.tool, "embed_texts") as mocked:
            plan = self.tool.build(self.corpus, self.output)
            self.assertEqual((plan["changed_documents"], plan["api_requests_required"]), (1, 1))
            mocked.assert_not_called()


@override_settings(BLOG_OWNER_USERNAME="publisher", HISTORY_EMBEDDING_API_KEY="isolated-embedding-key")
class EmbeddingRetrievalTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.setting = override_settings(HISTORY_MEDIA_ROOT=self.directory.name,
            HISTORY_EMBEDDING_INDEX=Path(self.directory.name) / ".semantic-index.json")
        self.setting.enable()
        self.addCleanup(self.setting.disable)
        cache.clear()
        self.owner = get_user_model().objects.create_user("publisher")
        self.other = get_user_model().objects.create_user("other")
        self.api = APIClient()
        self.api.force_authenticate(self.owner)
        self.transport = patch("blog.history_embeddings.urlopen", side_effect=AssertionError("Paid network blocked in tests.")).start()
        self.addCleanup(patch.stopall)
        self.ids = []
        for label, day in (("공항 출국", "07"), ("기자 회견", "08"), ("국제 안보 회의", "09")):
            value = packet()
            value["session"]["source_label"] = label
            value["frame"]["processed_at_utc"] = "2026-11-" + day + "T01:00:00+00:00"
            self.assertEqual(self.api.post("/api/v1/history/ingest/", value, format="json").status_code, 201)
            self.ids.append(str(TrackingSession.objects.get(source_label=label).pk))
        self.write_index()

    def write_index(self, questions=None):
        data = embedding.documents()
        embedding.atomic_json(embedding.index_path(), {**embedding.header(), "documents": [
            {"id": doc["id"], "sha256": doc["sha256"], "vector": axis(self.ids.index(doc["id"]))}
            for doc in data]})
        embedding.atomic_json(embedding.cache_path(), {**embedding.header(), "queries": {
            embedding.query_key(question): axis(position) for question, position in (questions or {"비행기를 타러 떠나는 장면": 0}).items()}})

    def test_default_query_does_not_embed_and_semantic_reorders_older_evidence(self):
        structured = retrieve({"date_basis": "processed"}, "비행기를 타러 떠나는 장면")
        result = retrieve({"semantic": True, "date_basis": "processed"}, "비행기를 타러 떠나는 장면")
        self.assertEqual(structured["facts"]["source_count"], 3)
        self.assertEqual(result["facts"]["source_count"], 1)
        self.assertEqual(result["evidence"][0]["source"], "공항 출국")
        self.assertEqual(result["retrieval"]["status"], "ranked")
        self.assertTrue(result["retrieval"]["query_cache_hit"])
        self.assertEqual(result["retrieval"]["api_requests"], 0)
        self.transport.assert_not_called()

    def test_explicit_headwear_description_excludes_reentry_even_when_vectors_are_identical(self):
        for key,title in zip(self.ids,("본인 모자 착용 웹캠 인식 확인","본인 웹캠 화면 이탈과 재진입 확인","본인 평소 모습 웹캠 인식 확인")):
            TrackingSession.objects.filter(pk=key).update(source_label=title)
        embedding.atomic_json(embedding.index_path(),{**embedding.header(),"documents":[
            {"id":d["id"],"sha256":d["sha256"],"vector":axis()} for d in embedding.documents()]})
        questions=("모자 착용 촬영을 찾아줘","후드 촬영을 찾아줘")
        embedding.atomic_json(embedding.cache_path(),{**embedding.header(),"queries":{embedding.query_key(q):axis() for q in questions}})
        for question in questions:
            result=retrieve({"semantic":True,"cache_only":True,"date_basis":"processed"},question)
            self.assertEqual(result["facts"]["source_count"],1)
            self.assertEqual([row["source"] for row in result["evidence"]],["본인 모자 착용 웹캠 인식 확인"])
            self.assertEqual(result["retrieval"]["metadata_candidate_sessions"],1)
        self.transport.assert_not_called()

    def test_unrecorded_source_condition_does_not_spend_on_a_query_or_infer_clothing(self):
        for question in ("모자 착용 촬영을 찾아줘","모자 안 쓴 촬영을 찾아줘"):
            result=retrieve({"semantic":True,"date_basis":"processed"},question)
            self.assertEqual(result["retrieval"]["status"],"no_match")
            self.assertEqual(result["facts"]["sampled_frames"],0)
        self.transport.assert_not_called()

    @override_settings(HISTORY_EMBEDDING_DAILY_LIMIT=0)
    def test_cached_search_still_works_at_zero_daily_quota(self):
        result = retrieve({"semantic": True, "date_basis": "processed"}, "비행기를 타러 떠나는 장면")
        self.assertEqual(result["retrieval"]["status"], "ranked")
        self.assertTrue(result["retrieval"]["query_cache_hit"])
        self.transport.assert_not_called()

    def configure_self_sources(self):
        titles = ("본인 모자 착용 웹캠 인식 확인", "본인 웹캠 화면 이탈과 재진입 확인", "본인 평소 모습 웹캠 인식 확인")
        for key, title in zip(self.ids, titles):
            TrackingSession.objects.filter(pk=key).update(source_label=title)
        self.write_index({"모자 착용 촬영을 찾아줘": 0})

    def test_negative_and_exclusion_conditions_ask_for_clarification_without_paid_calls(self):
        self.configure_self_sources()
        for question in ("모자를 착용하지 않은 촬영을 찾아줘", "모자 쓴 촬영은 제외해줘",
                         "후드를 안 쓴 촬영", "모자 없이 찍은 촬영", "재진입하지 않은 촬영", "모자 말고 평소 모습"):
            for semantic in (False, True):
                with self.subTest(question=question, semantic=semantic), patch("blog.history_api.generate") as llm:
                    result = self.api.post("/api/v1/history/ask/", {"question": question,
                        "semantic": semantic, "generate": True, "date_basis": "processed"}, format="json").json()
                    self.assertEqual(result["facts"]["source_count"], 0)
                    self.assertEqual(result["retrieval"]["condition_status"], "needs_clarification")
                    self.assertIn("조건을 구체적으로", result["answer"])
                    self.assertEqual(result["llm"]["status"], "not_requested")
                    llm.assert_not_called()
                    cache.clear()
        self.transport.assert_not_called()

    def test_positive_description_condition_is_kept_without_semantic_search(self):
        self.configure_self_sources()
        result = retrieve({"date_basis": "processed"}, "모자 착용 촬영을 찾아줘")
        self.assertEqual(result["facts"]["source_count"], 1)
        self.assertEqual(result["sources"][0]["label"], "본인 모자 착용 웹캠 인식 확인")
        self.assertEqual(result["retrieval"]["condition_status"], "applied")
        self.transport.assert_not_called()

    def test_review_invalidates_index_but_preserves_description_condition(self):
        self.configure_self_sources()
        track = PersonTrack.objects.get(session_id=self.ids[0])
        track.confirmed = track.candidate
        track.save()
        with patch("blog.history_api.generate") as llm:
            result = self.api.post("/api/v1/history/ask/", {"question": "모자 착용 촬영을 찾아줘",
                "semantic": True, "generate": True, "date_basis": "processed"}, format="json").json()
        self.assertEqual(result["retrieval"]["status"], "index_stale")
        self.assertEqual(result["facts"]["source_count"], 1)
        self.assertEqual(result["sources"][0]["label"], "본인 모자 착용 웹캠 인식 확인")
        self.assertIn("촬영 설명 조건을 유지", result["retrieval"]["message"])
        llm.assert_not_called()
        self.transport.assert_not_called()

    def test_missing_or_corrupt_index_does_not_expand_description_results(self):
        self.configure_self_sources()
        for mode in ("missing", "corrupt"):
            if mode == "missing":
                embedding.index_path().unlink()
            else:
                embedding.index_path().write_text("invalid index")
            with self.subTest(mode=mode), patch("blog.history_api.generate") as llm:
                result = self.api.post("/api/v1/history/ask/", {"question": "모자 착용 촬영을 찾아줘",
                    "semantic": True, "generate": True, "date_basis": "processed"}, format="json").json()
                self.assertEqual(result["facts"]["source_count"], 1)
                self.assertEqual(len(result["evidence"]), 1)
                self.assertIn("촬영 설명 조건을 유지", result["retrieval"]["message"])
                llm.assert_not_called()
                cache.clear()
        self.transport.assert_not_called()

    def test_description_scope_still_obeys_date_and_person_filters(self):
        self.configure_self_sources()
        for scope in ({"start": "2026-11-08", "end": "2026-11-09"}, {"profile": "person-a"}):
            result = retrieve({"semantic": True, "date_basis": "processed", **scope}, "모자 착용 촬영을 찾아줘")
            self.assertEqual(result["facts"]["sampled_frames"], 0)
            self.assertEqual(result["facts"]["source_count"], 0)
        self.transport.assert_not_called()

    @override_settings(HISTORY_EMBEDDING_DAILY_LIMIT=0)
    def test_quota_returns_record_answer_and_skips_both_paid_transports(self):
        with patch("blog.history_api.generate") as llm:
            response = self.api.post("/api/v1/history/ask/", {
                "question":"새로운 검색", "date_basis":"processed", "semantic":True, "generate":True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["retrieval"]["status"], "daily_limit")
        self.assertEqual(response.json()["retrieval"]["api_requests"], 0)
        self.assertEqual(response.json()["mode"], "records")
        self.assertEqual(response.json()["facts"]["source_count"], 3)
        llm.assert_not_called()
        self.transport.assert_not_called()

    def test_date_profile_and_session_filters_cannot_be_bypassed_by_semantic_similarity(self):
        for params in ({"start": "2026-11-09", "end": "2026-11-09"},
                       {"profile": "person-a"}, {"session": self.ids[1]}):
            result = retrieve({"semantic": True, "date_basis": "processed", **params}, "비행기를 타러 떠나는 장면")
            self.assertEqual(result["facts"]["sampled_frames"], 0)
        self.transport.assert_not_called()

    def test_missing_stale_or_corrupt_index_never_starts_a_paid_query(self):
        for mode in ("missing", "stale", "corrupt"):
            self.write_index()
            path = embedding.index_path()
            if mode == "missing":
                path.unlink()
            elif mode == "corrupt":
                path.write_text("private malformed content")
            else:
                TrackingSession.objects.filter(pk=self.ids[0]).update(source_label="바뀐 영상 설명")
            result = retrieve({"semantic": True}, "색인되지 않은 새 질문")
            self.assertEqual(result["facts"]["source_count"], 3)
            self.assertIn(result["retrieval"]["status"], ("index_missing", "index_stale", "unavailable"))
        self.transport.assert_not_called()

    def test_renaming_and_reviewing_a_person_invalidates_the_document(self):
        track = PersonTrack.objects.filter(session_id=self.ids[0]).get()
        track.confirmed = track.candidate
        track.save()
        result = retrieve({"semantic": True}, "새 질문")
        self.assertEqual(result["retrieval"]["status"], "index_stale")
        self.transport.assert_not_called()

    def test_repeated_query_persists_vector_and_performs_one_mocked_request(self):
        self.transport.side_effect = None
        self.transport.return_value.__enter__.return_value.read.return_value = response([axis()])
        first = retrieve({"semantic": True}, "  공항에서   떠나는 장면 ")
        second = retrieve({"semantic": True}, "공항에서 떠나는 장면")
        self.assertEqual(first["retrieval"]["api_requests"], 1)
        self.assertEqual(second["retrieval"]["api_requests"], 0)
        self.transport.assert_called_once()

    def test_corpus_export_requires_owner_and_contains_no_pixels_or_face_embeddings(self):
        path = "/api/v1/history/embedding-documents/"
        self.assertEqual(APIClient().get(path).status_code, 401)
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(path).status_code, 403)
        self.api.force_authenticate(self.owner)
        response_value = self.api.get(path)
        self.assertEqual(response_value["Cache-Control"], "private, no-store")
        self.assertEqual(len(response_value.json()["documents"]), 3)
        for doc in response_value.json()["documents"]:
            self.assertNotIn("image_url", doc["text"])
            self.assertNotIn("buffalo_l", doc["text"])
            self.assertIn("미확인 얼굴 후보", doc["text"])
        self.transport.assert_not_called()

    def test_index_failure_skips_llm_and_default_api_flags_do_not_generate(self):
        embedding.index_path().unlink()
        with patch("blog.history_api.generate") as llm:
            result = self.api.post("/api/v1/history/ask/", {"question": "새 질문", "semantic": True, "generate": True}, format="json")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["llm"]["status"], "not_requested")
            llm.assert_not_called()
        self.transport.assert_not_called()

    def test_semantic_endpoint_returns_exact_aggregates_and_independent_llm_opt_in(self):
        with patch("blog.history_api.generate") as llm:
            result = self.api.post("/api/v1/history/ask/", {"question": "비행기를 타러 떠나는 장면", "semantic": True}, format="json")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["facts"]["sampled_frames"], 1)
            self.assertEqual(result.json()["llm"]["status"], "not_requested")
            self.assertIn("최대 5개 영상", result.json()["answer"])
            self.assertFalse(result.json()["answer"].startswith("의미 검색"))
            llm.assert_not_called()
        self.transport.assert_not_called()

    def test_empty_scope_does_not_make_a_query_embedding(self):
        result = retrieve({"semantic": True, "date_basis": "processed", "start": "2030-01-01"}, "새 질문")
        self.assertEqual(result["retrieval"]["status"], "empty")
        self.transport.assert_not_called()

    def test_unsupported_metadata_is_not_invented_in_documents(self):
        corpus = embedding.documents()
        self.assertTrue(all("확인된 촬영 날짜: 미상" in doc["text"] for doc in corpus))
        self.assertTrue(all("촬영일과 구분" in doc["text"] for doc in corpus))
        self.assertFalse(any("옷" in doc["text"] for doc in corpus))

    def test_failed_paid_attempt_is_counted_once_and_uses_no_llm(self):
        self.transport.side_effect = HTTPError("https://api.openai.com/", 500, "private provider failure", None, None)
        with patch("blog.history_api.generate") as llm:
            result = self.api.post("/api/v1/history/ask/", {"question": "새 질문", "semantic": True, "generate": True}, format="json").json()
            self.assertEqual(result["retrieval"]["status"], "unavailable")
            self.assertEqual(result["retrieval"]["api_requests"], 1)
            self.assertNotIn("private provider failure", json.dumps(result))
            self.transport.assert_called_once()
            llm.assert_not_called()

    def test_in_progress_query_does_not_start_another_paid_call(self):
        with embedding.query_lock():
            result = retrieve({"semantic": True}, "새 질문")
        self.assertEqual(result["retrieval"]["status"], "unavailable")
        self.assertEqual(result["retrieval"]["api_requests"], 0)
        self.transport.assert_not_called()

    def test_no_similar_document_returns_no_evidence(self):
        self.write_index({"설명과 관계없는 질문": 4})
        result = retrieve({"semantic": True}, "설명과 관계없는 질문")
        self.assertEqual(result["retrieval"]["status"], "no_match")
        self.assertEqual(result["facts"]["source_count"], 0)
        self.assertEqual(result["evidence"], [])
        self.transport.assert_not_called()

    def test_semantic_throttling_stops_the_next_query_without_a_paid_call(self):
        first = self.api.post("/api/v1/history/ask/", {"question": "비행기를 타러 떠나는 장면", "semantic": True}, format="json")
        second = self.api.post("/api/v1/history/ask/", {"question": "다른 질문", "semantic": True}, format="json")
        self.assertEqual((first.status_code, second.status_code), (200, 429))
        self.transport.assert_not_called()

    def test_cache_only_verification_never_generates_a_missing_query_vector(self):
        for question in ("비행기를 타러 떠나는 장면", "색인에 없는 질문"):
            result = retrieve({"semantic": True, "cache_only": True}, question)
            self.assertEqual(result["retrieval"]["api_requests"], 0)
        with patch("blog.history_api.generate") as llm:
            result = self.api.post("/api/v1/history/ask/", {"question": "질문", "semantic": True,
                "cache_only": True, "generate": True}, format="json")
            self.assertEqual(result.status_code, 400)
            llm.assert_not_called()
        self.transport.assert_not_called()
