import json
import re
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from blog.services import create_post
from .helpers import TemporaryMediaMixin, uploaded_photo
from .test_photo_content import packet


class MobileWebTests(TemporaryMediaMixin, TestCase):
    def setUp(self):
        from django.test import override_settings
        publisher = override_settings(BLOG_OWNER_USERNAME="mobile-web-owner")
        publisher.enable()
        self.addCleanup(publisher.disable)
        self.owner=get_user_model().objects.create_user('mobile-web-owner')
        self.post=create_post(actor=self.owner, values={'title':'후기','text':'제목과 본문에는 문구 없음','image':uploaded_photo(),'photo_content':packet(text='바다 라멘 CAFE 100%')})

    def config(self,response,name):
        match=re.search(rf'<script id="{name}" type="application/json">(.*?)</script>',response.content.decode(),re.S)
        self.assertIsNotNone(match)
        return json.loads(match[1])

    def test_mobile_composer_remains_login_protected(self):
        self.assertEqual(self.client.get('/post/new/').status_code,302)

    def test_owner_gets_self_hosted_tools_camera_and_basic_form(self):
        self.client.force_login(self.owner)
        response=self.client.get('/post/new/')
        for value in ['content/composer.mjs','content/content.css','capture="environment"','id="mosaic-stage"','id="ocr-lines"','name="csrfmiddlewaretoken"','name="image"']:
            self.assertContains(response,value)
        self.assertEqual(self.config(response,'composer-config'),{'post_id':None})
        self.assertNotContains(response,'cdn.jsdelivr.net')

    def test_edit_config_loads_existing_metadata_without_other_owner_access(self):
        self.client.force_login(self.owner)
        response=self.client.get(f'/post/{self.post.pk}/edit/')
        config=self.config(response,'composer-config')
        self.assertEqual(config['post_id'],self.post.pk)
        self.assertEqual(config['image'],self.post.image.url)
        other=get_user_model().objects.create_user('mobile-web-other')
        self.client.force_login(other)
        self.assertEqual(self.client.get(f'/post/{self.post.pk}/edit/').status_code,403)

    def test_search_context_reaches_detail_and_matching_original_line(self):
        response=self.client.get('/',{'q':'바다라멘 cafe'})
        self.assertContains(response,f'/post/{self.post.pk}/?q=')
        detail=self.client.get(f'/post/{self.post.pk}/',{'q':'바다라멘 CAFE'})
        config=self.config(detail,'detail-config')
        self.assertEqual(config['matched_ids'],[str(self.post.content.lines.get().line_id)])
        self.assertEqual(config['content']['revision'],1)
        self.assertContains(detail,'content/detail.mjs')

    def test_literal_percent_matches_and_invalid_query_does_not_highlight(self):
        self.assertTrue(self.config(self.client.get(f'/post/{self.post.pk}/',{'q':'100%'}),'detail-config')['matched_ids'])
        self.assertEqual(self.config(self.client.get(f'/post/{self.post.pk}/',{'q':'가'}),'detail-config')['matched_ids'],[])

    def test_ocr_and_query_cannot_break_json_script_or_inject_html(self):
        self.post.content.lines.update(text='</script><script>alert(1)</script>')
        response=self.client.get(f'/post/{self.post.pk}/',{'q':'</script>'})
        self.assertNotContains(response,'</script><script>alert(1)</script>')
        self.assertEqual(self.config(response,'detail-config')['content']['lines'][0]['text'],'</script><script>alert(1)</script>')

    @override_settings(DEBUG=False)
    def test_development_model_probe_is_unavailable_in_production(self):
        self.assertEqual(self.client.get('/dev/content-check/').status_code,404)

    @override_settings(DEBUG=True)
    def test_development_probe_runs_only_local_browser_models(self):
        self.assertContains(self.client.get('/dev/content-check/'),'실제 인식 검사 시작')

    def test_javascript_disabled_basic_post_and_edit_still_work(self):
        self.client.force_login(self.owner)
        response=self.client.post('/post/new/',{'title':'기본 작성','text':'기본 폼 유지','image':uploaded_photo()})
        self.assertEqual(response.status_code,302)
        original_name=self.post.image.name
        response=self.client.post(f'/post/{self.post.pk}/edit/',{'title':'제목 수정','text':'본문 수정'})
        self.assertEqual(response.status_code,302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.image.name,original_name)
        self.assertEqual(self.post.content.lines.get().text,'바다 라멘 CAFE 100%')
