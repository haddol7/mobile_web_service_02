"""Actual HTTP transport, multipart and search evidence for E03/E05."""
import json
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase

from api_test_engine import PhotoBlogHTTPClient, multipart_body
from blog.models import Post
from .helpers import TemporaryMediaMixin, photo_bytes
from .test_photo_content import packet


class ContentRealHTTPTests(TemporaryMediaMixin, LiveServerTestCase):
    def setUp(self):
        from django.test import override_settings
        publisher = override_settings(BLOG_OWNER_USERNAME="content-http")
        publisher.enable()
        self.addCleanup(publisher.disable)
        super().setUp()
        self.owner=get_user_model().objects.create_user("content-http",password="http-content-fixture-91")
        self.http=PhotoBlogHTTPClient(self.live_server_url)
        self.assertEqual(self.http.authenticate(self.owner.username,"http-content-fixture-91").status,200)

    def upload(self,data):
        body,kind=multipart_body({"title":"음식 후기","text":"본문에 가게 이름 없음","photo_content":json.dumps(data)},
                                 {"image":("photo.png","image/png",photo_bytes())})
        return self.http.request("POST","/api_root/Post/",body,kind)

    def test_actual_upload_public_file_search_correction_and_exclusion(self):
        result=self.upload(packet(text="바다라멘"))
        self.assertEqual(result.status,201,result.body)
        post_id=result.json()["id"]
        self.assertEqual(len(result.json()),7)
        image=self.http.request("GET",result.json()["image"].removeprefix(self.live_server_url),authenticated=False)
        self.assertEqual(image.body,photo_bytes())
        url="/api/v1/photo-text-search/?"+urlencode({"q":"바다라멘"})
        found=self.http.request("GET",url,authenticated=False)
        self.assertEqual(found.status,200,found.body)
        self.assertEqual(found.json()["results"][0]["post"]["id"],post_id)
        correction=packet(text="새가게",revision=1)
        detail=f"/api/v1/posts/{post_id}/content/"
        saved=self.http.request("PATCH",detail,json.dumps(correction).encode(),"application/json")
        self.assertEqual(saved.status,200,saved.body)
        self.assertEqual(self.http.request("GET",url).json()["results"],[])
        correction.update(expected_revision=2,lines=[])
        self.assertEqual(self.http.request("PATCH",detail,json.dumps(correction).encode(),"application/json").status,200)
        self.assertEqual(self.http.request("GET","/api/v1/photo-text-search/?"+urlencode({"q":"새가게"})).json()["results"],[])

    def test_actual_mismatched_image_is_not_saved(self):
        data=packet(); data["image_sha256"]="0"*64
        result=self.upload(data)
        self.assertEqual(result.status,400,result.body)
        self.assertEqual(result.json()["code"],"image_mismatch")
        self.assertEqual(Post.objects.count(),0)

    def test_actual_stale_write_returns_409_and_legacy_array_remains(self):
        created=self.upload(packet()).json()
        result=self.http.request("PATCH",f'/api/v1/posts/{created["id"]}/content/',json.dumps(packet(revision=0)).encode(),"application/json")
        self.assertEqual(result.status,409,result.body)
        self.assertEqual(result.json()["current_revision"],1)
        listing=self.http.request("GET","/api_root/Post/").json()
        self.assertIsInstance(listing,list)
        self.assertEqual(listing[0]["id"],created["id"])
