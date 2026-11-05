"""Session information for the single-owner photo blog."""
from django.middleware.csrf import get_token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .ownership import is_blog_owner, is_blog_admin

class AuthMe(APIView):
    permission_classes = (AllowAny,)
    def get(self, request):
        user = request.user
        response = Response({"user": {"id": user.pk, "username": user.username} if user.is_authenticated else None,
                             "can_publish": is_blog_owner(user), "can_manage_all": is_blog_admin(user), "csrf_token": get_token(request)})
        response["Cache-Control"] = "no-store"
        return response
