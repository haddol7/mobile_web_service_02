"""Private text embeddings with explicit paid-call opt-in; no automatic indexing."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone as django_timezone

MAX_DOCUMENTS = 512
MAX_BATCH = 64
MAX_TEXT_BYTES = 6000
MAX_BATCH_BYTES = 128000
MAX_INDEX_BYTES = 16 * 1024 * 1024
MODEL = "text-embedding-3-small"
DIMENSIONS = 512

# Small metadata vocabulary for hybrid retrieval. These are title terms, not inferred visual labels.
TITLE_CONCEPTS = (
    ("출국", "출발", "떠나", "떠나는", "depart", "boarding", "비행기를타", "비행기타"),
    ("입국", "도착", "arrival", "arriv", "착륙"),
    ("기자", "브리핑", "보도", "언론", "press", "briefing"),
    ("안보", "나토", "nato", "security", "군사", "국방"),
    ("회의", "회담", "정상", "논의", "summit", "meeting"),
    ("보행", "걸어", "걷", "통로", "pedestrian", "walking"),
    ("연설", "발언", "말하", "speech", "address"),
    ("행사", "선서", "서명", "ceremony", "signing", "signed"),
)


def title_match(question, title):
    def features(text):
        compact = "".join(re.findall(r"[a-z가-힣]+", normalize_query(text).casefold()))
        for common in ("영상", "장면", "기록", "사진", "찾아줘", "보여줘", "알려줘"):
            compact = compact.replace(common, "")
        grams = {compact[i:i+2] for i in range(len(compact)-1)}
        concepts = {i for i, words in enumerate(TITLE_CONCEPTS) if any(word in compact for word in words)}
        return grams, concepts
    query_grams, query_concepts = features(question)
    title_grams, title_concepts = features(title)
    lexical = 2 * len(query_grams & title_grams) / max(1, len(query_grams) + len(title_grams))
    concepts = len(query_concepts & title_concepts) / max(1, len(query_concepts))
    return max(lexical, concepts)


class EmbeddingError(Exception):
    """Generic failure; provider payloads and credentials must not escape."""
    def __init__(self, message, *, attempted=False):
        super().__init__(message)
        self.api_requests = int(attempted)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_query(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def vector(values):
    try:
        if not isinstance(values, list) or len(values) != DIMENSIONS or any(type(v) not in (int, float) for v in values):
            raise ValueError
        values = [float(v) for v in values]
        norm = math.hypot(*values)
        if not all(math.isfinite(v) for v in values) or not math.isfinite(norm) or norm < 1e-12:
            raise ValueError
        return [value / norm for value in values]
    except (TypeError, ValueError, OverflowError):
        raise EmbeddingError("Invalid embedding vector.") from None


def embed_texts(texts, *, approved=False):
    # Both the operator indexing tool and each interactive request must opt in.
    if approved is not True:
        raise EmbeddingError("Paid embedding calls require explicit approval.")
    if (not isinstance(texts, list) or not 1 <= len(texts) <= MAX_BATCH or
            any(not isinstance(t, str) or not t.strip() or len(t.encode("utf-8")) > MAX_TEXT_BYTES for t in texts)):
        raise EmbeddingError("Embedding input exceeds the approved batch bounds.")
    if sum(len(t.encode("utf-8")) for t in texts) > MAX_BATCH_BYTES:
        raise EmbeddingError("Embedding input exceeds the approved batch bounds.")
    key = settings.HISTORY_EMBEDDING_API_KEY
    if not key or any(c.isspace() for c in key):
        raise EmbeddingError("Embedding service is not configured.")
    body = json.dumps({"model": MODEL, "dimensions": DIMENSIONS,
                       "encoding_format": "float", "input": texts}, ensure_ascii=False).encode()
    request = Request("https://api.openai.com/v1/embeddings", data=body,
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    try:
        # One attempt only. A timeout is never silently retried at the user's expense.
        with urlopen(request, timeout=20) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("model") != MODEL or not isinstance(result.get("data"), list) or len(result["data"]) != len(texts):
            raise ValueError
        ordered = {}
        for row in result["data"]:
            position = row["index"]
            if type(position) is not int or position not in range(len(texts)) or position in ordered:
                raise ValueError
            ordered[position] = vector(row["embedding"])
        usage = result.get("usage", {})
        if not isinstance(usage, dict):
            raise ValueError
        return {"vectors": [ordered[i] for i in range(len(texts))],
                "usage": {k: v for k, v in usage.items()
                          if k in ("prompt_tokens", "total_tokens") and type(v) is int and v >= 0}}
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError, EmbeddingError):
        raise EmbeddingError("Embedding request failed; no automatic retry was made.", attempted=True) from None


def documents(session_ids=None):
    """Describe stored metadata only. Never infer clothes, actions or capture dates from pixels."""
    from .models import TrackingSession, PersonTrack
    sessions = TrackingSession.objects.filter(frames__isnull=False).distinct().order_by("pk")
    if session_ids is not None:
        sessions = sessions.filter(pk__in=session_ids)
    if sessions.count() > MAX_DOCUMENTS:
        raise EmbeddingError("Embedding corpus exceeds the configured limit.")
    result = []
    for session in sessions:
        frames = session.frames.all()
        confirmed, candidates = set(), set()
        for track in PersonTrack.objects.filter(session=session).select_related("candidate", "confirmed"):
            if track.confirmed_id:
                confirmed.add(track.confirmed.display_name)
            elif track.candidate_id and not track.reviewed_at:
                candidates.add(track.candidate.display_name)
        days = sorted({django_timezone.localtime(value).date().isoformat()
                       for value in frames.exclude(observed_at=None).values_list("observed_at", flat=True)})
        analyses = sorted({django_timezone.localtime(value).date().isoformat()
                           for value in frames.values_list("processed_at", flat=True)})
        text = "\n".join([
            "영상 설명: " + session.source_label,
            "입력 종류: " + ("실시간 카메라" if session.source_kind == "live" else "저장 영상"),
            "확인된 인물: " + (", ".join(sorted(confirmed)[:20]) or "없음"),
            "미확인 얼굴 후보: " + (", ".join(sorted(candidates)[:20]) or "없음"),
            "확인된 촬영 날짜: " + (", ".join(days[:20]) or "미상"),
            "분석 날짜(촬영일과 구분): " + ", ".join(analyses[:20]),
            "저장된 관측 사진: " + str(frames.count()) + "장",
            "영상 설명 속 날짜는 확인된 촬영 시각을 대신하지 않습니다.",
        ])
        # A large profile collection is bounded explicitly rather than silently truncated.
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise EmbeddingError("A session document exceeds the configured text limit.")
        result.append({"id": str(session.pk), "text": text, "sha256": digest(text)})
    return result


def index_path():
    return Path(settings.HISTORY_EMBEDDING_INDEX)


def cache_path():
    return index_path().with_name(".semantic-query-cache.json")


def read_json(path):
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_INDEX_BYTES + 1)
        if len(raw) > MAX_INDEX_BYTES:
            raise ValueError
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeError):
        raise EmbeddingError("Private embedding storage is unavailable.") from None


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".semantic-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(data, target, ensure_ascii=False, allow_nan=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def header():
    return {"schema": 1, "model": MODEL, "dimensions": DIMENSIONS}


def read_index(path=None):
    value = read_json(path or index_path())
    if value is None:
        return None
    if any(value.get(k) != v for k, v in header().items()) or not isinstance(value.get("documents"), list):
        raise EmbeddingError("Embedding index uses an incompatible format.")
    if len(value["documents"]) > MAX_DOCUMENTS:
        raise EmbeddingError("Embedding index exceeds the configured limit.")
    mapped = {}
    for item in value["documents"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in mapped:
            raise EmbeddingError("Embedding index contains invalid documents.")
        mapped[item["id"]] = {"sha256": item.get("sha256"), "vector": vector(item.get("vector"))}
    return mapped


def query_key(question):
    return digest(MODEL + ":" + str(DIMENSIONS) + ":" + normalize_query(question))


def read_queries(path=None):
    value = read_json(path or cache_path())
    if value is None:
        return {}
    if any(value.get(k) != v for k, v in header().items()) or not isinstance(value.get("queries"), dict):
        raise EmbeddingError("Embedding query cache uses an incompatible format.")
    if len(value["queries"]) > 256:
        raise EmbeddingError("Embedding query cache exceeds the configured limit.")
    return {key: vector(row) for key, row in value["queries"].items()}


@contextmanager
def query_lock():
    path = cache_path().with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
    except (BlockingIOError, OSError):
        raise EmbeddingError("Another embedding query is in progress.") from None


def query_vector(question, *, allow_api=True):
    completed = False
    try:
        with query_lock():
            entries = read_queries()
            key = query_key(question)
            if key in entries:
                return entries[key], True
            if not allow_api:
                raise EmbeddingError("This verification request may only use cached query vectors.")
            result = embed_texts([normalize_query(question)], approved=True)
            completed = True
            entries[key] = result["vectors"][0]
            atomic_json(cache_path(), {**header(), "queries": dict(list(entries.items())[-256:])})
            return result["vectors"][0], False
    except EmbeddingError as error:
        if completed:
            error.api_requests = 1
        raise


def rank(question, frames, *, allow_api=True):
    """Filter first; skip paid requests when coverage is absent, stale or empty."""
    ids = set(str(key) for key in frames.order_by().values_list("session_id", flat=True).distinct())
    base = {"strategy": "semantic", "status": "unavailable", "scope": "condition_filtered",
            "api_requests": 0, "matched_sessions": 0}
    if not ids:
        return {**base, "status": "empty", "session_ids": []}
    try:
        stored = read_index()
        if stored is None:
            return {**base, "status": "index_missing"}
        current = documents(ids)
        missing = [doc for doc in current if doc["id"] not in stored or stored[doc["id"]]["sha256"] != doc["sha256"]]
        if missing:
            return {**base, "status": "index_stale", "missing_documents": len(missing)}
        query, cached = query_vector(question, allow_api=allow_api)
        titles = {doc["id"]: doc["text"].splitlines()[0].removeprefix("영상 설명: ") for doc in current}
        scores = []
        for key in ids:
            cosine = sum(a*b for a, b in zip(query, stored[key]["vector"]))
            lexical = title_match(question, titles[key])
            scores.append((.75 * cosine + .25 * lexical, key, cosine, lexical))
        scores.sort(key=lambda row: (-row[0], row[1]))
        selected = [row for row in scores if row[0] >= .30][:5]
        return {**base, "status": "ranked" if selected else "no_match", "scope": "semantic_top_5",
                "api_requests": 0 if cached else 1, "query_cache_hit": cached,
                "ranking": "embedding_title_hybrid_v2", "matched_sessions": len(selected),
                "session_ids": [key for score, key, cosine, lexical in selected],
                "matches": [{"session_id": key, "similarity": round(cosine, 6),
                             "title_match": round(lexical, 6), "rank_score": round(score, 6)}
                            for score, key, cosine, lexical in selected]}
    except EmbeddingError as error:
        return {**base, "api_requests": error.api_requests}
