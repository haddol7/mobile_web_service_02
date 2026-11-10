from io import BytesIO
import json
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from blog.history_annotations import render_overlay, scaled_box
from blog.models import TrackingFrame, PersonTrack
from .test_history import packet


@override_settings(BLOG_OWNER_USERNAME="publisher")
class HistoryAnnotationTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = override_settings(HISTORY_MEDIA_ROOT=directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = get_user_model().objects.create_user("publisher")
        self.other = get_user_model().objects.create_user("other")
        self.api = APIClient()
        self.api.force_authenticate(self.owner)
        data = packet()
        data["frame"].update(image_size=[800, 600], tracks=[{"track_id": 1, "bbox": [80, 120, 600, 560]}])
        data["frame"]["faces"][0]["bbox"] = [240, 240, 400, 400]
        photo = BytesIO()
        Image.new("RGB", (400, 300), "#ffffff").save(photo, "JPEG")
        response = self.api.post("/api/v1/history/ingest/", {
            "packet": json.dumps(data), "image": SimpleUploadedFile("frame.jpg", photo.getvalue(), content_type="image/jpeg")}, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.frame = TrackingFrame.objects.get(pk=response.json()["id"])
        self.url = f"/api/v1/history/images/{self.frame.pk}/"

    def rendered(self):
        observations = list(self.frame.observations.select_related("track__confirmed", "candidate"))
        return render_overlay(Image.new("RGB", (400, 300), "white"), self.frame.image_size, observations, [])

    def test_coordinates_follow_resized_photo_and_are_clipped(self):
        image, count = self.rendered()
        self.assertEqual(count, 2)
        self.assertEqual(image.getpixel((40, 200)), (56, 189, 248))
        self.assertEqual(image.getpixel((120, 180)), (251, 191, 36))
        self.assertEqual(image.getpixel((350, 250)), (255, 255, 255))
        self.assertEqual(scaled_box([-10, 20, 900, 700], [800, 600], (400, 300)), (0, 10, 399, 299))
        for box, size in (([1, 2, 3, 4], []), ([0, 0, 10, 10], [0, 20]),
                          ([500, 0, 600, 30], [400, 300]), ([0, 0, float("nan"), 1], [400, 300])):
            self.assertIsNone(scaled_box(box, size, (400, 300)))

    def test_confirmed_and_rejected_tracks_have_distinct_face_colors(self):
        track = PersonTrack.objects.get()
        track.confirmed_id = "person-a"
        track.save(update_fields=["confirmed"])
        self.assertEqual(self.rendered()[0].getpixel((120, 180)), (52, 211, 153))
        from django.utils import timezone
        track.confirmed = None
        track.reviewed_at = timezone.now()
        track.save(update_fields=["confirmed", "reviewed_at"])
        self.assertEqual(self.rendered()[0].getpixel((120, 180)), (203, 213, 225))

    def test_image_endpoint_is_public_and_does_not_overwrite_original(self):
        before = self.frame.image.read()
        self.frame.image.close()
        annotated = self.api.get(self.url + "?boxes=1")
        self.assertEqual(annotated.status_code, 200)
        self.assertEqual(annotated["X-Detection-Boxes"], "2")
        self.assertEqual(annotated["Cache-Control"], "private, no-store")
        self.assertNotEqual(annotated.content, before)
        raw = self.api.get(self.url)
        self.assertEqual(b"".join(raw.streaming_content), before)
        self.assertEqual(APIClient().get(self.url + "?boxes=1").status_code, 200)
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(self.url + "?boxes=1").status_code, 200)

    def test_display_urls_have_boxes_but_registration_and_face_crops_do_not(self):
        row = self.api.get("/api/v1/history/sessions/?date_basis=processed").json()["results"][0]
        self.assertTrue(row["image_url"].endswith("?boxes=1"))
        self.assertNotIn("boxes", row["tracks"][0]["face_url"])
        crop = self.api.get(row["tracks"][0]["face_url"])
        self.assertNotIn("X-Detection-Overlay", crop)

    def test_missing_geometry_never_invents_boxes_or_identity_for_unlinked_faces(self):
        observations = list(self.frame.observations.select_related("track__confirmed", "candidate"))
        image, count = render_overlay(Image.new("RGB", (400, 300), "white"), [], observations, [])
        self.assertEqual(count, 0)
        self.assertEqual(image.getpixel((40, 200)), (255, 255, 255))
        image, count = render_overlay(Image.new("RGB", (400, 300), "white"), [400, 300], [],
                                      [{"bbox": [100, 100, 200, 200], "candidate_profile_id": "person-a"}])
        self.assertEqual(count, 1)
        self.assertEqual(image.getpixel((100, 170)), (203, 213, 225))
