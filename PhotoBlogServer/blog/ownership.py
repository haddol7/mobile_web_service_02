"""One configured publisher; existing accounts remain readable but cannot publish."""
from django.conf import settings
from django.core.exceptions import PermissionDenied

def is_blog_owner(user):
    return bool(user.is_authenticated and user.is_active and user.username == settings.BLOG_OWNER_USERNAME)

def is_blog_admin(user):
    return bool(is_blog_owner(user) and user.is_staff and user.is_superuser)

def can_manage_post(user, post):
    return is_blog_owner(user) and (post.author_id == user.pk or is_blog_admin(user))

def require_blog_owner(user):
    if not is_blog_owner(user):
        raise PermissionDenied("운영자만 사진글을 작성하거나 변경할 수 있습니다.")

def owner_context(request):
    return {"is_blog_owner": is_blog_owner(request.user)}
