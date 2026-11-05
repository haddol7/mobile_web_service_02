"""Public reading and a single publisher across web, token and session APIs."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from blog.models import Post
from blog.services import create_post, update_post, delete_post
from blog.content_services import update_content
from django.core.exceptions import PermissionDenied
from .helpers import TemporaryMediaMixin, uploaded_photo
from .test_photo_content import packet


@override_settings(BLOG_OWNER_USERNAME='publisher')
class SingleOwnerTests(TemporaryMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.owner=get_user_model().objects.create_user('publisher',password='publisher-test-48')
        self.other=get_user_model().objects.create_superuser('other-admin',password='other-test-58')
        self.post=create_post(actor=self.owner,values={'title':'기존 사진','text':'보존할 내용','image':uploaded_photo(),'photo_content':packet()})

    def test_registration_and_all_old_studio_endpoints_are_gone(self):
        count=get_user_model().objects.count()
        for path in ['/accounts/signup/','/api/v1/auth/register/','/village/','/studio/me/','/studio/1/',
                     '/api/v1/galleries/','/api/v1/galleries/1/','/api/v1/galleries/1/layout/','/api/v1/catalog/']:
            for method in ['get','post']:
                self.assertEqual(getattr(self.client,method)(path).status_code,404,path)
        self.assertEqual(get_user_model().objects.count(),count)
        self.assertFalse(hasattr(self.owner,'gallery'))

    def test_navigation_login_and_session_have_no_studio_or_signup(self):
        for path in ['/','/accounts/login/']:
            response=self.client.get(path)
            self.assertNotContains(response,'회원가입')
            self.assertNotContains(response,'/studio/')
            self.assertNotContains(response,'사진관')
        self.client.force_login(self.owner)
        me=self.client.get('/api/v1/auth/me/').json()
        self.assertTrue(me['can_publish'])
        self.assertNotIn('gallery_id',me)
        self.assertContains(self.client.get('/'),'사진 게시')
        self.client.force_login(self.other)
        self.assertFalse(self.client.get('/api/v1/auth/me/').json()['can_publish'])
        self.assertNotContains(self.client.get('/'),'href="/post/new/"')

    def test_existing_nonowner_even_superuser_cannot_create_edit_delete_or_correct(self):
        self.client.force_login(self.other)
        for path in ['/post/new/',f'/post/{self.post.pk}/edit/']:
            self.assertEqual(self.client.get(path).status_code,403)
        self.assertEqual(self.client.post(f'/post/{self.post.pk}/delete/').status_code,403)
        api=APIClient()
        token=Token.objects.create(user=self.other)
        api.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(api.post('/api_root/Post/',{'title':'금지','text':'금지','image':uploaded_photo()},format='multipart').status_code,403)
        self.assertEqual(api.patch(f'/api_root/Post/{self.post.pk}/',{'title':'금지'},format='json').status_code,403)
        self.assertEqual(api.delete(f'/api_root/Post/{self.post.pk}/').status_code,403)
        self.assertEqual(api.patch(f'/api/v1/posts/{self.post.pk}/content/',packet(revision=1),format='json').status_code,403)
        for action in [lambda:create_post(actor=self.other,values={}),
                       lambda:update_post(actor=self.other,post_id=self.post.pk,values={}),
                       lambda:delete_post(actor=self.other,post_id=self.post.pk),
                       lambda:update_content(actor=self.other,post_id=self.post.pk,packet=packet(revision=1))]:
            with self.assertRaises(PermissionDenied):action()
        self.post.refresh_from_db()
        self.assertEqual(self.post.title,'기존 사진')
        self.assertEqual(Post.objects.count(),1)

    def test_public_reading_and_required_seven_field_array_remain(self):
        result=self.client.get('/api_root/Post/').json()
        self.assertEqual(set(result[0]),{'id','author','title','text','created_date','published_date','image'})
        self.assertContains(self.client.get('/'),'기존 사진')
        self.assertEqual(self.client.get(f'/post/{self.post.pk}/').status_code,200)
        self.assertEqual(self.client.get(f'/api/v1/posts/{self.post.pk}/content/').status_code,200)

    def test_unknown_or_inactive_publisher_fails_closed(self):
        with override_settings(BLOG_OWNER_USERNAME='missing'):
            with self.assertRaises(PermissionDenied):create_post(actor=self.owner,values={})
        self.owner.is_active=False
        with self.assertRaises(PermissionDenied):create_post(actor=self.owner,values={})

    def test_retired_admin_has_no_special_publishing_permission(self):
        admin=get_user_model().objects.create_user('admin',password='isolated-admin-fixture')
        self.client.force_login(admin)
        self.assertEqual(self.client.get(f'/post/{self.post.pk}/edit/').status_code,403)
        admin.is_staff=admin.is_superuser=True
        admin.save()
        self.assertEqual(self.client.get(f'/post/{self.post.pk}/edit/').status_code,403)
        self.assertFalse(self.client.get('/api/v1/auth/me/').json()['can_manage_all'])
        with self.assertRaises(PermissionDenied):
            update_post(actor=admin,post_id=self.post.pk,values={'title':'관리자 수정'})
        self.post.refresh_from_db()
        self.assertEqual(self.post.author_id,self.owner.pk)
        self.assertEqual(self.post.title,'기존 사진')
