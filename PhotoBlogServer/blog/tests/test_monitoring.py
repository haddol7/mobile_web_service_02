import tempfile
import re
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from .test_history import packet
from .helpers import uploaded_photo
from blog.models import PersonTrack, PersonProfile, Post, TrackingFrame


@override_settings(BLOG_OWNER_USERNAME="publisher")
class MonitoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user("publisher")
        cls.other = get_user_model().objects.create_user("viewer")

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = override_settings(HISTORY_MEDIA_ROOT=directory.name, MEDIA_ROOT=directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.api = APIClient()
        self.api.force_authenticate(self.owner)

    def send(self, value):
        response = self.api.post("/api/v1/history/ingest/", value, format="json")
        self.assertEqual(response.status_code, 201)

    def test_summary_and_pages_are_available_to_visitors_and_other_accounts(self):
        for path in ("/people/", "/history/", "/detections/", "/questions/"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/history/overview/").status_code, 200)
        self.client.force_login(self.other)
        for path in ("/people/", "/history/", "/detections/", "/questions/", "/api/v1/history/overview/"):
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_summary_distinguishes_candidates_confirmations_and_passages(self):
        self.send(packet(direction="in"))
        data = self.api.get("/api/v1/history/overview/").json()
        self.assertEqual((data["facts"]["pending_tracks"], data["facts"]["passages"], data["facts"]["sampled_frames"]), (1, 1, 1))
        self.assertEqual(data["profiles"][0]["candidate_tracks"], 1)
        track = PersonTrack.objects.get()
        self.api.patch(f"/api/v1/history/tracks/{track.pk}/", {"revision": track.revision, "profile": "person-a"}, format="json")
        data = self.api.get("/api/v1/history/overview/").json()
        self.assertEqual(data["facts"]["pending_tracks"], 0)
        self.assertEqual(data["profiles"][0]["confirmed_tracks"], 1)
        self.assertEqual(data["profiles"][0]["candidate_tracks"], 0)
        self.assertIsNone(data["profiles"][0]["last_observed_at"])
        self.assertIsNone(data["recent_frames"][0]["observed_at"])

    def test_enrolled_faces_are_visible_before_the_first_observation(self):
        self.send(packet())
        PersonProfile.objects.create(key="enrolled",display_name="출입 인물 02")
        PersonProfile.objects.create(key="empty",display_name="빈 시험 자료")
        result=self.api.post("/api/v1/history/references/enrolled/",{"image":uploaded_photo()},format="multipart")
        self.assertEqual(result.status_code,200)
        overview=self.api.get("/api/v1/history/overview/").json()
        self.assertEqual({row["key"] for row in overview["visible_profiles"]},{"person-a","enrolled"})
        enrolled=next(row for row in overview["visible_profiles"] if row["key"]=="enrolled")
        self.assertFalse(enrolled["active"])
        self.assertEqual(enrolled["source_count"],0)
        self.assertTrue(enrolled["portrait_url"])
        self.client.force_login(self.owner)
        page=self.client.get("/people/")
        self.assertContains(page,"출입 인물 02")
        self.assertContains(page,"등록 완료, 발견 대기")
        self.assertNotContains(page,"빈 시험 자료")

    def test_operator_dashboard_and_guest_landing_have_different_data(self):
        self.send(packet())
        response = self.client.get("/")
        self.assertNotContains(response, "테스트 영상")
        self.assertNotContains(response, "등록 인물 A")
        self.assertContains(response, "운영자 로그인")
        self.client.force_login(self.owner)
        response = self.client.get("/")
        self.assertContains(response, 'id="history-grid"')
        self.assertContains(response, 'aria-label="전체 저장 기록 집계"')
        self.assertEqual(response.context["monitor"]["facts"]["sampled_frames"], 1)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        for path in ("/people/", "/questions/", "/detections/"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertContains(self.client.get("/people/"), "발견 이력 보기")
        self.assertContains(self.client.get("/questions/"), 'id="chat-thread"')

    def test_profile_counts_do_not_multiply_when_a_track_has_multiple_frames(self):
        first = packet()
        self.send(first)
        self.send(packet(session=first["session"]["id"], index=2))
        track = PersonTrack.objects.get()
        self.api.patch(f"/api/v1/history/tracks/{track.pk}/", {"revision": track.revision, "profile": "person-a"}, format="json")
        self.send(packet())
        data = self.api.get("/api/v1/history/overview/").json()
        self.assertEqual((data["facts"]["sampled_frames"], data["facts"]["observed_tracks"]), (3, 2))
        self.assertEqual((data["profiles"][0]["confirmed_tracks"], data["profiles"][0]["candidate_tracks"]), (1, 1))

    def test_monitoring_routes_show_observations_and_preserve_legacy_photo_api(self):
        legacy = Post.objects.create(author=self.owner, title="프로젝트1 배경 테스트 사진",
                                     text="옛 블로그 자료", image=uploaded_photo())
        self.send(packet())
        self.client.force_login(self.owner)
        for path in ("/", "/detections/", "/history/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, legacy.title)
            self.assertNotContains(response, legacy.image.name)
            self.assertNotContains(response, 'class="post-grid')
        self.assertContains(self.client.get("/detections/"), 'id="history-grid"')
        self.assertEqual(self.api.get("/api/v1/history/frames/").json()["results"][0]["id"], TrackingFrame.objects.get().pk)
        self.assertEqual(self.api.get("/api/v1/history/overview/").json()["facts"]["detection_posts"], 0)
        self.assertContains(self.client.get("/photos/"), legacy.title)
        row = self.client.get("/api_root/Post/").json()[0]
        self.assertEqual(row["id"], legacy.pk)
        self.assertEqual(set(row), {"id", "author", "title", "text", "created_date", "published_date", "image"})
        self.assertTrue(Post.objects.filter(pk=legacy.pk).exists())

    def test_merged_records_and_dedicated_questions_have_three_distinct_tabs(self):
        self.send(packet())
        self.client.force_login(self.owner)
        for path, active in (("/", "관측 기록"), ("/detections/", "관측 기록"),
                             ("/history/", "관측 기록"), ("/questions/", "AI 질문"), ("/people/", "인물 확인")):
            html = self.client.get(path).content.decode()
            navigation = re.search(r'<div class="section-nav".*?</div>', html, re.S).group()
            self.assertEqual(re.findall(r'<a\b[^>]*>(.*?)</a>', navigation), ["관측 기록", "인물 확인", "AI 질문"])
            self.assertEqual(re.findall(r'<a\b[^>]*aria-current="page"[^>]*>(.*?)</a>', navigation), [active])
        self.assertContains(self.client.get("/detections/"), 'id="question-panel"')
        self.assertContains(self.client.get("/people/person-a/"), 'href="/questions/?profile=person-a&amp;include_candidates=true&amp;date_basis=processed"')

    def test_record_entry_points_share_summary_and_filterable_timeline(self):
        self.send(packet())
        self.client.force_login(self.owner)
        for path in ("/", "/detections/", "/history/"):
            response = self.client.get(path + "?profile=person-a&include_candidates=true")
            self.assertTemplateUsed(response, "blog/history.html")
            self.assertEqual(response.context["monitor"]["facts"]["sessions"], 1)
            self.assertContains(response, 'id="history-days"')
            self.assertContains(response, 'id="history-grid"')
            self.assertNotContains(response, 'class="review-queue"')
        response = self.client.get("/questions/?profile=person-a&include_candidates=true")
        self.assertNotContains(response, 'class="observation-summary"')
        self.assertTrue(response.context["history_config"]["question_page"])
