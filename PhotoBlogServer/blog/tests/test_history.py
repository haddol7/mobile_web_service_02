from copy import deepcopy
from datetime import datetime, timezone as utc
import hashlib
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from blog.models import PersonProfile, PersonTrack, TrackingFrame, TrackingSession, PassageEvent, PersonObservation
from blog.history_queries import retrieve, date_range
from .helpers import uploaded_photo


def packet(session=None, index=1, *, started=None, direction=None, candidate=True, kind="video"):
    session = session or uuid4().hex
    key = hashlib.sha256(f"{session}:1:{index}:{direction}".encode()).hexdigest()
    return {"schema_version": 1, "session": {"id": session, "source_label": "테스트 영상", "source_kind": kind,
        "recording_started_at": started, "model_versions": {"face_model": "buffalo_l"},
        "profiles": [{"id": "person-a", "name": "등록 인물 A"}]},
        "frame": {"frame_index": index, "video_seconds": float(index-1),
            "processed_at_utc": "2026-11-08T01:00:00+00:00", "captured_at": None,
            "tracks": [{"track_id": 1, "bbox": [0, 0, 100, 100]}],
            "faces": [{"bbox": [10, 10, 40, 40], "body_track_id": 1,
                       "candidate_profile_id": "person-a" if candidate else None,
                       "similarity": .8 if candidate else .1, "margin": .3,
                       "detection_score": .9, "status": "candidate" if candidate else "unresolved"}],
            "crossings": [{"event_id": key, "track_id": 1, "direction": direction}] if direction else []}}


@override_settings(BLOG_OWNER_USERNAME="publisher")
class HistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("publisher")
        cls.other = get_user_model().objects.create_superuser("other", "other@example.test", "isolated-history-test")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        setting = override_settings(HISTORY_MEDIA_ROOT=self.directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        cache.clear()
        self.api = APIClient()
        self.api.force_authenticate(self.owner)

    def send(self, value, *, image=False):
        if image:
            return self.api.post("/api/v1/history/ingest/", {"packet": json.dumps(value), "image": uploaded_photo()}, format="multipart")
        return self.api.post("/api/v1/history/ingest/", value, format="json")

    def test_duplicate_replay_does_not_duplicate_frames_tracks_or_passages(self):
        value = packet(direction="in")
        self.assertEqual(self.send(value).status_code, 201)
        self.assertEqual(self.send(value).status_code, 200)
        self.assertEqual((TrackingSession.objects.count(), TrackingFrame.objects.count(),
                          PersonTrack.objects.count(), PersonObservation.objects.count(), PassageEvent.objects.count()), (1,1,1,1,1))

    def test_conflicting_frame_or_session_is_rejected(self):
        value = packet()
        self.send(value)
        conflict = deepcopy(value)
        conflict["frame"]["tracks"][0]["bbox"][0] = 2
        self.assertEqual(self.send(conflict).status_code, 409)
        conflict = deepcopy(value)
        conflict["frame"]["frame_index"] = 2
        conflict["session"]["source_label"] = "다른 영상"
        self.assertEqual(self.send(conflict).status_code, 409)
        self.assertEqual(TrackingFrame.objects.count(), 1)

    def test_untrusted_and_invalid_packets_are_rejected_without_rows(self):
        values = []
        value = packet(); value["frame"]["tracks"][0]["bbox"][2] = -1; values.append(value)
        value = packet(); value["frame"]["tracks"].append(value["frame"]["tracks"][0]); values.append(value)
        value = packet(); value["frame"]["faces"][0]["candidate_profile_id"] = "not-registered"; values.append(value)
        value = packet(direction="in"); value["frame"]["crossings"][0]["event_id"] = "a"*64; values.append(value)
        value = packet(); value["frame"]["processed_at_utc"] = "2026-11-08T10:00:00"; values.append(value)
        value = packet(); value["frame"]["confirmed_profile_id"] = "person-a"; values.append(value)
        value = packet(); value["session"]["model_versions"] = {str(i): "x" for i in range(11)}; values.append(value)
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(self.send(value).status_code, 400)
        self.assertEqual(TrackingSession.objects.count(), 0)

    def test_nonfinite_number_rejected(self):
        value = packet()
        value["frame"]["video_seconds"] = "nan"
        self.assertEqual(self.send(value).status_code, 400)

    def test_unassigned_face_is_retained_without_forcing_identity(self):
        value = packet()
        value["frame"]["faces"][0]["body_track_id"] = None
        self.assertEqual(self.send(value).status_code, 201)
        self.assertEqual(len(TrackingFrame.objects.get().unassigned_faces), 1)
        self.assertIsNone(PersonTrack.objects.get().candidate_id)

    def test_two_faces_inside_one_track_are_not_assigned(self):
        value = packet()
        value["frame"]["faces"].append(deepcopy(value["frame"]["faces"][0]))
        self.send(value)
        self.assertIsNone(PersonTrack.objects.get().candidate_id)

    def test_candidate_is_not_confirmation_and_profile_search_requires_opt_in(self):
        self.send(packet())
        track = PersonTrack.objects.get()
        self.assertEqual(track.candidate_id, "person-a")
        self.assertIsNone(track.confirmed_id)
        self.assertEqual(retrieve({"profile": "person-a"})["facts"]["observed_tracks"], 0)
        self.assertEqual(retrieve({"profile": "person-a", "include_candidates": True})["facts"]["observed_tracks"], 1)

    def test_manual_review_has_revision_and_can_clear_identity(self):
        self.send(packet())
        track = PersonTrack.objects.get()
        path = f"/api/v1/history/tracks/{track.pk}/"
        self.assertEqual(self.api.patch(path, {"revision": 1, "profile": "person-a"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch(path, {"revision": 1, "profile": None}, format="json").status_code, 409)
        self.assertEqual(retrieve({"profile": "person-a"})["facts"]["confirmed_tracks"], 1)
        self.assertEqual(self.api.patch(path, {"revision": 2, "profile": None}, format="json").status_code, 200)
        self.assertEqual(retrieve({"profile": "person-a", "include_candidates": True})["facts"]["observed_tracks"], 0)

    def test_tracking_ids_are_scoped_to_sessions_and_confirmation_not_propagated(self):
        first = packet(); self.send(first)
        track = PersonTrack.objects.get()
        self.api.patch(f"/api/v1/history/tracks/{track.pk}/", {"revision": 1, "profile": "person-a"}, format="json")
        self.send(packet())
        self.assertEqual(PersonTrack.objects.count(), 2)
        self.assertEqual(PersonTrack.objects.filter(confirmed__isnull=False).count(), 1)

    def test_unknown_recording_date_is_not_processing_date(self):
        self.send(packet())
        self.assertIsNone(TrackingFrame.objects.get().observed_at)
        self.assertEqual(retrieve({})["facts"]["unknown_date_frames"], 1)
        self.assertEqual(retrieve({"start": "2026-11-08", "end": "2026-11-08"})["facts"]["sampled_frames"], 0)

    def test_known_video_relative_time_and_korean_day_boundary(self):
        start = "2026-11-07T23:59:59+09:00"
        first = packet(started=start, direction="in")
        self.send(first)
        self.send(packet(first["session"]["id"], 2, started=start, direction="out"))
        result = retrieve({"start": "2026-11-08", "end": "2026-11-08"})
        self.assertEqual(result["facts"]["dates"], ["2026-11-08"])
        self.assertEqual(result["facts"]["passages"], 1)
        self.assertEqual(result["facts"]["direction_out"], 1)

    def test_live_requires_explicit_received_time(self):
        value = packet(kind="live")
        self.assertEqual(self.send(value).status_code, 400)
        value["frame"]["captured_at"] = "2026-11-08T09:00:00+09:00"
        self.assertEqual(self.send(value).status_code, 201)
        self.assertIsNotNone(TrackingFrame.objects.get().observed_at)

    def test_out_of_order_observations_keep_track_extent(self):
        first = packet(index=20); self.send(first)
        self.send(packet(first["session"]["id"], 2))
        track = PersonTrack.objects.get()
        self.assertEqual((track.first_frame, track.last_frame), (2,20))

    def test_invalid_post_rolls_back_session_and_profile(self):
        value = packet(); value["post_id"] = 999999
        self.assertEqual(self.send(value, image=True).status_code, 400)
        self.assertEqual(TrackingSession.objects.count(), 0)
        self.assertEqual(PersonProfile.objects.count(), 0)

    def test_private_snapshot_and_api_require_configured_owner(self):
        response = self.send(packet(), image=True)
        self.assertEqual(response.status_code, 201)
        path = f'/api/v1/history/images/{response.json()["id"]}/'
        response = self.api.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get(path).status_code, 401)
        self.api.force_authenticate(self.other)
        for endpoint in [path, "/api/v1/history/frames/", "/api/v1/history/profiles/"]:
            self.assertEqual(self.api.get(endpoint).status_code, 403)
        self.assertEqual(self.api.post("/api/v1/history/ask/", {"question": "몇 번?"}, format="json").status_code, 403)

    def test_frames_are_bounded_and_private(self):
        self.send(packet())
        self.assertEqual(self.api.get("/api/v1/history/frames/?limit=25").status_code, 400)
        response = self.api.get("/api/v1/history/frames/?limit=1").json()
        self.assertEqual(len(response["results"]), 1)
        self.assertIn("tracks", response["results"][0])

    def test_questions_return_exact_counts_and_evidence_without_llm_key(self):
        self.send(packet(direction="in"))
        response = self.api.post("/api/v1/history/ask/", {"question": "몇 번 통과했어?"}, format="json")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["mode"], "records")
        self.assertEqual(result["facts"]["passages"], 1)
        self.assertEqual(result["facts"]["confirmed_profiles"], 0)
        self.assertIn("선 통과는 1건", result["answer"])
        self.assertEqual(len(result["evidence"]), 1)

    @override_settings(HISTORY_LLM_API_KEY="", HISTORY_LLM_MODEL="")
    def test_missing_generation_auth_is_explicit_and_retrieval_still_works(self):
        response = self.api.post("/api/v1/history/ask/", {"question": "기록", "generate": True}, format="json").json()
        self.assertEqual(response["mode"], "records")
        self.assertEqual(response["llm"]["status"], "not_configured")

    def test_ambiguous_person_and_unsupported_date_need_clarification(self):
        for question in ["이 사람 언제 왔어?", "11월 2일 몇 번 왔어?"]:
            self.assertEqual(self.api.post("/api/v1/history/ask/", {"question": question}, format="json").status_code, 400)
        self.assertEqual(self.api.get("/api/v1/history/frames/?start=2026-13-20").status_code, 400)

    def test_owner_web_page_exists_without_publishing_history_publicly(self):
        self.assertEqual(self.client.get("/history/").status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get("/history/").status_code, 403)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get("/history/"), "기록에 질문하기")

    @override_settings(HISTORY_LLM_PROVIDER="gemini", HISTORY_LLM_API_KEY="isolated-test-key", HISTORY_LLM_MODEL="test-model")
    def test_generation_validates_citations_and_rejects_invented_numbers(self):
        from blog.history_llm import generate
        self.send(packet())
        retrieved = retrieve({})
        cite = retrieved["evidence"][0]["id"]
        def result(answer, ids):
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(
                {"answer": answer, "evidence_ids": ids})}]}}]}).encode()
        with patch("blog.history_llm.urlopen") as mocked:
            mocked.return_value.__enter__.return_value.read.return_value = result("추적 기록은 1개입니다.", [cite])
            generated = generate("얼마나?", retrieved)
            self.assertEqual(generated["status"], "generated")
            self.assertNotIn("image_url", mocked.call_args.args[0].data.decode())
            mocked.return_value.__enter__.return_value.read.return_value = result("99999명이 왔습니다.", [cite])
            self.assertEqual(generate("얼마나?", retrieved)["status"], "unavailable")
            mocked.return_value.__enter__.return_value.read.return_value = result("추적 기록은 1개입니다.", ["fake"])
            self.assertEqual(generate("얼마나?", retrieved)["status"], "unavailable")

    def test_empty_result_does_not_assert_absence(self):
        response = self.api.post("/api/v1/history/ask/", {"question": "몇 명?"}, format="json").json()
        self.assertIn("판단할 수는 없습니다", response["answer"])
