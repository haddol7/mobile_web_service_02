"""Check saved production conversations with cached embeddings; never generate with a provider."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import requests
import pythonanywhere_auth as auth


ROOT = Path(__file__).resolve().parents[2]


def main():
    assert os.environ.get("WSL_DISTRO_NAME"), "Use WSL"
    account = json.loads(auth.private_read(Path.home()/".config/mobile-web-service/common02/edge-auth.json"))
    base = account["base_url"].rstrip("/")
    assert base == "https://daejinha.pythonanywhere.com"
    client = requests.Session()
    client.headers["Authorization"] = "Token " + account["token"]

    def api(method, path, body=None, expected=200, session=client):
        response = session.request(method, base+"/api/v1/history/"+path, json=body, timeout=(5,40), allow_redirects=False)
        assert response.status_code == expected, f"{method} {path}: HTTP {response.status_code}"
        return response.json()

    anonymous = requests.get(base+"/api/v1/history/conversations/", timeout=(5,20), allow_redirects=False)
    assert anonymous.status_code in (401,403)
    api("GET", "conversations/"+str(uuid4())+"/", expected=404)
    private = ROOT/"evidence/private/chat/cloud-seed.json"
    private.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if private.exists():
        seed = json.loads(private.read_text())
    else:
        chat = api("POST", "conversations/", {}, expected=201)
        seed = {"conversation_id": chat["id"], "request_ids": [str(uuid4()),str(uuid4())]}
        fd = os.open(private, os.O_CREAT|os.O_TRUNC|os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(seed, output)
    questions = ["비행기를 타러 떠나는 장면을 찾아줘", "그 영상은 언제 분석됐어?"]
    results = []
    bodies = []
    for question, request_id in zip(questions,seed["request_ids"]):
        body = {"question":question, "conversation_id":seed["conversation_id"], "request_id":request_id,
                "date_basis":"processed", "include_candidates":True, "semantic":True,
                "cache_only":True, "generate":False}
        bodies.append(body)
        result = api("POST", "ask/", body)
        assert result["retrieval"]["api_requests"] == 0
        assert result["llm"]["status"] == "not_requested" and result["mode"] == "records"
        assert result["evidence"] and result["chat"]["conversation_id"] == seed["conversation_id"]
        results.append(result)
    assert results[0]["retrieval"]["query_cache_hit"] is True
    assert results[0]["retrieval"]["status"] == "ranked"
    expected_sessions = {str(row["session_id"]) for row in results[0]["evidence"]}
    assert {str(row["session_id"]) for row in results[1]["evidence"]} <= expected_sessions
    replay = api("POST", "ask/", bodies[0])
    assert replay["replayed"] is True and replay["chat"] == results[0]["chat"]
    other = requests.Session()
    other.headers["Authorization"] = client.headers["Authorization"]
    restored = api("GET", "conversations/"+seed["conversation_id"]+"/", session=other)
    assert len(restored["turns"]) == 2 and all(row["state"] == "complete" for row in restored["turns"])
    assert [row["question"] for row in restored["turns"]] == questions
    assert [row["result"]["answer"] for row in restored["turns"]] == [row["answer"] for row in results]
    listing = api("GET", "conversations/")
    assert any(row["id"] == seed["conversation_id"] and row["turn_count"] == 2 for row in listing["results"])
    proof = {"pass":True, "environment":"WSL against PythonAnywhere", "production_verified":True,
             "verified_utc":datetime.now(timezone.utc).isoformat(), "persisted_turns":2,
             "restored_in_separate_session":True, "request_replay_without_duplicate":True,
             "owner_only":True, "missing_chat_404":True, "followup_uses_prior_evidence":True,
             "conversation_hash":hashlib.sha256(seed["conversation_id"].encode()).hexdigest(),
             "actual_embedding_api_calls":0, "actual_llm_api_calls":0,
             "scope":"Storage, owner authorization and cached retrieval; no live provider generation test"}
    target = ROOT/"evidence/ui-audit/chat-cloud.json"
    target.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
