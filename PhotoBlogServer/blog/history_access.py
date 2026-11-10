"""Public observation access with operator writes and isolated visitor chats."""
import secrets

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .ownership import is_blog_owner


class ReadOrHistoryOwner(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_blog_owner(request.user)


class PublicQuestionPermission(BasePermission):
    def has_permission(self, request, view):
        if request.method not in SAFE_METHODS and request.auth is None:
            SessionAuthentication().enforce_csrf(request)
        return True


def conversation_owner(request):
    if request.user.is_authenticated and request.user.is_active:
        return request.user.pk
    session = request.session
    owner = session.get("history_visitor")
    if type(owner) is not int or not -(2**62) <= owner < 0:
        owner = -(secrets.randbits(62) or 1)
        session["history_visitor"] = owner
    return owner
