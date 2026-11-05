from django.contrib.auth import get_user_model
from django.test import TestCase
from blog.services import create_post
from .helpers import TemporaryMediaMixin, uploaded_photo
from .test_photo_content import packet


class ContentWebTests(TemporaryMediaMixin, TestCase):
    def setUp(self):
        from django.test import override_settings
        publisher = override_settings(BLOG_OWNER_USERNAME="web-content")
        publisher.enable()
        self.addCleanup(publisher.disable)
        super().setUp()
        owner=get_user_model().objects.create_user("web-content")
        self.post=create_post(actor=owner,values={"title":"사진 기록","text":"설명","image":uploaded_photo(),"photo_content":packet(text="바다 라멘")})

    def test_web_search_uses_photo_text_and_combines_filters(self):
        self.assertContains(self.client.get("/",{"q":"바다라멘","theme":"food"}),"사진 기록")
        self.assertNotContains(self.client.get("/",{"q":"바다라멘","theme":"animal"}),"사진 기록")

    def test_invalid_query_and_metadata_display_are_escaped(self):
        response=self.client.get("/",{"q":"가"})
        self.assertContains(response,"검색어는 2–80문자")
        self.assertNotContains(response,"사진 기록")
        detail=self.client.get(f"/post/{self.post.pk}/")
        self.assertEqual(detail.context['photo_content']['lines'][0]['text'],"바다 라멘")
        self.assertNotContains(detail,'id="all-locations"')
        self.assertNotContains(detail,'id="plain-photo-lines"')

    def test_primary_web_navigation_is_photo_based(self):
        response=self.client.get("/")
        self.assertContains(response,"사진 블로그")
        self.assertNotContains(response,"사진관 마을")
