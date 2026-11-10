from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from blog import request_limits as limits
from blog.auth_limits import client_ip
from blog.history_embeddings import embed_texts, EmbeddingError
from blog.history_llm import generate


class IsolatedLimits:
    def setUp(self):
        super().setUp()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = override_settings(SECURITY_STATE_ROOT=self.folder.name,
            LOGIN_RATE_LIMIT_ENABLED=True,
            TRUST_PYTHONANYWHERE_REAL_IP=False, LOGIN_PAIR_FAILURE_LIMIT=5,
            LOGIN_IP_FAILURE_LIMIT=20, LOGIN_FAILURE_WINDOW_SECONDS=900,
            HISTORY_LLM_DAILY_LIMIT=3, HISTORY_EMBEDDING_DAILY_LIMIT=100)
        self.config.enable()
        self.addCleanup(self.config.disable)


class PersistentLimitTests(IsolatedLimits, SimpleTestCase):
    def test_atomic_reservations_cannot_exceed_daily_limit_across_connections(self):
        with override_settings(HISTORY_EMBEDDING_DAILY_LIMIT=3):
            def attempt(_):
                try:
                    limits.consume_api("embedding")
                    return True
                except limits.DailyLimit:
                    return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(attempt, range(16))), 3)
            with self.assertRaises(limits.DailyLimit):
                limits.consume_api("embedding")
        self.assertEqual(os.stat(limits.state_path()).st_mode & 0o777, 0o600)

    def test_parallel_login_attempts_reserve_slots_before_password_checks(self):
        def attempt(_):
            try:
                limits.reserve_auth("192.0.2.4", "operator")
                return True
            except limits.AuthBlocked:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(12))), 5)

    def test_daily_reset_is_korean_midnight_and_kinds_are_independent(self):
        with override_settings(HISTORY_LLM_DAILY_LIMIT=1, HISTORY_EMBEDDING_DAILY_LIMIT=1):
            with patch("blog.request_limits.timezone.now", return_value=datetime(2026,11,10,14,59,tzinfo=timezone.utc)):
                limits.consume_api("generation")
                limits.consume_api("embedding")
                with self.assertRaises(limits.DailyLimit) as caught:
                    limits.consume_api("generation")
                self.assertEqual(caught.exception.data["resets_at"], "2026-11-11T00:00:00+09:00")
            with patch("blog.request_limits.timezone.now", return_value=datetime(2026,11,10,15,0,tzinfo=timezone.utc)):
                limits.consume_api("generation")

    def test_login_block_lasts_fifteen_minutes_from_threshold_and_expires(self):
        for second in range(5):
            with patch("blog.request_limits.time.time", return_value=1000+second):
                limits.reserve_auth("192.0.2.4", "operator")
        with patch("blog.request_limits.time.time", return_value=1005):
            with self.assertRaises(limits.AuthBlocked) as caught:
                limits.reserve_auth("192.0.2.4", "operator")
            self.assertEqual(caught.exception.wait, 899)
        with patch("blog.request_limits.time.time", return_value=1904):
            limits.reserve_auth("192.0.2.4", "operator")

    def test_state_persists_and_contains_no_plaintext_account_or_address(self):
        for _ in range(5):
            limits.reserve_auth("192.0.2.123", "private-operator")
        with self.assertRaises(limits.AuthBlocked):
            limits.reserve_auth("192.0.2.123", "PRIVATE-OPERATOR")
        raw = limits.state_path().read_bytes()
        self.assertNotIn(b"192.0.2.123", raw)
        self.assertNotIn(b"private-operator", raw)

    def test_ip_limit_survives_username_rotation_and_success_does_not_erase_other_failures(self):
        with override_settings(LOGIN_IP_FAILURE_LIMIT=3):
            limits.reserve_auth("192.0.2.4", "other-a")
            limits.reserve_auth("192.0.2.4", "other-b")
            keys = limits.reserve_auth("192.0.2.4", "valid")
            limits.finish_auth(keys, success=True)
            limits.reserve_auth("192.0.2.4", "other-c")
            with self.assertRaises(limits.AuthBlocked):
                limits.reserve_auth("192.0.2.4", "other-d")

    def test_direct_clients_cannot_spoof_forwarded_headers(self):
        request = RequestFactory().get("/", REMOTE_ADDR="192.0.2.4",
            HTTP_X_REAL_IP="198.51.100.2", HTTP_X_FORWARDED_FOR="203.0.113.2")
        self.assertEqual(client_ip(request), "192.0.2.4")
        with override_settings(TRUST_PYTHONANYWHERE_REAL_IP=True):
            self.assertEqual(client_ip(request), "198.51.100.2")

    def test_ipv4_mapped_ipv6_cannot_create_a_second_bucket(self):
        request = RequestFactory().get("/", REMOTE_ADDR="::ffff:192.0.2.4")
        self.assertEqual(client_ip(request), "192.0.2.4")

    def test_symlink_store_fails_closed(self):
        target = Path(self.folder.name) / "target"
        target.write_bytes(b"unchanged")
        limits.state_path().symlink_to(target)
        with self.assertRaises(limits.LimitStoreUnavailable):
            limits.consume_api("generation")
        self.assertEqual(target.read_bytes(), b"unchanged")


@override_settings(BLOG_OWNER_USERNAME="publisher")
class LoginProtectionTests(IsolatedLimits, TestCase):
    def setUp(self):
        super().setUp()
        self.owner = get_user_model().objects.create_user("publisher", password="test-login-passphrase")

    def fail(self, path="/accounts/login/", username="publisher", **headers):
        return self.client.post(path, {"username": username, "password": "wrong"}, **headers)

    def test_website_and_token_failures_share_a_limit(self):
        for _ in range(4):
            self.assertEqual(self.fail().status_code, 200)
        self.assertEqual(self.fail("/api-token-auth/").status_code, 400)
        with patch("django.contrib.auth.backends.ModelBackend.authenticate") as authenticate:
            response = self.fail("/api-token-auth/")
            self.assertEqual(response.status_code, 429)
            self.assertGreater(int(response["Retry-After"]), 0)
            authenticate.assert_not_called()
        self.assertEqual(self.fail().status_code, 429)

    def test_admin_login_is_also_protected(self):
        for _ in range(5):
            self.assertEqual(self.fail("/admin/login/").status_code, 200)
        response = self.fail("/admin/login/")
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "잠시 후", status_code=429)

    def test_successful_login_resets_pair_and_normal_logout_still_works(self):
        for _ in range(4):
            self.fail()
        response = self.client.post("/accounts/login/", {"username":"publisher", "password":"test-login-passphrase"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 302)
        for _ in range(5):
            self.assertEqual(self.fail().status_code, 200)
        self.assertEqual(self.fail().status_code, 429)

    def test_token_success_resets_counter_and_json_login_cannot_bypass(self):
        client = APIClient()
        for _ in range(4):
            self.assertEqual(client.post("/api-token-auth/", {"username":"publisher", "password":"wrong"}, format="json").status_code, 400)
        self.assertEqual(client.post("/api-token-auth/", {"username":"publisher", "password":"test-login-passphrase"}, format="json").status_code, 200)
        self.assertEqual(self.fail("/api-token-auth/").status_code, 400)

    def test_get_and_other_ip_are_not_locked_out(self):
        for _ in range(5):
            self.fail()
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)
        self.assertEqual(self.fail(REMOTE_ADDR="192.0.2.7").status_code, 200)
        self.assertEqual(self.client.get("/api_root/").status_code, 200)

    def test_forwarded_header_changes_do_not_evade_local_limit(self):
        for index in range(5):
            self.fail(HTTP_X_FORWARDED_FOR=f"192.0.2.{index}", HTTP_X_REAL_IP=f"198.51.100.{index}")
        self.assertEqual(self.fail(HTTP_X_REAL_IP="198.51.100.77").status_code, 429)

    def test_unknown_user_has_same_protection_and_no_account_disclosure(self):
        for _ in range(5):
            self.fail(username="absent-account")
        response = self.fail(username="absent-account")
        self.assertEqual(response.status_code, 429)
        self.assertNotContains(response, "absent-account", status_code=429)

    def test_store_failure_prevents_authentication(self):
        with patch("blog.auth_limits.reserve_auth", side_effect=limits.LimitStoreUnavailable), patch("django.contrib.auth.backends.ModelBackend.authenticate") as authenticate:
            self.assertEqual(self.fail().status_code, 503)
            authenticate.assert_not_called()

    def test_csrf_protection_still_rejects_before_authentication(self):
        client = Client(enforce_csrf_checks=True)
        with patch("django.contrib.auth.backends.ModelBackend.authenticate") as authenticate:
            self.assertEqual(client.post("/accounts/login/", {"username":"publisher", "password":"wrong"}).status_code, 403)
            authenticate.assert_not_called()
        self.assertFalse(limits.state_path().exists())

    def test_usage_is_owner_only_and_reading_does_not_consume_quota(self):
        api = APIClient()
        self.assertEqual(api.get("/api/v1/history/usage/").status_code, 401)
        other = get_user_model().objects.create_user("reader")
        api.force_authenticate(other)
        self.assertEqual(api.get("/api/v1/history/usage/").status_code, 403)
        api.force_authenticate(self.owner)
        limits.consume_api("generation")
        for _ in range(2):
            response = api.get("/api/v1/history/usage/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["daily"]["generation"], {"limit":3,"used":1,"remaining":2})
            self.assertEqual(response["Cache-Control"], "private, no-store")


@override_settings(HISTORY_LLM_PROVIDER="openai", HISTORY_LLM_API_KEY="isolated-test-key",
                   HISTORY_LLM_MODEL="test-model", HISTORY_EMBEDDING_API_KEY="isolated-test-key")
class PaidTransportLimitTests(IsolatedLimits, SimpleTestCase):
    def test_generation_limit_prevents_transport_and_failures_still_count(self):
        retrieved = {"facts":{}, "interpretation":{}, "evidence":[]}
        with patch("blog.history_llm.urlopen", side_effect=TimeoutError) as transport:
            for _ in range(3):
                self.assertEqual(generate("설명", retrieved)["status"], "unavailable")
            result = generate("다시 설명", retrieved)
            self.assertEqual(result["status"], "daily_limit")
            self.assertEqual(result["used"], 3)
            self.assertEqual(transport.call_count, 3)

    def test_embedding_limit_prevents_transport_and_failures_still_count(self):
        with override_settings(HISTORY_EMBEDDING_DAILY_LIMIT=1), patch("blog.history_embeddings.urlopen", side_effect=TimeoutError) as transport:
            with self.assertRaises(EmbeddingError):
                embed_texts(["검색"], approved=True)
            with self.assertRaises(limits.DailyLimit):
                embed_texts(["다시 검색"], approved=True)
            transport.assert_called_once()

    def test_zero_limit_disables_both_paid_transports(self):
        with override_settings(HISTORY_LLM_DAILY_LIMIT=0, HISTORY_EMBEDDING_DAILY_LIMIT=0), patch("blog.history_llm.urlopen") as llm, patch("blog.history_embeddings.urlopen") as embedding:
            self.assertEqual(generate("설명", {"facts":{},"interpretation":{},"evidence":[]})["status"], "daily_limit")
            with self.assertRaises(limits.DailyLimit):
                embed_texts(["검색"], approved=True)
            llm.assert_not_called()
            embedding.assert_not_called()

    def test_usage_store_failure_never_calls_either_provider(self):
        with patch("blog.request_limits.connection", side_effect=limits.LimitStoreUnavailable), patch("blog.history_llm.urlopen") as llm, patch("blog.history_embeddings.urlopen") as embedding:
            self.assertEqual(generate("설명", {"facts":{},"interpretation":{},"evidence":[]})["status"], "unavailable")
            with self.assertRaises(EmbeddingError):
                embed_texts(["검색"], approved=True)
            llm.assert_not_called()
            embedding.assert_not_called()
