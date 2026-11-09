import os
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings


class ProductionConfigurationUnitTests(SimpleTestCase):
    def load_settings(self, **environment):
        test_env = {"DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": "test-configuration-key-that-is-not-a-production-credential", **environment}
        with patch.dict(os.environ, test_env):
            return runpy.run_path(str(Path(settings.BASE_DIR) / "photoblog" / "settings.py"))

    def test_production_requires_environment_secret(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            self.load_settings(DJANGO_SECRET_KEY="")

    def test_production_secure_cookies_and_redirect_enabled(self):
        config = self.load_settings()
        self.assertFalse(config["DEBUG"])
        self.assertTrue(config["SESSION_COOKIE_SECURE"])
        self.assertTrue(config["CSRF_COOKIE_SECURE"])
        self.assertTrue(config["SECURE_SSL_REDIRECT"])
        self.assertEqual(config["SECURE_PROXY_SSL_HEADER"], ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_allowed_hosts_are_explicit_and_environment_can_override(self):
        config = self.load_settings(DJANGO_ALLOWED_HOSTS="example.pythonanywhere.com, 127.0.0.1")
        self.assertEqual(config["ALLOWED_HOSTS"], ["example.pythonanywhere.com", "127.0.0.1"])

    def test_production_does_not_serve_media_through_debug_url_patterns(self):
        with override_settings(DEBUG=False):
            config = runpy.run_path(str(Path(settings.BASE_DIR) / "photoblog" / "urls.py"))
        self.assertFalse(any("media" in str(pattern.pattern) for pattern in config["urlpatterns"]))

    def test_history_media_follows_the_persistent_target_of_a_release_media_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);shared=root/"shared/media";shared.mkdir(parents=True)
            release=root/"release";release.mkdir();(release/"media").symlink_to(shared,target_is_directory=True)
            config=self.load_settings(DJANGO_MEDIA_ROOT=str(release/"media"))
            self.assertEqual(config["HISTORY_MEDIA_ROOT"],root/"shared/private_tracking")

    def test_history_media_can_be_explicitly_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/"private-history"
            config=self.load_settings(HISTORY_MEDIA_ROOT=str(destination))
            self.assertEqual(config["HISTORY_MEDIA_ROOT"],destination)

    def test_daily_limits_have_bounded_defaults_and_allow_emergency_stop(self):
        with patch.dict(os.environ):
            os.environ.pop("HISTORY_LLM_DAILY_LIMIT", None)
            config = self.load_settings(HISTORY_EMBEDDING_DAILY_LIMIT="100")
        self.assertEqual(config["HISTORY_LLM_DAILY_LIMIT"], 3)
        self.assertEqual(config["HISTORY_EMBEDDING_DAILY_LIMIT"], 100)
        self.assertEqual(self.load_settings(HISTORY_LLM_DAILY_LIMIT="0")["HISTORY_LLM_DAILY_LIMIT"], 0)
        for invalid in ("-1", "unlimited", "10001", "", "５０"):
            with self.subTest(invalid=invalid), self.assertRaises(ImproperlyConfigured):
                self.load_settings(HISTORY_LLM_DAILY_LIMIT=invalid)
