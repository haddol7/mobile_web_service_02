from django.urls import path

from . import api_v1
from . import content_api


urlpatterns = [
    path("posts/<int:post_id>/content/", content_api.PostContent.as_view(), name="post_content"),
    path("post-contents/", content_api.ContentSummaries.as_view(), name="content_summaries"),
    path("content-posts/", content_api.ContentPosts.as_view(), name="content_posts"),
    path("photo-text-search/", content_api.PhotoTextSearch.as_view(), name="photo_text_search"),
    path("auth/me/", api_v1.AuthMe.as_view(), name="auth_me"),
]
