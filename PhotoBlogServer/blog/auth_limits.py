"""Protect the existing website, admin and token login without changing their APIs."""
import ipaddress
import json
import math

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

from .request_limits import AuthBlocked, LimitStoreUnavailable, reserve_auth, finish_auth


def mark_login(sender, request, **kwargs):
    if request is not None:
        request._limited_login_success = True


user_logged_in.connect(mark_login, dispatch_uid="blog.limited-login-success", weak=False)


def client_ip(request):
    # PythonAnywhere overwrites X-Real-IP. Local/direct deployments ignore it.
    value = request.META.get("HTTP_X_REAL_IP") if settings.TRUST_PYTHONANYWHERE_REAL_IP else None
    value = value or request.META.get("REMOTE_ADDR", "")
    try:
        address = ipaddress.ip_address(value)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return str(address)
    except ValueError:
        return "unknown"


class LoginLimitMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if request.method != "POST" or not match or match.url_name not in ("login", "api_token_auth"):
            return None
        token = match.url_name == "api_token_auth"
        try:
            if request.content_type == "application/json":
                body = request.body
                data = json.loads(body) if len(body) <= 8192 else {}
            else:
                data = request.POST
            username = data.get("username", "") if isinstance(data, dict) or hasattr(data, "get") else ""
            username = username if isinstance(username, str) else ""
        except (ValueError, UnicodeError):
            username = ""
        try:
            request._login_limit_keys = reserve_auth(client_ip(request), username)
            request._login_limit_token = token
        except AuthBlocked as error:
            wait = error.wait
            message = f"로그인을 여러 번 실패했습니다. 약 {math.ceil(wait/60)}분 후 다시 시도해주세요."
            if token:
                response = JsonResponse({"detail": message, "code": "login_rate_limited", "retry_after": wait}, status=429)
            else:
                response = render(request, "registration/rate_limited.html", {"message": message, "retry_url": request.get_full_path()}, status=429)
            response["Retry-After"] = str(wait)
            response["Cache-Control"] = "private, no-store"
            return response
        except LimitStoreUnavailable:
            return self.unavailable(request, token)
        return None

    @staticmethod
    def unavailable(request, token):
        message = "로그인 보호 상태를 확인하지 못했습니다. 잠시 후 다시 시도해주세요."
        response = (JsonResponse({"detail": message}, status=503) if token else
                    render(request, "registration/rate_limited.html", {"message": message, "retry_url": request.get_full_path()}, status=503))
        response["Cache-Control"] = "private, no-store"
        response["Retry-After"] = "60"
        return response

    def process_response(self, request, response):
        keys = getattr(request, "_login_limit_keys", None)
        if keys:
            success = (getattr(request, "_limited_login_success", False)
                       or (request._login_limit_token and response.status_code == 200))
            try:
                finish_auth(keys, success=success, server_error=response.status_code >= 500)
            except LimitStoreUnavailable:
                # Do not replace an already successful login; preflight fails closed next time.
                pass
        return response
