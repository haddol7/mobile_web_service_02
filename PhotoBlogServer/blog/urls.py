from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("Post", views.PostViewSet)

urlpatterns = [
    path("dev/content-check/", views.content_check, name="content_check"),
    path("", views.post_list, name="post_list"),
    path("post/new/", views.post_new, name="post_new"),
    path("post/<int:pk>/", views.post_detail, name="post_detail"),
    path("post/<int:pk>/edit/", views.post_edit, name="post_edit"),
    path("post/<int:pk>/delete/", views.post_delete, name="post_delete"),
    path("js_test/", views.js_test, name="js_test"),
    path("api_root/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls")),
]
