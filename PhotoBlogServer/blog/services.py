"""Transactional photo writes with SQLite write intent before reading revisions."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import Post
from .ownership import require_blog_owner, can_manage_post

def lock_owner(owner_id):
    get_user_model().objects.filter(pk=owner_id).update(last_login=F("last_login"))


def remove_uncommitted_upload(post, original_name):
    """Remove only the new file when a transaction owned here rolls back."""
    image = post.image
    if image and image._committed and image.name != original_name:
        image.storage.delete(image.name)


def create_post(*, actor, values):
    require_blog_owner(actor)
    packet = values.get("photo_content")
    if packet is not None:
        from .content_rules import validate_packet
        validate_packet(packet)
    post = Post(author_id=actor.pk, published_date=timezone.now())
    for field in ("title", "text", "image"):
        if field in values:
            setattr(post, field, values[field])
    committed = False

    def mark_committed():
        nonlocal committed
        committed = True

    try:
        with transaction.atomic():
            transaction.on_commit(mark_committed)
            lock_owner(actor.pk)
            post.save()
            if packet is not None:
                from .content_services import save_content_locked
                save_content_locked(post, packet, require_revision=False)
        return post
    except Exception:
        if not committed:
            remove_uncommitted_upload(post, None)
        raise


def update_post(*, actor, post_id, values):
    require_blog_owner(actor)
    packet = values.get("photo_content")
    if packet is not None:
        from .content_rules import validate_packet
        validate_packet(packet)
    post, old_name = None, None
    committed = False

    def mark_committed():
        nonlocal committed
        committed = True

    try:
        with transaction.atomic():
            transaction.on_commit(mark_committed)
            lock_owner(actor.pk)
            post = Post.objects.get(pk=post_id)
            if not can_manage_post(actor, post):
                raise PermissionDenied("자신의 게시글만 변경할 수 있습니다.")
            old_name = post.image.name
            for field in ("title", "text", "image"):
                if field in values:
                    setattr(post, field, values[field])
            post.save()
            if packet is not None:
                from .content_services import save_content_locked
                save_content_locked(post, packet)
            elif post.image.name != old_name:
                from .content_services import invalidate_content_locked
                invalidate_content_locked(post)
        return post
    except Exception:
        if not committed and post is not None and old_name is not None:
            remove_uncommitted_upload(post, old_name)
        raise


def delete_post(*, actor, post_id):
    require_blog_owner(actor)
    with transaction.atomic():
        lock_owner(actor.pk)
        post = Post.objects.get(pk=post_id)
        if not can_manage_post(actor, post):
            raise PermissionDenied("자신의 게시글만 삭제할 수 있습니다.")
        post.delete()

