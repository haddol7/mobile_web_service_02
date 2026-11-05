"""Writes sharing the existing per-owner SQLite lock and transaction owner."""
import hashlib

from django.core.exceptions import PermissionDenied
from django.db import transaction
from PIL import Image

from .content_rules import ContentError, validate_packet
from .models import PhotoContent, PhotoTag, PhotoTextLine, Post


def image_fingerprint(image):
    with image.open("rb") as source:
        digest = hashlib.sha256()
        for chunk in source.chunks():
            digest.update(chunk)
        source.seek(0)
        with Image.open(source) as decoded:
            size = decoded.size
    return digest.hexdigest(), size[0], size[1]


def stale(revision):
    raise ContentError("사진이나 내용이 변경되었습니다. 최신 내용을 확인하세요.", code="stale_content",
                       status=409, revision=revision)


def save_content_locked(post, packet, *, require_revision=True):
    """Caller owns atomic + owner write intent; this function never commits files."""
    clean = validate_packet(packet)
    current = PhotoContent.objects.filter(post=post).first()
    revision = current.revision if current else 0
    if require_revision and "expected_revision" not in clean:
        raise ContentError("내용 버전이 필요합니다.", field="expected_revision")
    if clean.get("expected_revision", 0) != revision:
        stale(revision)
    digest, width, height = image_fingerprint(post.image)
    if (clean["image_sha256"], clean["width"], clean["height"]) != (digest, width, height):
        raise ContentError("분석 결과가 현재 게시 사진과 다릅니다.", code="image_mismatch", field="image_sha256")
    values = {k: clean[k] for k in ("schema_version", "image_sha256", "width", "height", "model_versions",
                                    "mapping_version", "theme_status", "theme", "theme_origin", "ocr_status")}
    if current is None:
        current = PhotoContent.objects.create(post=post, revision=1, **values)
    else:
        from django.utils import timezone
        changed = PhotoContent.objects.filter(pk=current.pk, revision=revision).update(
            revision=revision+1, updated_at=timezone.now(), **values)
        if changed != 1:
            stale(PhotoContent.objects.get(pk=current.pk).revision)
        current.refresh_from_db()
        current.tags.all().delete()
        current.lines.all().delete()
    PhotoTag.objects.bulk_create([PhotoTag(content=current, position=i, **tag) for i, tag in enumerate(clean["tags"])])
    PhotoTextLine.objects.bulk_create([PhotoTextLine(content=current, position=i, **line) for i, line in enumerate(clean["lines"])])
    return current


def invalidate_content_locked(post):
    current = PhotoContent.objects.filter(post=post).first()
    if current is None:
        return
    digest, width, height = image_fingerprint(post.image)
    # Preserve a monotonic revision even when the replacement file has identical bytes.
    current.revision += 1
    current.image_sha256, current.width, current.height = digest, width, height
    current.theme, current.theme_status, current.theme_origin = None, "not_analyzed", "unclassified"
    current.ocr_status, current.model_versions, current.mapping_version = "not_analyzed", {}, ""
    current.save()
    current.tags.all().delete()
    current.lines.all().delete()


def update_content(*, actor, post_id, packet):
    from .ownership import require_blog_owner, can_manage_post
    require_blog_owner(actor)
    validate_packet(packet)
    from .services import lock_owner
    with transaction.atomic():
        lock_owner(actor.pk)
        post = Post.objects.get(pk=post_id)
        if not can_manage_post(actor, post):
            raise PermissionDenied("자신의 사진글만 변경할 수 있습니다.")
        return save_content_locked(post, packet)

