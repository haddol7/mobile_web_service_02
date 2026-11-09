"""Owner-scoped conversation state in the existing private storage directory."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

from django.conf import settings
from rest_framework.exceptions import APIException, NotFound, ValidationError


class ChatUnavailable(APIException):
    status_code = 503
    default_detail = "대화 기록을 불러오지 못했습니다. 잠시 후 다시 시도해주세요."


def stamp():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    path = Path(getattr(settings, "HISTORY_CHAT_ROOT", "") or settings.HISTORY_MEDIA_ROOT) / ".question-chats.sqlite3"
    db = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(descriptor)
        db = sqlite3.connect(path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
          CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, owner INTEGER NOT NULL, title TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS chat_owner_time ON conversations(owner,updated_at);
          CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT, conversation TEXT NOT NULL REFERENCES conversations(id),
            request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, question TEXT NOT NULL,
            parameters TEXT NOT NULL, state TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL,
            UNIQUE(conversation,request_id));
        """)
        yield db
    except (sqlite3.Error, OSError, ValueError, UnicodeError):
        raise ChatUnavailable() from None
    finally:
        if db is not None:
            db.close()


def conversation(db, owner, key):
    try:
        key = str(UUID(str(key)))
    except ValueError:
        raise NotFound() from None
    row = db.execute("SELECT * FROM conversations WHERE id=? AND owner=?", (key, owner)).fetchone()
    if row is None:
        raise NotFound()
    return row


def list_chats(owner, offset=0):
    with connection() as db:
        rows = db.execute("""SELECT c.*,COUNT(t.id) AS turn_count FROM conversations c
            LEFT JOIN turns t ON t.conversation=c.id WHERE c.owner=?
            GROUP BY c.id ORDER BY c.updated_at DESC,c.id LIMIT 21 OFFSET ?""", (owner, offset)).fetchall()
        return {"results": [dict(row) for row in rows[:20]],
                "next_offset": offset+20 if len(rows)>20 else None}


def create_chat(owner):
    key, now = str(uuid4()), stamp()
    with connection() as db:
        db.execute("INSERT INTO conversations VALUES(?,?,?,?,?)", (key, owner, "새 대화", now, now))
    return {"id": key, "title": "새 대화", "created_at": now, "updated_at": now, "turn_count": 0}


def read_chat(owner, key, before=None):
    with connection() as db:
        chat = conversation(db, owner, key)
        rows = db.execute("SELECT * FROM turns WHERE conversation=? AND id<? ORDER BY id DESC LIMIT 31",
                          (chat["id"], before if before is not None else 9223372036854775807)).fetchall()
        latest = db.execute("SELECT parameters FROM turns WHERE conversation=? ORDER BY id DESC LIMIT 1", (chat["id"],)).fetchone()
        turns = [{"id": row["id"], "request_id": row["request_id"], "question": row["question"],
                  "state": row["state"], "created_at": row["created_at"],
                  "result": json.loads(row["result"]) if row["result"] else None} for row in reversed(rows[:30])]
        return {"id": chat["id"], "title": chat["title"], "turns": turns,
                "scope": json.loads(latest["parameters"]) if latest else {},
                "next_before": rows[29]["id"] if len(rows)>30 else None}


def reserve(owner, key, request_id, question, parameters):
    try:
        request_id = str(UUID(str(request_id)))
    except ValueError:
        raise ValidationError("질문 요청 번호를 확인해주세요.") from None
    raw = json.dumps(parameters, ensure_ascii=False, sort_keys=True)
    fingerprint = hashlib.sha256((question+"\n"+raw).encode()).hexdigest()
    with connection() as db:
        chat = conversation(db, owner, key)
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT * FROM turns WHERE conversation=? AND request_id=?", (chat["id"], request_id)).fetchone()
        if old:
            db.commit()
            if old["fingerprint"] != fingerprint:
                raise ValidationError("같은 요청 번호로 질문 내용을 변경할 수 없습니다.")
            if old["state"] == "complete":
                return old["id"], json.loads(old["result"])
            error = APIException("이미 처리 중이거나 전송 결과 확인이 필요한 질문입니다. 대화 기록을 확인해주세요.")
            error.status_code = 409
            raise error
        now = stamp()
        turn = db.execute("INSERT INTO turns(conversation,request_id,fingerprint,question,parameters,state,created_at) VALUES(?,?,?,?,?,'pending',?)",
                          (chat["id"], request_id, fingerprint, question, raw, now))
        db.execute("UPDATE conversations SET title=CASE WHEN title='새 대화' THEN ? ELSE title END,updated_at=? WHERE id=?",
                   (" ".join(question.split())[:36], now, chat["id"]))
        db.commit()
        return turn.lastrowid, None


def finish(owner, key, turn_id, result=None):
    raw = json.dumps(result, ensure_ascii=False, allow_nan=False) if result is not None else None
    if raw and len(raw.encode()) > 1024*1024:
        raise ChatUnavailable()
    with connection() as db:
        chat = conversation(db, owner, key)
        db.execute("UPDATE turns SET state=?,result=? WHERE id=? AND conversation=?",
                   ("complete" if raw else "failed", raw, turn_id, chat["id"]))
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (stamp(), chat["id"]))


def previous_context(owner, key, current_turn):
    with connection() as db:
        chat = conversation(db, owner, key)
        rows = db.execute("SELECT question,result FROM turns WHERE conversation=? AND id<? AND state='complete' ORDER BY id DESC LIMIT 3",
                          (chat["id"], current_turn)).fetchall()
        messages = []
        for row in reversed(rows):
            result = json.loads(row["result"])
            reply = result["llm"].get("text") or result["answer"]
            messages += [{"role": "user", "content": row["question"][:400]},
                         {"role": "assistant", "content": reply[:1600]}]
        latest = json.loads(rows[0]["result"]) if rows else {}
        return messages, [str(item["session_id"]) for item in latest.get("evidence", [])]
