from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from rest_framework import permissions, viewsets

from .forms import PostForm
from .forms import PhotoSearchForm
from .content_rules import ContentError, THEMES, query_terms, normalize
from .content_queries import filter_content, matching_line_ids
from django.core.paginator import Paginator
from urllib.parse import urlencode
from .models import Post
from .permissions import IsPostOwnerOrReadOnly
from .serializers import PostSerializer
from . import services
from .ownership import require_blog_owner, can_manage_post


def post_list(request):
    posts = Post.objects.filter(published_date__lte=timezone.now()).select_related("author", "content").prefetch_related("content__tags")
    search = PhotoSearchForm(request.GET)
    if search.is_valid():
        try:
            terms = query_terms(search.cleaned_data["q"]) if search.cleaned_data["q"] else []
            posts = filter_content(posts, theme=search.cleaned_data["theme"], tag=search.cleaned_data["tag"], terms=terms)
        except ContentError as error:
            search.add_error("q", error.detail)
            posts = posts.none()
    else:
        posts = posts.none()
    page = Paginator(posts, 20).get_page(request.GET.get("page"))
    for post in page.object_list:
        post.theme_name = THEMES.get(post.content.theme, "미분류") if hasattr(post, "content") else "미분류"
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "blog/post_list.html", {"posts":page.object_list, "page_obj":page,
        "search_form":search,"search_query":request.GET.get("q", ""),"query_string":urlencode(params)})


def post_detail(request, pk):
    post = get_object_or_404(Post.objects.select_related("author"), pk=pk, published_date__lte=timezone.now())
    from .content_api import content_payload
    content = content_payload(post)
    query = request.GET.get("q", "")
    try:
        terms = query_terms(query) if query else []
    except ContentError:
        terms = []
    matches = matching_line_ids(content["lines"], terms)
    return render(request, "blog/post_detail.html", {"post":post,"can_manage_post":can_manage_post(request.user,post),"photo_content":content,"theme_name":THEMES.get(content["theme"],"미분류"),
        "detail_config":{"image":post.image.url,"content":content,"matched_ids":matches,"query":query if terms else ""}})


@login_required
def post_new(request):
    require_blog_owner(request.user)
    form = PostForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        post = services.create_post(actor=request.user, values=form.cleaned_data)
        return redirect("post_detail", pk=post.pk)
    return render(request, "blog/post_edit.html", {"form": form, "editing": False,"composer_config":{"post_id":None}})


@login_required
def post_edit(request, pk):
    require_blog_owner(request.user)
    post = get_object_or_404(Post, pk=pk)
    if not can_manage_post(request.user, post):
        raise PermissionDenied
    form = PostForm(request.POST if request.method == "POST" else None, request.FILES or None, instance=post)
    if request.method == "POST" and form.is_valid():
        values = {"title": form.cleaned_data["title"], "text": form.cleaned_data["text"]}
        if "image" in request.FILES:
            values["image"] = form.cleaned_data["image"]
        services.update_post(actor=request.user, post_id=post.pk, values=values)
        return redirect("post_detail", pk=post.pk)
    return render(request, "blog/post_edit.html", {"form": form, "editing": True,"composer_config":{"post_id":post.pk,"image":post.image.url}})


@login_required
@require_POST
def post_delete(request, pk):
    require_blog_owner(request.user)
    post = get_object_or_404(Post, pk=pk)
    if not can_manage_post(request.user, post):
        raise PermissionDenied
    services.delete_post(actor=request.user, post_id=post.pk)
    return redirect("post_list")


def js_test(request):
    return render(request, "blog/js_test.html")


def content_check(request):
    from django.conf import settings
    from django.http import Http404
    if not settings.DEBUG:
        raise Http404
    return render(request, "blog/content_check.html")


class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    queryset = Post.objects.select_related("author").order_by("-created_date", "-id")
    permission_classes = (permissions.IsAuthenticatedOrReadOnly, IsPostOwnerOrReadOnly)
    pagination_class = None

    def handle_exception(self, exc):
        from .content_rules import ContentError
        from .content_api import content_error_response
        if isinstance(exc, ContentError):
            return content_error_response(exc)
        return super().handle_exception(exc)

    def get_queryset(self):
        return super().get_queryset().filter(published_date__lte=timezone.now())

    def perform_create(self, serializer):
        serializer.instance = services.create_post(actor=self.request.user, values=serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = services.update_post(actor=self.request.user, post_id=serializer.instance.pk, values=serializer.validated_data)

    def perform_destroy(self, instance):
        services.delete_post(actor=self.request.user, post_id=instance.pk)


