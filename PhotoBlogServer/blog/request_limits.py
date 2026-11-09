"""Persistent, atomic limits shared by WSGI workers, without external services."""
from contextlib import contextmanager
from datetime import datetime, timedelta, time as day_time
import hashlib
import hmac
import math
import os
from pathlib import Path
import sqlite3
import stat
import time
import unicodedata
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


class LimitStoreUnavailable(Exception):
    pass


class AuthBlocked(Exception):
    def __init__(self, wait):
        self.wait = max(1, math.ceil(wait))


class DailyLimit(Exception):
    def __init__(self, kind, used, limit, reset):
        label = "AI 설명" if kind == "generation" else "의미 검색"
        self.data = {"status": "daily_limit", "limit": limit, "used": used,
                     "resets_at": reset.isoformat(),
                     "message": f"오늘 {label} 사용 한도에 도달했습니다. 한국 시간 자정 이후 다시 사용할 수 있습니다. 저장된 기록은 계속 조회할 수 있습니다."}


def state_path():
    return Path(settings.SECURITY_STATE_ROOT or settings.HISTORY_MEDIA_ROOT) / ".request-limits.sqlite3"


@contextmanager
def connection():
    db = None
    try:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
                raise OSError("Unsafe limit store")
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        db = sqlite3.connect(path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.executescript("""
          CREATE TABLE IF NOT EXISTS auth_attempts (
            key TEXT PRIMARY KEY, started REAL NOT NULL, attempts INTEGER NOT NULL,
            blocked_until REAL NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS daily_usage (
            day TEXT NOT NULL, kind TEXT NOT NULL, used INTEGER NOT NULL,
            PRIMARY KEY(day,kind));
        """)
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except (sqlite3.Error, OSError, ValueError):
        raise LimitStoreUnavailable() from None
    finally:
        if db is not None:
            db.close()


def digest(label, value):
    return hmac.new(settings.SECRET_KEY.encode(), (label + ":" + value).encode(), hashlib.sha256).hexdigest()


def auth_keys(address, username):
    username = unicodedata.normalize("NFKC", username.strip()).casefold()[:150]
    return (digest("login-pair", address + "\0" + username), digest("login-ip", address))


def reserve_auth(address, username):
    """Count in-flight attempts too, so simultaneous failures cannot race the cap."""
    keys = auth_keys(address, username)
    limits = (settings.LOGIN_PAIR_FAILURE_LIMIT, settings.LOGIN_IP_FAILURE_LIMIT)
    now, window = time.time(), settings.LOGIN_FAILURE_WINDOW_SECONDS
    with connection() as db:
        db.execute("DELETE FROM auth_attempts WHERE started<=? AND blocked_until<=?", (now-window, now))
        for key, limit in zip(keys, limits):
            row = db.execute("SELECT * FROM auth_attempts WHERE key=?", (key,)).fetchone()
            if row and row["blocked_until"] > now:
                raise AuthBlocked(row["blocked_until"] - now)
        for key, limit in zip(keys, limits):
            row = db.execute("SELECT * FROM auth_attempts WHERE key=?", (key,)).fetchone()
            count = row["attempts"] + 1 if row else 1
            started = row["started"] if row else now
            blocked = now + window if count >= limit else 0
            db.execute("INSERT OR REPLACE INTO auth_attempts VALUES(?,?,?,?)", (key, started, count, blocked))
    return keys


def finish_auth(keys, *, success=False, server_error=False):
    # A success resets its own account/IP pair, not other failed accounts on the IP.
    if not (success or server_error):
        return
    with connection() as db:
        for index, key in enumerate(keys):
            if success and index == 0:
                db.execute("DELETE FROM auth_attempts WHERE key=?", (key,))
            else:
                limit = settings.LOGIN_PAIR_FAILURE_LIMIT if index == 0 else settings.LOGIN_IP_FAILURE_LIMIT
                db.execute("""UPDATE auth_attempts SET
                    blocked_until=CASE WHEN attempts-1<? THEN 0 ELSE blocked_until END,
                    attempts=MAX(0,attempts-1) WHERE key=?""", (limit, key))


def consume_api(kind):
    """Reserve one real outbound attempt before transport, including failed attempts."""
    limits = {"generation": settings.HISTORY_LLM_DAILY_LIMIT,
              "embedding": settings.HISTORY_EMBEDDING_DAILY_LIMIT}
    if kind not in limits:
        raise ValueError("Unknown API usage kind")
    day = timezone.now().astimezone(ZoneInfo("Asia/Seoul")).date()
    reset = datetime.combine(day + timedelta(days=1), day_time.min, tzinfo=ZoneInfo("Asia/Seoul"))
    with connection() as db:
        db.execute("DELETE FROM daily_usage WHERE day<?", ((day-timedelta(days=7)).isoformat(),))
        row = db.execute("SELECT used FROM daily_usage WHERE day=? AND kind=?", (day.isoformat(), kind)).fetchone()
        used = row["used"] if row else 0
        if used >= limits[kind]:
            raise DailyLimit(kind, used, limits[kind], reset)
        db.execute("""INSERT INTO daily_usage VALUES(?,?,1)
            ON CONFLICT(day,kind) DO UPDATE SET used=used+1""", (day.isoformat(), kind))


def usage_status():
    day = timezone.now().astimezone(ZoneInfo("Asia/Seoul")).date()
    reset = datetime.combine(day + timedelta(days=1), day_time.min, tzinfo=ZoneInfo("Asia/Seoul"))
    values = {}
    with connection() as db:
        for kind, limit in (("generation", settings.HISTORY_LLM_DAILY_LIMIT),
                            ("embedding", settings.HISTORY_EMBEDDING_DAILY_LIMIT)):
            row = db.execute("SELECT used FROM daily_usage WHERE day=? AND kind=?", (day.isoformat(), kind)).fetchone()
            used = row["used"] if row else 0
            values[kind] = {"limit": limit, "used": used, "remaining": max(0, limit-used)}
    return {"day": day.isoformat(), "timezone": "Asia/Seoul", "resets_at": reset.isoformat(),
            "daily": values, "login": {"pair_failures": settings.LOGIN_PAIR_FAILURE_LIMIT,
                "ip_failures": settings.LOGIN_IP_FAILURE_LIMIT, "wait_seconds": settings.LOGIN_FAILURE_WINDOW_SECONDS,
                "trusted_platform_ip": settings.TRUST_PYTHONANYWHERE_REAL_IP}}
