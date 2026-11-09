from django.urls import path

from . import api_v1
from . import content_api
from . import history_api
from . import chat_api


urlpatterns = [
    path("history/usage/", history_api.HistoryUsage.as_view(), name="history_usage"),
    path("history/conversations/", chat_api.Conversations.as_view(), name="chat_conversations"),
    path("history/conversations/<uuid:conversation_id>/", chat_api.ConversationDetail.as_view(), name="chat_conversation"),
    path("history/embedding-documents/", history_api.HistoryEmbeddingDocuments.as_view(), name="history_embedding_documents"),
    path("history/overview/", history_api.HistoryOverview.as_view(), name="history_overview"),
    path("history/sessions/",history_api.HistorySessions.as_view(),name="history_sessions"),
    path("history/people/<str:profile_key>/",history_api.HistoryPerson.as_view(),name="history_person"),
    path("history/references/<str:profile_key>/",history_api.HistoryReference.as_view(),name="history_reference"),
    path("history/ingest/", history_api.HistoryIngest.as_view(), name="history_ingest"),
    path("history/frames/", history_api.HistoryFrames.as_view(), name="history_frames"),
    path("history/profiles/", history_api.HistoryProfiles.as_view(), name="history_profiles"),
    path("history/tracks/<int:track_id>/", history_api.TrackReview.as_view(), name="history_track_review"),
    path("history/images/<str:frame_id>/", history_api.HistoryImage.as_view(), name="history_image"),
    path("history/ask/", history_api.HistoryQuestion.as_view(), name="history_ask"),
    path("posts/<int:post_id>/content/", content_api.PostContent.as_view(), name="post_content"),
    path("post-contents/", content_api.ContentSummaries.as_view(), name="content_summaries"),
    path("content-posts/", content_api.ContentPosts.as_view(), name="content_posts"),
    path("photo-text-search/", content_api.PhotoTextSearch.as_view(), name="photo_text_search"),
    path("auth/me/", api_v1.AuthMe.as_view(), name="auth_me"),
]
