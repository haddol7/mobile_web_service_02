"""Isolated deployment-helper checks; no production or development DB writes."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from deploy.create_private_config import create_config
from deploy.production import load_environment, validate_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProductionPreparationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="common01-deploy-test-")
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / "production.json"
        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.values = {
            "DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DJANGO_ALLOWED_HOSTS": "daejinha.pythonanywhere.com",
        }

    def write_config(self, values=None):
        self.config.write_text(json.dumps(self.values if values is None else values), encoding="utf-8")
        self.config.chmod(0o600)

    def test_loads_exact_production_values_before_django_import(self):
        self.write_config()
        self.assertEqual(load_environment(self.config, PROJECT_ROOT), PROJECT_ROOT)
        self.assertEqual(os.environ["DJANGO_DEBUG"], "false")
        self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "photoblog.settings")
        self.assertTrue(os.environ["DJANGO_SECRET_KEY"] == self.values["DJANGO_SECRET_KEY"], "Loaded secret must match; values redacted.")

    def test_missing_file_does_not_mutate_environment(self):
        before = dict(os.environ)
        with self.assertRaises(ValueError):
            load_environment(self.config, PROJECT_ROOT)
        self.assertTrue(dict(os.environ) == before, "Invalid configuration must not mutate environment; values redacted.")

    def test_missing_extra_and_non_object_configuration_rejected(self):
        for values in (None, [], {}, {**self.values, "EXTRA": "unexpected"}):
            with self.subTest(kind=type(values).__name__), self.assertRaises(ValueError):
                validate_values(values)

    def test_debug_true_rejected_even_with_good_secret(self):
        with self.assertRaises(ValueError):
            validate_values({**self.values, "DJANGO_DEBUG": "true"})

    def test_unsafe_or_placeholder_secrets_rejected_without_echo(self):
        for secret in ("short", "a" * 64, "django-insecure-" + "abcdefgh" * 8,
                       "REPLACE_WITH_A_PRIVATE_RANDOM_SECRET_DO_NOT_COMMIT_IT", None):
            with self.subTest(kind=type(secret).__name__):
                with self.assertRaises(ValueError) as raised:
                    validate_values({**self.values, "DJANGO_SECRET_KEY": secret})
                if isinstance(secret, str):
                    self.assertNotIn(secret, str(raised.exception))

    def test_wildcard_localhost_multiple_or_url_hosts_rejected(self):
        for host in ("*", "localhost", "daejinha.pythonanywhere.com,localhost",
                     "https://daejinha.pythonanywhere.com", "evil.invalid", None):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_values({**self.values, "DJANGO_ALLOWED_HOSTS": host})

    def test_world_readable_file_and_directory_rejected(self):
        self.write_config()
        self.config.chmod(0o644)
        with self.assertRaises(ValueError):
            load_environment(self.config, PROJECT_ROOT)
        self.config.chmod(0o600)
        self.config.parent.chmod(0o755)
        try:
            with self.assertRaises(ValueError):
                load_environment(self.config, PROJECT_ROOT)
        finally:
            self.config.parent.chmod(0o700)

    def test_duplicate_keys_invalid_json_and_oversized_config_rejected(self):
        for content in ('{"DJANGO_SECRET_KEY":"first","DJANGO_SECRET_KEY":"second"}',
                        '{"DJANGO_SECRET_KEY": "private-parser-input", invalid}', " " * 17000):
            self.config.write_text(content, encoding="utf-8")
            self.config.chmod(0o600)
            with self.assertRaises(ValueError) as raised:
                load_environment(self.config, PROJECT_ROOT)
            self.assertNotIn("private-parser-input", str(raised.exception))

    def test_configuration_inside_source_or_symlink_rejected(self):
        with self.assertRaises(ValueError):
            load_environment(PROJECT_ROOT / "production.json", PROJECT_ROOT)
        self.write_config()
        link = self.config.parent / "linked.json"
        link.symlink_to(self.config)
        with self.assertRaises(ValueError):
            load_environment(link, PROJECT_ROOT)

    def test_creator_does_not_print_or_overwrite_secret(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(create_config(self.config, "daejinha.pythonanywhere.com"), self.config)
        self.assertEqual(output.getvalue(), "")
        first = self.config.read_bytes()
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            create_config(self.config, "daejinha.pythonanywhere.com")
        self.assertTrue(self.config.read_bytes() == first, "Existing private configuration must remain unchanged; values redacted.")

    def test_wsgi_example_fails_without_path_replacement(self):
        with self.assertRaisesRegex(RuntimeError, "approved Common Assessment"):
            runpy.run_path(str(PROJECT_ROOT / "deploy/pythonanywhere_wsgi.py.example"))

    def test_wsgi_loads_real_application_with_private_production_values(self):
        self.write_config()
        script = """
from pathlib import Path
import sys
root, config = map(Path, sys.argv[1:])
source = (root / 'deploy/pythonanywhere_wsgi.py.example').read_text(encoding='utf-8')
source = source.replace('/home/REPLACE_USERNAME/REPLACE_APPROVED_REPOSITORY/common01/PhotoBlogServer', str(root))
source = source.replace('/home/REPLACE_USERNAME/.config/common01/production.json', str(config))
namespace = {}
exec(compile(source, 'pythonanywhere_wsgi.py.example', 'exec'), namespace)
from django.conf import settings
assert callable(namespace['application'])
assert settings.DEBUG is False
assert settings.ALLOWED_HOSTS == ['daejinha.pythonanywhere.com']
assert settings.SECURE_SSL_REDIRECT and settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
print('Production WSGI application loaded in WSL; cloud deployment not performed.')
"""
        result = subprocess.run([
            sys.executable, "-B", "-c", script, str(PROJECT_ROOT), str(self.config),
        ], cwd=PROJECT_ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, "WSGI application import failed; confidential values redacted.")
        self.assertIn("Production WSGI application loaded", result.stdout)
        self.assertFalse(self.values["DJANGO_SECRET_KEY"] in result.stdout + result.stderr, "Secret must not appear in command output.")

    def test_non_linux_execution_rejected(self):
        with patch("deploy.production.os.name", "nt"), self.assertRaises(RuntimeError):
            load_environment(self.config, PROJECT_ROOT)

    def test_management_wrapper_deployment_checks_without_secret_output(self):
        self.write_config()
        result = subprocess.run([
            sys.executable, "-B", str(PROJECT_ROOT / "deploy/manage_production.py"),
            "--config", str(self.config), "check", "--deploy",
        ], cwd=PROJECT_ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, "Production check failed; confidential values redacted.")
        self.assertIn("security.W005", result.stderr)
        self.assertIn("security.W021", result.stderr)
        self.assertFalse(self.values["DJANGO_SECRET_KEY"] in result.stdout + result.stderr, "Secret must not appear in command output.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
