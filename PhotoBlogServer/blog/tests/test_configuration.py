import os
from pathlib import Path
import runpy
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
