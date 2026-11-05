"""Public photo-content browsing/search and owner-only corrections."""
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Exists, OuterRef, Q, Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .content_rules import ContentError, THEMES, normalize, query_terms
from .content_services import update_content
from .content_queries import filter_content, matching_line_ids
from .models import PhotoContent, PhotoTextLine, Post
from .serializers import PostSerializer


def content_error_response(error):
    body = {"code": error.code, "detail": error.detail, "fields": {error.field: error.detail}}
    if error.revision is not None:
        body["current_revision"] = error.revision
    return Response(body, status=error.status)


def public_posts():
    return Post.objects.filter(published_date__lte=timezone.now()).select_related("author", "content").prefetch_related("content__tags")


def content_payload(post, *, summary=False):
    try:
        content = post.content
    except PhotoContent.DoesNotExist:
        content = None
    result = {"post_id": post.pk, "revision": content.revision if content else 0,
              "image_sha256": content.image_sha256 if content else None,
              "width": content.width if content else None, "height": content.height if content else None,
              "theme": content.theme if content else None,
              "theme_status": content.theme_status if content else "not_analyzed",
              "theme_origin": content.theme_origin if content else "unclassified",
              "tags": [{"display": t.display, "origin": t.origin} for t in content.tags.all()] if content else [],
              "ocr_status": content.ocr_status if content else "not_analyzed"}
    if not summary:
        result.update(schema_version=1, model_versions=content.model_versions if content else {},
                      mapping_version=content.mapping_version if content else "",
                      lines=[line_payload(line) for line in content.lines.all()] if content else [])
    return result


def line_payload(line):
    return {"line_id": str(line.line_id), "text": line.text, "quad": line.quad, "origin": line.origin}


class ContentAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    def handle_exception(self, exc):
        if isinstance(exc, ContentError):
            return content_error_response(exc)
        if isinstance(exc, ObjectDoesNotExist):
            exc = NotFound("사진글을 찾을 수 없습니다.")
        return super().handle_exception(exc)


class PostContent(ContentAPIView):
    def get(self, request, post_id):
        return Response(content_payload(public_posts().get(pk=post_id)))

    def patch(self, request, post_id):
        if not request.user.is_authenticated:
            self.permission_denied(request)
        public_posts().get(pk=post_id)
        update_content(actor=request.user, post_id=post_id, packet=request.data)
        return Response(content_payload(public_posts().get(pk=post_id)))


class ContentSummaries(ContentAPIView):
    def get(self, request):
        values = request.query_params.get("ids", "").split(",")
        if not 1 <= len(values) <= 50 or any(not v.isascii() or not v.isdigit() or len(v) > 18 or int(v) <= 0 for v in values):
            raise ContentError("양의 글 ID를 최대 50개까지 입력하세요.", field="ids")
        ids = list(dict.fromkeys(int(v) for v in values))
        return Response({"results": [content_payload(p, summary=True) for p in public_posts().filter(pk__in=ids)]})


class ContentPosts(ContentAPIView):
    search = False

    def get(self, request):
        allowed = {"q", "theme", "tag", "author", "cursor", "limit"} if self.search else {"theme", "tag", "author", "cursor", "limit"}
        if set(request.query_params) - allowed or any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
            raise ContentError("조회 조건 구성을 확인하세요.", field="query")
        theme, tag, author = (request.query_params.get(k, "") for k in ("theme", "tag", "author"))
        if theme and theme not in THEMES and theme != "unclassified":
            raise ContentError("테마를 확인하세요.", field="theme")
        if len(tag) > 30 or (tag and not normalize(tag)):
            raise ContentError("태그는 1–30문자로 입력하세요.", field="tag")
        if author not in ("", "me"):
            raise ContentError("작성자 조건을 확인하세요.", field="author")
        if author and not request.user.is_authenticated:
            self.permission_denied(request)
        raw_limit = request.query_params.get("limit", "20")
        if not raw_limit.isascii() or not raw_limit.isdigit() or not 1 <= int(raw_limit) <= 50:
            raise ContentError("조회 개수는 1–50입니다.", field="limit")
        limit = int(raw_limit)
        terms = query_terms(request.query_params.get("q", "")) if self.search else []
        identity = {"theme": theme, "tag": normalize(tag), "author": request.user.pk if author else None,
                    "terms": terms, "search": self.search, "limit": limit}
        anchor, boundary = timezone.now(), None
        cursor = request.query_params.get("cursor")
        if cursor:
            try:
                if len(cursor) > 4096:
                    raise ValueError
                saved = signing.loads(cursor, salt="photo-content-cursor", max_age=3600)
                anchor = parse_datetime(saved["anchor"])
                boundary = (parse_datetime(saved["created"]), saved["id"])
                if saved["query"] != identity or not anchor or not timezone.is_aware(anchor) or not boundary[0] or not timezone.is_aware(boundary[0]) or type(boundary[1]) is not int:
                    raise ValueError
            except (signing.BadSignature, ValueError, KeyError, TypeError):
                raise ContentError("검색 조건에 맞는 다음 페이지를 다시 요청하세요.", field="cursor") from None
        posts = public_posts().filter(created_date__lte=anchor, published_date__lte=anchor)
        posts = filter_content(posts, theme=theme, tag=tag, terms=terms, author=request.user if author else None)
        if boundary:
            posts = posts.filter(Q(created_date__lt=boundary[0]) | Q(created_date=boundary[0], pk__lt=boundary[1]))
        if terms:
            match_filter = Q()
            for term in terms:
                match_filter |= Q(norm_text__contains=term) | Q(compact_text__contains=term.replace(" ", ""))
            posts = posts.prefetch_related(Prefetch("content__lines", queryset=PhotoTextLine.objects.filter(match_filter), to_attr="matched_lines"))
        rows = list(posts.order_by("-created_date", "-id")[:limit+1])
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit-1]
            next_cursor = signing.dumps({"query": identity, "anchor": anchor.isoformat(), "created": last.created_date.isoformat(), "id": last.pk}, salt="photo-content-cursor", compress=True)
        results = []
        for post in rows[:limit]:
            item = {"post": PostSerializer(post, context={"request": request}).data,
                    "content": content_payload(post, summary=True)}
            if self.search:
                content = post.content
                candidates = content.matched_lines
                matched_ids = set(matching_line_ids([line_payload(line) for line in candidates], terms))
                matches = [line for line in candidates if str(line.line_id) in matched_ids]
                item.update(content_revision=content.revision, image_sha256=content.image_sha256,
                            matched_lines=[line_payload(line) for line in matches[:10]], more_matches=max(0, len(matches)-10))
            results.append(item)
        return Response({"results": results, "next_cursor": next_cursor})


class PhotoTextSearch(ContentPosts):
    search = True
