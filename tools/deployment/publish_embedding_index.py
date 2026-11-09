"""Publish an approved index; all production verification is strictly cache-only."""
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

import requests
import pythonanywhere_auth as auth
from pythonanywhere_deploy import API, BASE, DOMAIN, HOME, SERVER, WORKSPACE

sys.path.insert(0, str(SERVER))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photoblog.settings")
import django
django.setup()
from blog.history_embeddings import read_index, read_queries, header, query_key


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    assert os.environ.get("WSL_DISTRO_NAME"), "Run in WSL"
    directory = WORKSPACE / "evidence/private/embeddings"
    index_file = directory / ".semantic-index.json"
    query_file = directory / ".semantic-query-cache.json"
    build = json.loads((WORKSPACE / "evidence/history/embedding-build.json").read_text())
    assert build["dry_run"] is False and build["index_sha256"] == sha(index_file.read_bytes())
    stored = read_index(index_file)
    seeds = read_queries(query_file)
    protocol = json.loads((WORKSPACE / "docs/testing/embedding-protocol.json").read_text())
    assert all(query_key(row["question"]) in seeds for row in protocol["queries"])
    api = API(auth.load_credentials())
    app = json.loads(auth.private_read(Path.home() / ".config/mobile-web-service/common02/edge-auth.json"))
    headers = {"Authorization": "Token " + app["token"]}
    origin = "https://" + DOMAIN
    corpus = requests.get(origin + "/api/v1/history/embedding-documents/", headers=headers, timeout=(5, 30))
    assert corpus.status_code == 200
    docs = corpus.json()["documents"]
    assert {row["id"]: row["sha256"] for row in docs} == {key: row["sha256"] for key, row in stored.items()}, "Corpus changed; review a fresh plan"
    remote_index = BASE + "/shared/private_tracking/.semantic-index.json"
    remote_queries = BASE + "/shared/private_tracking/.semantic-query-cache.json"
    old_index = api.file(remote_index, missing_ok=True)
    old_queries = api.file(remote_queries, missing_ok=True)
    if old_queries:
        existing = json.loads(old_queries)
        assert all(existing.get(k) == v for k, v in header().items())
        seeds.update(existing["queries"])
    content = json.dumps({**header(), "queries": dict(list(seeds.items())[-256:])}).encode()
    snapshot = BytesIO()
    with ZipFile(snapshot, "w", ZIP_DEFLATED) as archive:
        archive.writestr("missing.json", json.dumps([path for path, raw in ((remote_index, old_index), (remote_queries, old_queries)) if raw is None]))
        if old_index:
            archive.writestr("index.json", old_index)
        if old_queries:
            archive.writestr("queries.json", old_queries)
    backup = HOME + "/.config/mobile-web-service/common02/semantic-storage-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + ".zip"
    api.file(backup, snapshot.getvalue())
    assert sha(api.file(backup)) == sha(snapshot.getvalue())
    api.file(remote_queries, content)
    api.file(remote_index, index_file.read_bytes())
    assert sha(api.file(remote_index)) == sha(index_file.read_bytes())
    assert sha(api.file(remote_queries)) == sha(content)
    cases = []
    for row in protocol["queries"]:
        # cache_only forbids both embedding cache misses and all LLM generation on the server.
        response = requests.post(origin + "/api/v1/history/ask/", headers=headers, json={
            "question": row["question"], "date_basis": "processed", "include_candidates": True,
            "semantic": True, "cache_only": True, "generate": False}, timeout=(5, 30))
        assert response.status_code == 200
        result = response.json()
        retrieval = result["retrieval"]
        assert retrieval["api_requests"] == 0 and result["llm"]["status"] == "not_requested"
        labels = [item["source"] for item in result["evidence"]]
        matched = any(word.casefold() in label.casefold() for word in row["expected_source_keywords"] for label in labels)
        cases.append({"id": row["id"], "question": row["question"], "retrieval": retrieval,
                      "sources": labels, "expected_source_retrieved": matched,
                      "facts": result["facts"], "evidence_ids": [item["id"] for item in result["evidence"]],
                      "api_requests_during_verification": 0, "llm_generation_requests": 0})
        time.sleep(5.2)
    result = {"verified_utc": datetime.now(timezone.utc).isoformat(), "production_verified": True,
              "environment": "WSL against PythonAnywhere", "index_documents": len(stored),
              "pass": all(row["expected_source_retrieved"] and row["retrieval"]["status"] == "ranked" for row in cases),
              "quality_scope": "three fixed metadata-retrieval questions, not an accuracy benchmark",
              "paid_embedding_requests_for_build": build["actual_api_calls"],
              "paid_api_requests_during_verification": 0, "backup_verified": True,
              "index_sha256": sha(index_file.read_bytes()), "cases": cases}
    (WORKSPACE / "evidence/history/embedding-cloud.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
