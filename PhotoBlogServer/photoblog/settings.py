"""One Django/SQLite application, compatible with PythonAnywhere free hosting."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from photoblog.llm_config import load_llm_config

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("1", "true", "yes")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is required when DJANGO_DEBUG=false.")
    SECRET_KEY = "django-insecure-common02-local-development-only"

ALLOWED_HOSTS = [
    item.strip()
    for item in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,10.0.2.2,daejinha.pythonanywhere.com"
    ).split(",")
    if item.strip()
]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "rest_framework.authtoken", "blog.apps.BlogConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "blog.auth_limits.LoginLimitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "photoblog.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
                "blog.ownership.owner_context", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "photoblog.wsgi.application"
ASGI_APPLICATION = "photoblog.asgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DJANGO_DB_PATH", BASE_DIR / "db.sqlite3"),
    "OPTIONS": {"timeout": 20},
}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
BLOG_OWNER_USERNAME = os.environ.get("BLOG_OWNER_USERNAME", "daejinha")
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "dashboard"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))
HISTORY_MEDIA_ROOT = Path(os.environ.get("HISTORY_MEDIA_ROOT", MEDIA_ROOT.resolve().parent / "private_tracking"))
# Optional remote generation. Retrieval and exact aggregates work without an API key.
_history_llm = load_llm_config()
HISTORY_LLM_PROVIDER = _history_llm["provider"]
HISTORY_LLM_API_KEY = _history_llm["api_key"]
HISTORY_LLM_MODEL = _history_llm["model"]
HISTORY_EMBEDDING_API_KEY = os.environ.get("HISTORY_EMBEDDING_API_KEY", _history_llm["api_key"] if _history_llm["provider"] == "openai" else "")
HISTORY_EMBEDDING_INDEX = Path(os.environ.get("HISTORY_EMBEDDING_INDEX", HISTORY_MEDIA_ROOT / ".semantic-index.json"))
HISTORY_CHAT_ROOT = os.environ.get("HISTORY_CHAT_ROOT", "")
SECURITY_STATE_ROOT = os.environ.get("SECURITY_STATE_ROOT", "")
TRUST_PYTHONANYWHERE_REAL_IP = os.environ.get("DJANGO_TRUST_X_REAL_IP", "false").lower() == "true"
LOGIN_PAIR_FAILURE_LIMIT = 5
LOGIN_IP_FAILURE_LIMIT = 20
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60


def daily_limit(name, default):
    value = os.environ.get(name, str(default))
    if not value.isascii() or not value.isdigit() or not 0 <= int(value) <= 10000:
        raise ImproperlyConfigured(name + " must be an integer between 0 and 10000.")
    return int(value)


HISTORY_LLM_DAILY_LIMIT = daily_limit("HISTORY_LLM_DAILY_LIMIT", 3)
HISTORY_EMBEDDING_DAILY_LIMIT = daily_limit("HISTORY_EMBEDDING_DAILY_LIMIT", 100)
del _history_llm
# Limit text/form overhead separately from photo bytes. Photo validation enforces 5 MiB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    # Lecture ch05's Android sync reads a JSONArray, not a paginated object.
    "DEFAULT_PAGINATION_CLASS": None,
}
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

