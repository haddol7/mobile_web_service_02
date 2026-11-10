import json
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


class PublicAccessTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        config = override_settings(HISTORY_CHAT_ROOT=self.folder.name,
            SECURITY_STATE_ROOT=self.folder.name, HISTORY_MEDIA_ROOT=self.folder.name,
            HISTORY_LLM_API_KEY="", HISTORY_EMBEDDING_API_KEY="")
        config.enable()
        self.addCleanup(config.disable)

    def test_public_pages_and_read_apis_do_not_need_an_admin_or_login(self):
        visitor = APIClient()
        for path in ("/", "/people/", "/questions/", "/detections/",
                     "/api/v1/history/frames/", "/api/v1/history/profiles/",
                     "/api/v1/history/overview/"):
            self.assertEqual(visitor.get(path).status_code, 200, path)
        user = get_user_model().objects.create_user("ordinary-viewer")
        visitor.force_authenticate(user)
        self.assertEqual(visitor.get("/api/v1/history/overview/").status_code, 200)

    def test_guest_conversations_are_isolated_and_restore_in_the_same_browser(self):
        first, second = APIClient(), APIClient()
        key = first.post("/api/v1/history/conversations/", {}, format="json").json()["id"]
        response = first.post("/api/v1/history/ask/", {"question": "저장된 기록은?",
            "conversation_id": key, "request_id": str(uuid4())}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(first.get(f"/api/v1/history/conversations/{key}/").json()["turns"]), 1)
        self.assertEqual(second.get(f"/api/v1/history/conversations/{key}/").status_code, 404)
        self.assertEqual(second.get("/api/v1/history/conversations/").json()["results"], [])
        self.assertEqual(second.post("/api/v1/history/ask/", {"question": "다른 방문자의 대화",
            "conversation_id": key, "request_id": str(uuid4())}, format="json").status_code, 404)

    def test_guest_cannot_access_operator_mutations_or_private_usage(self):
        client = APIClient()
        for path in ("/api/v1/history/usage/", "/api/v1/history/embedding-documents/"):
            self.assertEqual(client.get(path).status_code, 401)
        for method, path in (("post", "/api/v1/history/ingest/"),
                             ("patch", "/api/v1/history/profiles/"),
                             ("patch", "/api/v1/history/tracks/1/"),
                             ("post", "/api/v1/history/references/person-a/")):
            self.assertIn(getattr(client, method)(path, {}, format="json").status_code, (401, 403))

    def test_guest_browser_writes_require_csrf_and_work_with_a_valid_token(self):
        client = APIClient(enforce_csrf_checks=True)
        url = "/api/v1/history/conversations/"
        self.assertEqual(client.post(url, {}, format="json").status_code, 403)
        self.assertEqual(client.get("/questions/").status_code, 200)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(url, {}, format="json", HTTP_X_CSRFTOKEN=token).status_code, 201)

    @override_settings(HISTORY_LLM_PROVIDER="openai", HISTORY_LLM_MODEL="test-model",
                       HISTORY_LLM_API_KEY="isolated-test-key", HISTORY_LLM_DAILY_LIMIT=5)
    def test_five_generation_calls_are_shared_across_visitors_and_the_sixth_is_blocked(self):
        raw = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content":
            json.dumps({"answer": "조건에 맞는 기록이 없습니다.", "evidence_ids": []})}}]}).encode()
        with patch("blog.history_llm.urlopen") as transport:
            transport.return_value.__enter__.return_value.read.return_value = raw
            statuses = []
            for _ in range(6):
                client = APIClient()
                result = client.post("/api/v1/history/ask/", {"question": "기록이 있어?",
                    "generate": True}, format="json")
                self.assertEqual(result.status_code, 200)
                statuses.append(result.json()["llm"]["status"])
            self.assertEqual(statuses, ["generated"] * 5 + ["daily_limit"])
            self.assertEqual(transport.call_count, 5)

    def test_login_attempt_limiter_is_disabled_by_default(self):
        self.assertFalse(settings.LOGIN_RATE_LIMIT_ENABLED)
        with patch("blog.auth_limits.reserve_auth") as limiter:
            response = self.client.post("/accounts/login/", {"username": "not-a-user", "password": "invalid"})
            self.assertEqual(response.status_code, 200)
            limiter.assert_not_called()
