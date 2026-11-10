from copy import deepcopy
from io import BytesIO
import json
import tempfile
from django.contrib.auth import get_user_model
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from PIL import Image
from blog.models import TrackingFrame,PersonTrack,PersonProfile
from .test_history import packet
from .helpers import uploaded_photo


@override_settings(BLOG_OWNER_USERNAME="publisher")
class PersonExperienceTests(TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        setting=override_settings(HISTORY_MEDIA_ROOT=directory.name);setting.enable();self.addCleanup(setting.disable)
        self.owner=get_user_model().objects.create_user("publisher");self.other=get_user_model().objects.create_user("other")
        self.api=APIClient();self.api.force_authenticate(self.owner)

    def send(self,source="source-a",purpose="demo"):
        data=packet();data["session"].update(purpose=purpose,source_reference=source)
        data["frame"]["image_size"]=[100,100]
        response=self.api.post("/api/v1/history/ingest/",{"packet":json.dumps(data),"image":uploaded_photo()},format="multipart")
        self.assertEqual(response.status_code,201);return response.json()["id"]

    def test_reference_portrait_is_public_but_changes_remain_owner_only(self):
        self.send();url="/api/v1/history/references/person-a/"
        self.assertEqual(self.api.post(url,{"image":uploaded_photo()},format="multipart").status_code,200)
        reference=PersonProfile.objects.get().reference_image.name
        image=self.api.get(url);self.assertEqual(image.status_code,200)
        with Image.open(BytesIO(b"".join(image.streaming_content))) as decoded:self.assertEqual(decoded.format,"JPEG")
        self.assertEqual(APIClient().get(url).status_code,200)
        self.api.force_authenticate(self.other);self.assertEqual(self.api.get(url).status_code,200)
        self.assertEqual(self.api.post(url,{"image":uploaded_photo()},format="multipart").status_code,403)
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.post(url,{"image":"not an image"}).status_code,400)
        self.assertEqual(PersonProfile.objects.get().reference_image.name,reference)

    def test_profile_shows_candidates_before_confirmation_and_two_distinct_sources(self):
        self.send("source-a");self.send("source-b")
        data=self.api.get("/api/v1/history/people/person-a/").json()
        self.assertEqual((data["confirmed_tracks"],data["candidate_tracks"],data["source_count"]),(0,2,2))
        self.assertEqual(len(data["timeline"]),2);self.assertEqual(len(data["pending"]),2)
        self.assertTrue(data["portrait_url"])
        self.client.force_login(self.owner)
        html=self.client.get("/people/person-a/")
        self.assertContains(html,"같은 인물로 확인");self.assertContains(html,"영상별 발견 이력")
        self.assertContains(html,"이번 영상에서 발견된 얼굴")

    def test_dataset_review_is_restricted_and_distinguished_from_operator_review(self):
        self.send(purpose="recording");track=PersonTrack.objects.first()
        url=f"/api/v1/history/tracks/{track.pk}/"
        self.assertEqual(self.api.patch(url,{"revision":1,"profile":"person-a","basis":"dataset"},format="json").status_code,400)
        self.send();track=PersonTrack.objects.order_by("-pk").first();url=f"/api/v1/history/tracks/{track.pk}/"
        response=self.api.patch(url,{"revision":1,"profile":"person-a","basis":"dataset"},format="json")
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()["review_basis"],"dataset")
        self.assertEqual(self.api.patch(url,{"revision":1,"profile":None},format="json").status_code,409)

    def test_analysis_date_filter_does_not_turn_unknown_capture_date_into_recorded_date(self):
        self.send();url="/api/v1/history/frames/?start=2026-11-08&end=2026-11-08"
        self.assertEqual(self.api.get(url).json()["results"],[])
        rows=self.api.get(url+"&date_basis=processed").json()["results"]
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]["observed_at"])
        self.assertEqual(rows[0]["time_basis"],"unknown_recording_date")
        self.assertEqual(self.api.get("/api/v1/history/frames/?date_basis=madeup").status_code,400)

    def test_question_retrieves_diverse_sources_and_deduplicates_reruns(self):
        self.send("same-source");self.send("same-source");self.send("other-source")
        response=self.api.post("/api/v1/history/ask/",{"question":"어떤 영상에서 발견됐어?","profile":"person-a","include_candidates":True,"date_basis":"processed"},format="json")
        self.assertEqual(response.status_code,200);data=response.json()
        self.assertEqual(data["facts"]["source_count"],2)
        self.assertEqual(data["facts"]["dates"],["2026-11-08"])
        self.assertIn("분석 날짜",data["answer"])
        self.assertTrue(all(e["observed_at"] is None for e in data["evidence"]))
        self.assertEqual(len({e["session_id"] for e in data["evidence"]}),3)

    def test_sessions_do_not_repeat_continuous_frames_as_separate_videos(self):
        self.send();first=TrackingFrame.objects.first()
        data=packet(session=first.session_id.hex,index=2)
        data["session"].update(purpose="demo",source_reference="source-a")
        self.assertEqual(self.api.post("/api/v1/history/ingest/",data,format="json").status_code,201)
        rows=self.api.get("/api/v1/history/sessions/").json()["results"]
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]["sample_count"],2);self.assertEqual(len(rows[0]["frames"]),2)
        self.assertEqual(self.api.get("/api/v1/history/sessions/?page=0").status_code,400)

    def test_face_crop_is_bound_to_an_observation_of_that_frame(self):
        key=self.send();track=PersonTrack.objects.first()
        response=self.api.get(f"/api/v1/history/images/{key}/?track={track.pk}")
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.api.get(f"/api/v1/history/images/{key}/?track=999999").status_code,404)
        self.assertEqual(self.api.get(f"/api/v1/history/images/{key}/?track=invalid").status_code,400)

from datetime import datetime,timezone
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from blog.models import TrackingFrame
from .test_history import packet


@override_settings(BLOG_OWNER_USERNAME="publisher",TIME_ZONE="Asia/Seoul")
class HistoryDateTests(TestCase):
    def setUp(self):
        self.api=APIClient();self.owner=get_user_model().objects.create_user("publisher")
        self.api.force_authenticate(self.owner)

    def send(self,session=None,index=1,processed="2026-11-08T14:59:59+00:00",started=None):
        data=packet(session=session,index=index,started=started)
        data["frame"]["processed_at_utc"]=processed
        response=self.api.post("/api/v1/history/ingest/",data,format="json")
        self.assertEqual(response.status_code,201)
        return data,response.json()["id"]

    def test_midnight_splits_one_session_without_dropping_or_duplicating_frames(self):
        session=uuid4().hex
        self.send(session,index=1);self.send(session,index=2,processed="2026-11-08T15:00:00+00:00")
        data=self.api.get("/api/v1/history/sessions/?date_basis=processed").json()
        self.assertEqual([r["date_key"] for r in data["results"]],["2026-11-09","2026-11-08"])
        self.assertEqual([r["sample_count"] for r in data["results"]],[1,1])
        self.assertEqual(len({f["id"] for r in data["results"] for f in r["frames"]}),2)
        self.assertTrue(all(f["observed_at"] is None for r in data["results"] for f in r["frames"]))

    def test_unknown_capture_day_is_a_separate_bucket_after_known_days(self):
        self.send();self.send(started="2024-01-01T10:00:00+09:00")
        data=self.api.get("/api/v1/history/sessions/?date_basis=recorded").json()
        self.assertEqual([r["date_key"] for r in data["results"]],["2024-01-01",None])
        self.assertEqual(data["results"][-1]["date_label"],"촬영 날짜 미상")
        self.assertEqual(sum(r["sample_count"] for r in data["days"]),2)

    def test_day_selection_keeps_other_days_available_and_applies_profile_scope(self):
        self.send();self.send(processed="2026-11-08T15:00:00+00:00")
        data=self.api.get("/api/v1/history/sessions/?date_basis=processed&start=2026-11-09&end=2026-11-09").json()
        self.assertEqual(len(data["results"]),1)
        self.assertEqual([d["date_key"] for d in data["days"]],["2026-11-09","2026-11-08"])
        empty=self.api.get("/api/v1/history/sessions/?date_basis=processed&profile=person-a").json()
        self.assertEqual(empty["results"],[]);self.assertEqual(empty["days"],[])

    def test_pagination_and_day_totals_use_all_matching_sessions(self):
        for _ in range(13):self.send()
        first=self.api.get("/api/v1/history/sessions/?date_basis=processed").json()
        second=self.api.get("/api/v1/history/sessions/?date_basis=processed&page=2").json()
        self.assertEqual((len(first["results"]),len(second["results"]),first["next_page"],second["next_page"]),(12,1,2,None))
        self.assertEqual(first["days"][0]["session_count"],13)
        self.assertEqual(len({r["id"] for r in first["results"]+second["results"]}),13)

    def test_profile_timeline_uses_the_same_local_date_groups(self):
        self.send();self.send(processed="2026-11-08T15:00:00+00:00")
        data=self.api.get("/api/v1/history/people/person-a/").json()
        self.assertEqual([r["date_key"] for r in data["timeline"]],["2026-11-09","2026-11-08"])
        self.assertEqual(len(data["days"]),2)
