from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.test import TransactionTestCase, override_settings
from blog.models import Post
from blog.services import create_post, update_post
from .helpers import TemporaryMediaMixin, uploaded_photo

class PhotoCommitStorageTests(TemporaryMediaMixin, TransactionTestCase):
    """Exercise real outer commits, not TestCase's rollback-only wrapper."""
    def setUp(self):
        publisher=override_settings(BLOG_OWNER_USERNAME="commit-owner")
        publisher.enable()
        self.addCleanup(publisher.disable)
        super().setUp()
        self.owner = get_user_model().objects.create_user("commit-owner", password="commit-fixture-password-89")
        self.post = create_post(actor=self.owner, values={"title": "원본", "text": "원본 파일", "image": uploaded_photo()})

    def test_old_file_cleanup_error_keeps_committed_new_file_and_logs_failure(self):
        old_name, old_path = self.post.image.name, Path(self.post.image.path)
        storage = self.post.image.storage
        real_delete = storage.delete

        def failing_delete(name):
            if name == old_name:
                raise OSError("isolated old-file cleanup failure")
            real_delete(name)

        with patch.object(storage, "delete", side_effect=failing_delete):
            with self.assertLogs("django.db.backends", level="ERROR"):
                updated = update_post(actor=self.owner, post_id=self.post.pk, values={"image": uploaded_photo("new.png")})
        self.post.refresh_from_db()
        self.assertEqual(self.post.image.name, updated.image.name)
        self.assertNotEqual(self.post.image.name, old_name)
        self.assertTrue(Path(self.post.image.path).exists())
        self.assertTrue(old_path.exists())  # Failed garbage collection does not undo a commit.

    def test_unrelated_post_commit_exception_is_not_mistaken_for_rollback(self):
        def fail_after_commit(sender, instance, **kwargs):
            def fail():
                raise RuntimeError("isolated third-party commit callback")
            transaction.on_commit(fail)

        post_save.connect(fail_after_commit, sender=Post, dispatch_uid="test.commit_failure")
        try:
            with self.assertRaisesRegex(RuntimeError, "third-party"):
                update_post(actor=self.owner, post_id=self.post.pk, values={"image": uploaded_photo("new.png")})
        finally:
            post_save.disconnect(sender=Post, dispatch_uid="test.commit_failure")
        self.post.refresh_from_db()
        self.assertTrue(Path(self.post.image.path).exists())

    def test_direct_model_commit_exception_preserves_new_upload(self):
        def fail_after_commit(sender, instance, **kwargs):
            def fail():
                raise RuntimeError("isolated model commit callback")
            transaction.on_commit(fail)

        post_save.connect(fail_after_commit, sender=Post, dispatch_uid="test.direct_commit_failure")
        try:
            self.post.image = uploaded_photo("new.png")
            with self.assertRaisesRegex(RuntimeError, "model commit"):
                self.post.save()
        finally:
            post_save.disconnect(sender=Post, dispatch_uid="test.direct_commit_failure")
        self.post.refresh_from_db()
        self.assertTrue(Path(self.post.image.path).exists())


