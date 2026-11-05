from rest_framework.permissions import BasePermission, SAFE_METHODS


from .ownership import is_blog_owner, can_manage_post


class IsPostOwnerOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_blog_owner(request.user)

    """Public photographs may be read; only their author may change them."""
    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or can_manage_post(request.user, obj)


