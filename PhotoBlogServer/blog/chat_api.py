from rest_framework import serializers
from rest_framework.response import Response
from .history_api import PublicQuestionAPI
from .history_access import conversation_owner
from .history_serializers import StrictSerializer
from . import chat_store


class Conversations(PublicQuestionAPI):
    def get(self, request):
        class Query(StrictSerializer):
            offset = serializers.IntegerField(min_value=0, max_value=1000000, default=0)
        form = Query(data=request.query_params)
        form.is_valid(raise_exception=True)
        return Response(chat_store.list_chats(conversation_owner(request), form.validated_data["offset"]))

    def post(self, request):
        form = StrictSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        return Response(chat_store.create_chat(conversation_owner(request)), status=201)


class ConversationDetail(PublicQuestionAPI):
    def get(self, request, conversation_id):
        class Query(StrictSerializer):
            before = serializers.IntegerField(min_value=1, required=False)
        form = Query(data=request.query_params)
        form.is_valid(raise_exception=True)
        return Response(chat_store.read_chat(conversation_owner(request), conversation_id, form.validated_data.get("before")))
