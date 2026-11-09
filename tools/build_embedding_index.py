"""WSL operator tool. Dry-run by default; paid calls require explicit, bounded approval."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PhotoBlogServer"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photoblog.settings")
import django
django.setup()
from blog.history_embeddings import (MAX_BATCH, MAX_BATCH_BYTES, MAX_DOCUMENTS, MAX_TEXT_BYTES, EmbeddingError,
    atomic_json, digest, embed_texts, header, normalize_query, query_key, read_index, read_queries, vector)


def batches(rows):
    pending, size = [], 0
    for row in rows:
        length = len(row[2].encode("utf-8"))
        if pending and (len(pending) >= MAX_BATCH or size + length > MAX_BATCH_BYTES):
            yield pending
            pending, size = [], 0
        pending.append(row)
        size += length
    if pending:
        yield pending


def prepare(corpus, output, questions):
    if not isinstance(corpus, dict) or any(corpus.get(k) != v for k, v in header().items()):
        raise EmbeddingError("Invalid corpus format.")
    docs = corpus.get("documents")
    if not isinstance(docs, list) or len(docs) > MAX_DOCUMENTS:
        raise EmbeddingError("Invalid corpus size.")
    ids = set()
    for doc in docs:
        if not isinstance(doc, dict) or not isinstance(doc.get("id"), str) or doc["id"] in ids:
            raise EmbeddingError("Invalid corpus document.")
        try:
            UUID(doc["id"])
        except ValueError:
            raise EmbeddingError("Invalid corpus document.") from None
        text = doc.get("text")
        if not isinstance(text, str) or not text.strip() or len(text.encode()) > MAX_TEXT_BYTES or doc.get("sha256") != digest(text):
            raise EmbeddingError("Invalid corpus text or fingerprint.")
        ids.add(doc["id"])
    if len(questions) > 16 or any(not isinstance(q, str) or not q.strip() or len(q) > 400 for q in questions):
        raise EmbeddingError("Invalid seed questions.")
    previous = read_index(output) or {}
    cache_file = Path(output).with_name(".semantic-query-cache.json")
    queries = read_queries(cache_file)
    pending = []
    for doc in docs:
        if doc["id"] not in previous or previous[doc["id"]]["sha256"] != doc["sha256"]:
            pending.append(("document", doc["id"], doc["text"]))
    for question in dict.fromkeys(normalize_query(q) for q in questions):
        if query_key(question) not in queries:
            pending.append(("query", query_key(question), question))
    plan = {**header(), "documents": len(docs), "changed_documents": sum(row[0] == "document" for row in pending),
            "new_seed_questions": sum(row[0] == "query" for row in pending),
            "api_requests_required": len(list(batches(pending))),
            "input_utf8_bytes": sum(len(row[2].encode("utf-8")) for row in pending),
            "images_or_face_vectors_sent": False, "llm_generation_calls": 0}
    return plan, docs, previous, queries, pending, cache_file


def build(corpus, output, questions=(), *, apply=False, allow_paid_api=False, max_api_calls=0, audit_path=None):
    plan, docs, previous, queries, pending, cache_file = prepare(corpus, output, questions)
    if not apply:
        return {**plan, "dry_run": True, "actual_api_calls": 0}
    required = plan["api_requests_required"]
    if required and (allow_paid_api is not True or type(max_api_calls) is not int or max_api_calls < required):
        raise EmbeddingError("Review the dry-run plan and obtain approval before enabling the required API calls.")
    rows = dict(previous)
    usage = {"prompt_tokens": 0, "total_tokens": 0}
    calls = 0
    for batch in batches(pending):
        if calls >= max_api_calls:
            raise EmbeddingError("Approved API call budget is exhausted.")
        calls += 1
        if audit_path:
            atomic_json(audit_path, {**plan, "dry_run": False, "phase": "request_started",
                        "requests_attempted": calls, "pass": False})
        try:
            result = embed_texts([item[2] for item in batch], approved=True)
        except EmbeddingError as error:
            if audit_path:
                atomic_json(audit_path, {**plan, "dry_run": False, "phase": "request_failed",
                            "actual_api_calls": calls - 1 + error.api_requests, "pass": False,
                            "automatic_retry": False})
            raise
        for key in usage:
            usage[key] += result["usage"].get(key, 0)
        for (kind, key, text), embedded in zip(batch, result["vectors"]):
            if kind == "document":
                rows[key] = {"sha256": digest(text), "vector": vector(embedded)}
            else:
                queries[key] = vector(embedded)
    generated = datetime.now(timezone.utc).isoformat()
    index = {**header(), "created_at": generated,
             "documents": [{"id": doc["id"], **rows[doc["id"]]} for doc in docs]}
    atomic_json(cache_file, {**header(), "queries": dict(list(queries.items())[-256:])})
    atomic_json(output, index)
    return {**plan, "dry_run": False, "actual_api_calls": calls, "usage": usage,
            "created_at": generated, "index_sha256": __import__("hashlib").sha256(Path(output).read_bytes()).hexdigest()}


def main():
    if not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in the WSL project virtualenv.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence/private/embeddings/.semantic-index.json")
    parser.add_argument("--seed-query", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--max-api-calls", type=int, default=0)
    args = parser.parse_args()
    destination = ROOT / "evidence/history/embedding-build.json"
    try:
        result = build(json.loads(args.corpus.read_text()), args.output, args.seed_query, apply=args.apply,
                       allow_paid_api=args.allow_paid_api, max_api_calls=args.max_api_calls, audit_path=destination)
    except EmbeddingError as error:
        raise SystemExit(str(error)) from None
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
