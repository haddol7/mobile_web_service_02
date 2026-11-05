from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from blog.models import Post
from blog.validators import MAX_PHOTO_BYTES
from .helpers import TemporaryMediaMixin, photo_bytes, uploaded_photo


class BaselineIntegrationTests(TemporaryMediaMixin, TestCase):
    def setUp(self):
        from django.test import override_settings
        publisher = override_settings(BLOG_OWNER_USERNAME="baseline-owner")
        publisher.enable()
        self.addCleanup(publisher.disable)
        super().setUp()
        User = get_user_model()
        self.owner = User.objects.create_user("baseline-owner", password="integration-password-48")
        self.visitor = User.objects.create_user("baseline-visitor", password="integration-password-73")
        self.token = Token.objects.create(user=self.owner)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def post(self, **overrides):
        payload = {"title": "빛이 드는 사진", "text": "기본 이미지 게시글", "image": uploaded_photo()}
        payload.update(overrides)
        return self.api.post("/api_root/Post/", payload, format="multipart")

    def fixture_post(self):
        return Post.objects.create(author=self.owner, title="소유자 사진", text="원본 내용", image=uploaded_photo())

    def test_authenticated_multipart_saves_actual_image_bytes_and_row(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        post = Post.objects.get(pk=response.data["id"])
        self.assertEqual(post.author, self.owner)
        self.assertEqual(post.text, "기본 이미지 게시글")
        self.assertIsNotNone(post.published_date)
        self.assertEqual(Path(post.image.path).read_bytes(), photo_bytes())
        self.assertRegex(post.image.name, r"^images/\d{4}/\d{2}/\d{2}/[a-f0-9]{32}\.png$")

    def test_array_response_matches_lecture_android_jsonarray_contract(self):
        for index in range(12):
            Post.objects.create(author=self.owner, title=f"사진 {index}", text="내용", image=uploaded_photo())
        response = APIClient().get("/api_root/Post/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(len(response.json()), 12)
        self.assertEqual(set(response.json()[0]), {"id", "author", "title", "text", "created_date", "published_date", "image"})

    def test_public_api_and_web_can_read_image_post(self):
        post = self.fixture_post()
        self.assertEqual(str(post), post.title)
        api = APIClient().get(f"/api_root/Post/{post.pk}/")
        self.assertEqual(api.status_code, 200)
        listing = self.client.get(reverse("post_list"))
        self.assertContains(listing, post.title)
        self.assertContains(listing, post.image.url)

    def test_api_author_and_timestamps_cannot_be_spoofed(self):
        response = self.post(author=self.visitor.pk, created_date="1990-01-01T00:00:00Z", published_date="1990-01-01T00:00:00Z")
        self.assertEqual(response.status_code, 201)
        post = Post.objects.get(pk=response.data["id"])
        self.assertEqual(post.author, self.owner)
        self.assertGreater(post.created_date.year, 1990)
        self.assertGreater(post.published_date.year, 1990)

    def test_anonymous_cannot_create_update_or_delete(self):
        post = self.fixture_post()
        client = APIClient()
        self.assertEqual(client.post("/api_root/Post/", {"title": "침입"}, format="json").status_code, 401)
        self.assertEqual(client.patch(f"/api_root/Post/{post.pk}/", {"title": "침입"}, format="json").status_code, 401)
        self.assertEqual(client.delete(f"/api_root/Post/{post.pk}/").status_code, 401)

    def test_other_author_cannot_update_or_delete(self):
        post = self.fixture_post()
        client = APIClient()
        client.force_authenticate(self.visitor)
        self.assertEqual(client.patch(f"/api_root/Post/{post.pk}/", {"title": "침입"}, format="json").status_code, 403)
        self.assertEqual(client.delete(f"/api_root/Post/{post.pk}/").status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.title, "소유자 사진")
        self.assertEqual(post.author, self.owner)

    def test_owner_can_patch_without_changing_author_or_created_date(self):
        post = self.fixture_post()
        created = post.created_date
        response = self.api.patch(f"/api_root/Post/{post.pk}/", {"title": "수정", "author": self.visitor.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.title, "수정")
        self.assertEqual(post.author, self.owner)
        self.assertEqual(post.created_date, created)

    def test_owner_delete_releases_actual_media_after_commit(self):
        post = self.fixture_post()
        old_path = Path(post.image.path)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api.delete(f"/api_root/Post/{post.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())
        self.assertFalse(old_path.exists())

    def test_image_replacement_releases_only_old_media(self):
        post = self.fixture_post()
        old_path = Path(post.image.path)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.api.patch(f"/api_root/Post/{post.pk}/", {"image": uploaded_photo("replacement.png", size=(24, 16))}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        post.refresh_from_db()
        self.assertFalse(old_path.exists())
        self.assertTrue(Path(post.image.path).exists())

    def test_required_image_is_not_a_missing_default_path(self):
        response = self.api.post("/api_root/Post/", {"title": "사진 없음", "text": "내용"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)
        self.assertEqual(Post.objects.count(), 0)

    def test_corrupt_image_and_extension_mismatch_rejected_without_writing(self):
        invalid = SimpleUploadedFile("broken.png", b"not a PNG", content_type="image/png")
        self.assertEqual(self.post(image=invalid).status_code, 400)
        self.assertEqual(self.post(image=uploaded_photo("spoof.jpg")).status_code, 400)
        self.assertEqual(Post.objects.count(), 0)
        self.assertEqual(list(Path(self.media_root).rglob("*")), [])

    def test_valid_image_over_five_mib_rejected(self):
        too_large = photo_bytes() + b"\0" * MAX_PHOTO_BYTES
        image = SimpleUploadedFile("large.png", too_large, content_type="image/png")
        response = self.post(image=image)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Post.objects.count(), 0)

    def test_blank_title_and_text_are_rejected(self):
        response = self.post(title="   ", text="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.data)
        self.assertIn("text", response.data)

    def test_future_post_not_exposed_on_api_or_web(self):
        post = self.fixture_post()
        post.published_date = timezone.now() + timedelta(days=1)
        post.save(update_fields=["published_date"])
        self.assertEqual(APIClient().get("/api_root/Post/").json(), [])
        self.assertEqual(APIClient().get(f"/api_root/Post/{post.pk}/").status_code, 404)
        self.assertEqual(self.client.get(reverse("post_detail", args=[post.pk])).status_code, 404)

    def test_existing_web_image_upload_and_display_flow(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("post_new"), {"title": "웹 사진", "text": "웹에서 올린 사진", "image": uploaded_photo("web.png")})
        post = Post.objects.get(title="웹 사진")
        self.assertRedirects(response, reverse("post_detail", args=[post.pk]))
        detail = self.client.get(reverse("post_detail", args=[post.pk]))
        self.assertContains(detail, post.image.url)
        self.assertContains(detail, "웹에서 올린 사진")

    def test_web_truncated_jpeg_is_rejected_without_db_or_media_write(self):
        self.client.force_login(self.owner)
        image = SimpleUploadedFile(
            "truncated.jpg", photo_bytes(image_format="JPEG")[:-10], content_type="image/jpeg"
        )
        response = self.client.post(reverse("post_new"), {
            "title": "잘린 사진", "text": "저장 거부 확인", "image": image,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("image", response.context["form"].errors)
        self.assertEqual(Post.objects.count(), 0)
        self.assertEqual(list(Path(self.media_root).rglob("*")), [])

    def test_web_non_owner_edit_get_post_and_delete_forbidden(self):
        post = self.fixture_post()
        self.client.force_login(self.visitor)
        self.assertEqual(self.client.get(reverse("post_edit", args=[post.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("post_edit", args=[post.pk]), {"title": "침입", "text": "침입"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("post_delete", args=[post.pk])).status_code, 403)
        detail = self.client.get(reverse("post_detail", args=[post.pk]))
        self.assertNotContains(detail, reverse("post_edit", args=[post.pk]))
        post.refresh_from_db()
        self.assertEqual(post.author, self.owner)

    def test_web_owner_edit_preserves_author_and_can_delete(self):
        post = self.fixture_post()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("post_edit", args=[post.pk])).status_code, 200)
        response = self.client.post(reverse("post_edit", args=[post.pk]), {"title": "웹 수정", "text": "원본 사진 유지"})
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.author, self.owner)
        self.assertEqual(post.title, "웹 수정")
        self.assertEqual(self.client.get(reverse("post_delete", args=[post.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("post_delete", args=[post.pk])).status_code, 302)

    def test_empty_web_post_is_bound_and_shows_required_field_errors(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("post_new"), {})
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.assertIn("image", response.context["form"].errors)
        self.assertEqual(Post.objects.count(), 0)

    def test_login_redirect_is_real_and_login_logout_work(self):
        response = self.client.get(reverse("post_new"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")
        logged_in = self.client.post(reverse("login"), {"username": self.owner.username, "password": "integration-password-48"})
        self.assertEqual(logged_in.status_code, 302)
        self.assertEqual(self.client.get(reverse("post_new")).status_code, 200)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 302)
        self.assertEqual(self.client.get(reverse("post_new")).status_code, 302)

    def test_token_endpoint_accepts_valid_credentials_rejects_invalid(self):
        valid = self.client.post(reverse("api_token_auth"), {"username": self.owner.username, "password": "integration-password-48"})
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["token"], self.token.key)
        invalid = self.client.post(reverse("api_token_auth"), {"username": self.owner.username, "password": "wrong"})
        self.assertEqual(invalid.status_code, 400)

    def test_session_authenticated_api_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post("/api_root/Post/", {"title": "no CSRF", "text": "내용", "image": uploaded_photo()}, format="multipart")
        self.assertEqual(response.status_code, 403)

    def test_web_form_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post(reverse("post_new"), {"title": "no CSRF", "text": "내용", "image": uploaded_photo()})
        self.assertEqual(response.status_code, 403)

    def test_api_root_options_head_and_js_validation_view(self):
        root = self.client.get("/api_root/")
        self.assertEqual(root.status_code, 200)
        self.assertIn("Post", root.json())
        options = self.api.options("/api_root/Post/")
        self.assertEqual(options.status_code, 200)
        self.assertIn("POST", options["Allow"])
        self.assertEqual(self.api.head("/api_root/Post/").status_code, 200)
        self.assertContains(self.client.get(reverse("js_test")), "JSON 응답 새로고침")

