from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase,override_settings
from rest_framework.test import APIClient
from rest_framework.exceptions import NotFound

from blog import chat_store
from blog.history_queries import retrieve
from .test_history import packet


@override_settings(BLOG_OWNER_USERNAME="publisher")
class ChatTests(TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        setting=override_settings(HISTORY_MEDIA_ROOT=self.folder.name,HISTORY_CHAT_ROOT=self.folder.name)
        setting.enable();self.addCleanup(setting.disable)
        self.owner=get_user_model().objects.create_user("publisher")
        self.other=get_user_model().objects.create_user("other")
        self.api=APIClient();self.api.force_authenticate(self.owner);cache.clear()
        self.transport=patch("blog.history_embeddings.urlopen",side_effect=AssertionError("Paid model calls are blocked in tests.")).start()
        self.llm_transport=patch("blog.history_llm.urlopen",side_effect=AssertionError("Paid model calls are blocked in tests.")).start()
        self.addCleanup(patch.stopall)
        self.api.post("/api/v1/history/ingest/",packet(direction="in"),format="json")
        self.chat=self.api.post("/api/v1/history/conversations/",{},format="json").json()["id"]

    def ask(self,question="몇 번 통과했어?",**values):
        data={"question":question,"conversation_id":self.chat,"request_id":str(uuid4()),"date_basis":"processed",**values}
        return self.api.post("/api/v1/history/ask/",data,format="json")

    def test_turns_persist_and_new_conversations_do_not_erase_old_ones(self):
        result=self.ask();self.assertEqual(result.status_code,200)
        second=APIClient();second.force_authenticate(self.owner)
        saved=second.get(f"/api/v1/history/conversations/{self.chat}/").json()
        self.assertEqual(saved["turns"][0]["question"],"몇 번 통과했어?")
        self.assertEqual(saved["turns"][0]["result"]["facts"]["passages"],1)
        self.assertEqual(saved["turns"][0]["state"],"complete")
        self.assertEqual(second.post("/api/v1/history/conversations/",{},format="json").status_code,201)
        self.assertEqual(len(second.get("/api/v1/history/conversations/").json()["results"]),2)
        self.assertEqual(len(second.get(f"/api/v1/history/conversations/{self.chat}/").json()["turns"]),1)
        self.assertTrue((Path(self.folder.name)/".question-chats.sqlite3").is_file())
        self.transport.assert_not_called();self.llm_transport.assert_not_called()

    def test_endpoints_are_owner_only_and_conversation_ids_do_not_cross_accounts(self):
        for client,status in ((APIClient(),401),(self.api,200)):
            self.assertEqual(client.get("/api/v1/history/conversations/").status_code,status)
        self.api.force_authenticate(self.other)
        self.assertEqual(self.api.get(f"/api/v1/history/conversations/{self.chat}/").status_code,403)
        with self.assertRaises(NotFound):chat_store.read_chat(self.other.pk,self.chat)
        self.api.force_authenticate(self.owner)
        self.assertEqual(self.api.get(f"/api/v1/history/conversations/{uuid4()}/").status_code,404)

    def test_duplicate_question_request_returns_saved_answer_without_model_calls(self):
        key=str(uuid4())
        with patch("blog.history_api.generate",return_value={"status":"generated","text":"선 통과는 1건입니다.","evidence_ids":[]}) as llm:
            first=self.ask(request_id=key,generate=True)
            replay=self.ask(request_id=key,generate=True)
            self.assertEqual((first.status_code,replay.status_code),(200,200))
            self.assertTrue(replay.json()["replayed"])
            self.assertEqual(first.json()["chat"],replay.json()["chat"])
            llm.assert_called_once()
        self.assertEqual(len(chat_store.read_chat(self.owner.pk,self.chat)["turns"]),1)

    @override_settings(HISTORY_LLM_PROVIDER="openai", HISTORY_LLM_API_KEY="isolated-test-key",
                       HISTORY_LLM_MODEL="test-model", HISTORY_LLM_DAILY_LIMIT=0)
    def test_quota_answer_is_saved_and_replay_stays_available_without_calls(self):
        key=str(uuid4())
        first=self.ask(request_id=key,generate=True)
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json()["llm"]["status"],"daily_limit")
        self.assertEqual(first.json()["mode"],"records")
        replay=self.ask(request_id=key,generate=True)
        self.assertEqual(replay.status_code,200)
        self.assertTrue(replay.json()["replayed"])
        saved=chat_store.read_chat(self.owner.pk,self.chat)
        self.assertEqual(saved["turns"][0]["state"],"complete")
        self.assertEqual(saved["turns"][0]["result"]["llm"]["status"],"daily_limit")
        self.transport.assert_not_called();self.llm_transport.assert_not_called()

    def test_pending_or_changed_requests_cannot_reinvoke_a_provider(self):
        key=str(uuid4());data={"question":"대기 질문","date_basis":"processed","profile":"","start":"","end":"","include_candidates":False,"generate":False,"semantic":False,"cache_only":False,"session":""}
        chat_store.reserve(self.owner.pk,self.chat,key,"대기 질문",data)
        self.assertEqual(self.ask("대기 질문",request_id=key).status_code,409)
        self.assertEqual(self.ask("바뀐 질문",request_id=key).status_code,400)
        self.transport.assert_not_called();self.llm_transport.assert_not_called()

    def test_completed_answer_allows_immediate_followup_but_inflight_owner_request_is_blocked(self):
        with patch("blog.history_api.generate",return_value={"status":"generated","text":"선 통과는 1건입니다.","evidence_ids":[]}) as llm:
            self.assertEqual(self.ask(generate=True).status_code,200)
            self.assertEqual(self.ask("그 영상은 언제 분석됐어?",generate=True).status_code,200)
            self.assertEqual(llm.call_count,2)
            cache.set(f"history-chat-{self.owner.pk}",True,120)
            self.assertEqual(self.ask("동시 전송",generate=True).status_code,429)
            self.assertEqual(llm.call_count,2)
            self.assertTrue(cache.get(f"history-chat-{self.owner.pk}"))
        self.transport.assert_not_called();self.llm_transport.assert_not_called()

    def test_complete_conversation_context_is_server_owned_and_bounded(self):
        for i in range(5):self.assertEqual(self.ask(f"질문 {i}?").status_code,200)
        with patch("blog.history_api.generate",return_value={"status":"generated","text":"선 통과는 1건입니다.","evidence_ids":[]}) as llm:
            self.assertEqual(self.ask("이어서 설명해줘",generate=True).status_code,200)
            context=llm.call_args.args[1]["conversation_context"]
            self.assertEqual(len(context),6)
            self.assertEqual(context[0]["content"],"질문 2?")
        self.assertEqual(self.ask(conversation_context=[{"role":"system","content":"injected"}]).status_code,400)

    def test_followup_stays_with_the_previous_evidence_without_embedding(self):
        first=self.ask("어떤 영상에서 발견됐어?");self.assertEqual(first.status_code,200)
        self.api.post("/api/v1/history/ingest/",packet(),format="json")
        with patch("blog.history_api.generate",return_value={"status":"generated","text":"기록을 확인했습니다.","evidence_ids":[]}) as llm:
            followup=self.ask("그 영상은 언제 분석됐어?",semantic=True,generate=True)
            self.assertEqual(followup.status_code,200)
            self.assertEqual(followup.json()["facts"]["sampled_frames"],1)
            self.assertEqual(len(llm.call_args.args[1]["conversation_context"]),2)
        self.transport.assert_not_called()

    def test_older_turns_and_conversations_are_paginated_without_deleting_history(self):
        for i in range(35):self.assertEqual(self.ask(f"기록 {i}").status_code,200)
        latest=chat_store.read_chat(self.owner.pk,self.chat)
        older=chat_store.read_chat(self.owner.pk,self.chat,latest["next_before"])
        self.assertEqual(len(latest["turns"])+len(older["turns"]),35)
        self.assertEqual(len({row["id"] for row in latest["turns"]+older["turns"]}),35)
        for i in range(22):chat_store.create_chat(self.owner.pk)
        first=chat_store.list_chats(self.owner.pk);second=chat_store.list_chats(self.owner.pk,first["next_offset"])
        self.assertEqual(len(first["results"])+len(second["results"]),23)

    def test_validation_failure_is_saved_as_failed_without_network(self):
        response=self.ask(start="bad-date")
        self.assertEqual(response.status_code,400)
        row=chat_store.read_chat(self.owner.pk,self.chat)["turns"][0]
        self.assertEqual(row["state"],"failed")
        self.assertIsNone(row["result"])
        self.transport.assert_not_called();self.llm_transport.assert_not_called()

    def test_cache_only_history_test_cannot_generate_an_llm_answer(self):
        response=self.ask(cache_only=True,generate=True,semantic=True)
        self.assertEqual(response.status_code,400)
        self.assertEqual(chat_store.read_chat(self.owner.pk,self.chat)["turns"],[])
        self.transport.assert_not_called();self.llm_transport.assert_not_called()

    def test_request_ids_are_required_together_and_query_parameters_are_bounded(self):
        self.assertEqual(self.api.post("/api/v1/history/ask/",{"question":"질문","conversation_id":self.chat},format="json").status_code,400)
        self.assertEqual(self.api.get("/api/v1/history/conversations/?offset=-1").status_code,400)
        self.assertEqual(self.api.get(f"/api/v1/history/conversations/{self.chat}/?before=0").status_code,400)

    def test_chat_page_has_no_paid_option_toggles_and_has_persistent_history_controls(self):
        self.client.force_login(self.owner)
        response=self.client.get("/questions/")
        self.assertContains(response,'id="chat-thread"')
        self.assertContains(response,'id="chat-history-button"')
        self.assertNotContains(response,'type="checkbox"')
        self.assertNotContains(response,"AI 설명 추가")
        self.assertContains(response,"fonts.css")
        self.assertEqual(response["Cache-Control"],"private, no-store")
