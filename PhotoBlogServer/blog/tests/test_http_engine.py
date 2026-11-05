from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase

from api_test_engine import PhotoBlogHTTPClient, multipart_body
from blog.models import Post
from .helpers import TemporaryMediaMixin, photo_bytes


class RealHTTPAPIEngineTests(TemporaryMediaMixin, LiveServerTestCase):
    """Exercise real HTTP parsing, ORM writes and stored image bytes together."""
    def setUp(self):
        from django.test import override_settings
        publisher = override_settings(BLOG_OWNER_USERNAME="http-owner")
        publisher.enable()
        self.addCleanup(publisher.disable)
        super().setUp()
        User = get_user_model()
        self.owner = User.objects.create_user("http-owner", password="isolated-http-fixture-49")
        self.other = User.objects.create_user("http-other", password="isolated-http-fixture-63")
        self.http = PhotoBlogHTTPClient(self.live_server_url)
        self.assertEqual(self.http.authenticate(self.owner.username, "isolated-http-fixture-49").status, 200)

    def test_real_multipart_request_persists_row_and_serves_identical_photo(self):
        image = photo_bytes()
        result = self.http.post_photo("HTTP 엔진 사진", "실제 소켓·HTTP·DB·이미지 저장 검증", image)
        self.assertEqual(result.status, 201)
        data = result.json()
        post = Post.objects.get(pk=data["id"])
        self.assertEqual(post.author_id, self.owner.pk)
        self.assertEqual(Path(post.image.path).read_bytes(), image)
        # Use the relative media URL so the request goes to this isolated live server.
        photo = self.http.request("GET", post.image.url)
        self.assertEqual(photo.status, 200)
        self.assertEqual(photo.body, image)
        listing = self.http.request("GET", "/api_root/Post/")
        self.assertEqual(listing.status, 200)
        self.assertIsInstance(listing.json(), list)
        self.assertEqual(listing.json()[0]["id"], post.pk)

    def test_real_head_and_options_contract(self):
        head = self.http.request("HEAD", "/api_root/Post/")
        self.assertEqual(head.status, 200)
        self.assertEqual(head.body, b"")
        options = self.http.request("OPTIONS", "/api_root/Post/")
        self.assertEqual(options.status, 200)
        self.assertIn("POST", options.headers["Allow"])
        self.assertIn("actions", options.json())

    def test_real_anonymous_request_is_rejected_without_persisting(self):
        unauthenticated = PhotoBlogHTTPClient(self.live_server_url)
        result = unauthenticated.post_photo("anonymous", "not allowed", photo_bytes())
        self.assertEqual(result.status, 401)
        self.assertEqual(Post.objects.count(), 0)

    def test_real_invalid_credentials_do_not_produce_token(self):
        wrong = PhotoBlogHTTPClient(self.live_server_url)
        result = wrong.authenticate(self.owner.username, "wrong")
        self.assertEqual(result.status, 400)
        self.assertIsNone(wrong.token)

    def test_real_malformed_authorization_header_is_rejected(self):
        self.http.token = "invalid token with extra parts"
        result = self.http.request("GET", "/api_root/Post/")
        self.assertEqual(result.status, 401)
        self.assertIn("detail", result.json())

    def test_real_owner_boundary_update_delete_and_media_cleanup(self):
        created = self.http.post_photo("owner-only", "original", photo_bytes())
        self.assertEqual(created.status, 201)
        pk = created.json()["id"]
        post = Post.objects.get(pk=pk)
        image_path = Path(post.image.path)
        other = PhotoBlogHTTPClient(self.live_server_url)
        self.assertEqual(other.authenticate(self.other.username, "isolated-http-fixture-63").status, 200)
        body = b'{"title":"unauthorized"}'
        self.assertEqual(other.request("PATCH", f"/api_root/Post/{pk}/", body, "application/json").status, 403)
        self.assertEqual(other.request("DELETE", f"/api_root/Post/{pk}/").status, 403)
        updated = self.http.request("PATCH", f"/api_root/Post/{pk}/", b'{"title":"owner changed"}', "application/json")
        self.assertEqual(updated.status, 200)
        deleted = self.http.request("DELETE", f"/api_root/Post/{pk}/")
        self.assertEqual(deleted.status, 204)
        self.assertFalse(Post.objects.filter(pk=pk).exists())
        self.assertFalse(image_path.exists())

    def test_real_invalid_multipart_image_is_rejected(self):
        result = self.http.post_photo("bad-image", "invalid bytes", b"not an image")
        self.assertEqual(result.status, 400)
        self.assertIn("image", result.json())
        self.assertEqual(Post.objects.count(), 0)

    def test_real_truncated_jpeg_multipart_is_rejected_without_db_or_media_write(self):
        truncated = photo_bytes(image_format="JPEG")[:-10]
        result = self.http.post_photo(
            "truncated-jpeg", "잘린 JPEG는 저장하면 안 됩니다.", truncated,
            filename="truncated.jpg", content_type="image/jpeg",
        )
        self.assertEqual(result.status, 400)
        self.assertIn("image", result.json())
        self.assertEqual(Post.objects.count(), 0)
        self.assertEqual(list(Path(self.media_root).rglob("*")), [])

    def test_real_malformed_multipart_without_boundary_is_rejected(self):
        result = self.http.request("POST", "/api_root/Post/", b"bad multipart", "multipart/form-data")
        self.assertEqual(result.status, 400)
        self.assertEqual(Post.objects.count(), 0)

    def test_real_binary_multipart_builder_preserves_image_bytes(self):
        image = photo_bytes() + b"\0\xff\r\n"
        body, content_type = multipart_body({"title": "한글"}, {"image": ("photo.png", "image/png", image)})
        self.assertIn(image, body)
        self.assertIn("한글".encode(), body)
        self.assertIn("boundary=photoblog-", content_type)
