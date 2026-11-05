import json
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings
from api_test_engine import PhotoBlogHTTPClient
from .helpers import TemporaryMediaMixin, photo_bytes


@override_settings(BLOG_OWNER_USERNAME='http-publisher')
class SingleOwnerHTTPTests(TemporaryMediaMixin, LiveServerTestCase):
    def setUp(self):
        super().setUp()
        User=get_user_model()
        self.owner=User.objects.create_user('http-publisher',password='http-owner-fixture-82')
        self.reader=User.objects.create_user('old-reader',password='http-reader-fixture-93')

    def test_actual_owner_upload_reader_denial_and_public_seven_field_sync(self):
        owner=PhotoBlogHTTPClient(self.live_server_url)
        self.assertEqual(owner.authenticate(self.owner.username,'http-owner-fixture-82').status,200)
        created=owner.post_photo('1인 운영','운영자 사진',photo_bytes())
        self.assertEqual(created.status,201)
        reader=PhotoBlogHTTPClient(self.live_server_url)
        self.assertEqual(reader.authenticate(self.reader.username,'http-reader-fixture-93').status,200)
        self.assertEqual(reader.post_photo('금지','금지',photo_bytes()).status,403)
        path=f'/api_root/Post/{created.json()["id"]}/'
        self.assertEqual(reader.request('PATCH',path,json.dumps({'title':'금지'}).encode(),'application/json').status,403)
        self.assertEqual(reader.request('DELETE',path).status,403)
        public=PhotoBlogHTTPClient(self.live_server_url)
        posts=public.request('GET','/api_root/Post/').json()
        self.assertEqual(len(posts),1)
        self.assertEqual(set(posts[0]),{'id','author','title','text','created_date','published_date','image'})
        self.assertEqual(public.request('GET',created.json()['image'].removeprefix(self.live_server_url)).body,photo_bytes())

    def test_actual_retired_routes_and_session_capability(self):
        public=PhotoBlogHTTPClient(self.live_server_url)
        for path in ['/accounts/signup/','/api/v1/auth/register/','/village/','/studio/me/','/api/v1/galleries/','/api/v1/catalog/']:
            self.assertEqual(public.request('GET',path).status,404)
        self.assertFalse(public.request('GET','/api/v1/auth/me/').json()['can_publish'])
