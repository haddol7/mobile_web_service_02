"""Publish real portal observations and a separately approved one-request embedding update."""
import argparse
from datetime import datetime, timezone
import fcntl
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
from pythonanywhere_deploy import API, BASE, HOME, WORKSPACE, SERVER

OUT = WORKSPACE/"evidence/private/cctv-walking/expanded"
REMOTE_INDEX = BASE+"/shared/private_tracking/.semantic-index.json"
sys.path.insert(0,str(SERVER))
os.environ.setdefault("DJANGO_SETTINGS_MODULE","photoblog.settings")
import django
django.setup()
from blog.history_serializers import PacketSerializer
from blog.history_embeddings import header,read_index


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def app_client():
    credentials=json.loads(auth.private_read(Path.home()/".config/mobile-web-service/common02/edge-auth.json"))
    client=requests.Session()
    client.headers["Authorization"]="Token "+credentials["token"]
    origin=credentials["base_url"].rstrip("/")
    assert origin=="https://daejinha.pythonanywhere.com"
    return client,origin


def call(client,origin,method,path,**kwargs):
    response=client.request(method,origin+path,timeout=(5,40),allow_redirects=False,**kwargs)
    assert response.status_code in (200,201), f"{path}: HTTP {response.status_code}"
    return response.json()


def inputs():
    data=json.loads((OUT/"packets.json").read_text())
    assert len(data["cases"])==4 and len({row["session"] for row in data["cases"]})==4
    for entry in data["entries"]:
        form=PacketSerializer(data=entry["packet"])
        form.is_valid(raise_exception=True)
        frame=entry["packet"]["frame"]
        assert frame["captured_at"] is None and not frame["crossings"]
        assert all(face["candidate_profile_id"] is None for face in frame["faces"])
        expected=sha(f'{entry["packet"]["session"]["id"]}:{frame["frame_index"]}'.encode())
        assert expected==entry["id"]
    return data


def preflight():
    OUT.mkdir(parents=True,exist_ok=True)
    client,origin=app_client()
    api=API(auth.load_credentials())
    corpus=call(client,origin,"GET","/api/v1/history/embedding-documents/")
    stored=read_index_from_bytes(api.file(REMOTE_INDEX),OUT)
    assert {row["id"]:row["sha256"] for row in corpus["documents"]}=={key:row["sha256"] for key,row in stored.items()}, "Existing corpus needs a separate review before adding sources"
    proof={"pass":True,"verified_utc":stamp(),"existing_documents":len(stored),
           "existing_index_current":True,"facts":call(client,origin,"GET","/api/v1/history/overview/")["facts"],
           "actual_embedding_api_calls":0,"actual_llm_api_calls":0}
    save(WORKSPACE/"evidence/history/chokepoint-expanded-preflight.json",proof)
    print(json.dumps(proof),flush=True)


def observations():
    data=inputs()
    client,origin=app_client()
    posts=call(client,origin,"GET","/api_root/Post/")
    before=call(client,origin,"GET","/api/v1/history/overview/")["facts"]
    previous_chats=call(client,origin,"GET","/api/v1/history/conversations/")["results"]
    created=0
    for entry in data["entries"]:
        result=call(client,origin,"POST","/api/v1/history/ingest/",
                    data={"packet":json.dumps(entry["packet"],ensure_ascii=False)},
                    files={"image":("portal.jpg",(WORKSPACE/entry["image"]).read_bytes(),"image/jpeg")})
        assert result["id"]==entry["id"]
        created+=result["created"]
    replay=data["entries"][0]
    result=call(client,origin,"POST","/api/v1/history/ingest/",data={"packet":json.dumps(replay["packet"],ensure_ascii=False)},
                files={"image":("portal.jpg",(WORKSPACE/replay["image"]).read_bytes(),"image/jpeg")})
    assert result["created"] is False
    cases=[]
    for case in data["cases"]:
        result=call(client,origin,"GET","/api/v1/history/sessions/",params={"date_basis":"processed","session":case["session"]})
        cards=result["results"]
        assert sum(card["sample_count"] for card in cards)==case["selected_frames"]
        frames=[frame for card in cards for frame in card["frames"]]
        assert len(frames)==case["selected_frames"]
        assert all(frame["observed_at"] is None and all(not track["confirmed"] and not track["candidate"] for track in frame["tracks"]) for frame in frames)
        question=call(client,origin,"POST","/api/v1/history/ask/",json={"question":"어떤 영상에서 발견됐어?",
            "session":case["session"],"date_basis":"processed","include_candidates":True,"semantic":False,"generate":False})
        assert question["facts"]["source_count"]==1 and question["facts"]["sampled_frames"]==len(frames)
        assert question["retrieval"]["api_requests"]==0 and question["llm"]["status"]=="not_requested"
        image=client.get(origin+frames[0]["image_url"],timeout=(5,20),allow_redirects=False)
        assert image.status_code==200 and image.headers["Content-Type"].startswith("image/jpeg")
        anonymous=requests.get(origin+frames[0]["image_url"],timeout=(5,20),allow_redirects=False)
        assert anonymous.status_code in (401,403)
        cases.append({**case,"cloud_samples":len(frames),"question_db_counts_match":True,
                      "authenticated_image_sha256":sha(image.content),"anonymous_image_denied":True})
    after_posts=call(client,origin,"GET","/api_root/Post/")
    assert all(row in after_posts for row in posts)
    chats=call(client,origin,"GET","/api/v1/history/conversations/")["results"]
    assert all(any(row["id"]==old["id"] and row["turn_count"]>=old["turn_count"] for row in chats) for old in previous_chats)
    proof={"pass":True,"verified_utc":stamp(),"environment":"WSL against PythonAnywhere","production_verified":True,
           "new_recordings":4,"selected_observation_images":len(data["entries"]),"newly_created_images":created,
           "previous_facts":before,"current_facts":call(client,origin,"GET","/api/v1/history/overview/")["facts"],
           "cases":cases,"existing_posts_preserved":True,"existing_chats_preserved":True,
           "duplicate_replay_created_new_frame":False,"original_capture_dates_invented":False,
           "identities_automatically_confirmed":False,"actual_embedding_api_calls":0,"actual_llm_api_calls":0}
    save(WORKSPACE/"evidence/history/chokepoint-expanded-cloud.json",proof)
    print(json.dumps({key:value for key,value in proof.items() if key!="cases"},ensure_ascii=False),flush=True)


def embeddings(approved):
    assert approved, "The owner must explicitly authorize the single embedding request"
    data=inputs()
    new_ids={str(__import__("uuid").UUID(row["session"])) for row in data["cases"]}
    client,origin=app_client()
    api=API(auth.load_credentials())
    corpus=call(client,origin,"GET","/api/v1/history/embedding-documents/")
    expected_counts={str(__import__("uuid").UUID(row["session"])):row["selected_frames"] for row in data["cases"]}
    for row in corpus["documents"]:
        if row["id"] in expected_counts:
            assert f'저장된 관측 사진: {expected_counts[row["id"]]}장' in row["text"]
    directory=OUT/"embeddings"
    directory.mkdir(exist_ok=True)
    index=directory/".semantic-index.json"
    audit=WORKSPACE/"evidence/history/chokepoint-expanded-embedding-build.json"
    completion=directory/"completed-build.json"
    remote_before=api.file(REMOTE_INDEX)
    if not index.exists():
        index.write_bytes(remote_before)
    queries=api.file(BASE+"/shared/private_tracking/.semantic-query-cache.json")
    (directory/".semantic-query-cache.json").write_bytes(queries)
    save(directory/"corpus.json",corpus)
    sys.path.insert(0,str(WORKSPACE/"tools"))
    from build_embedding_index import prepare,build
    plan,docs,previous,_,pending,_=prepare(corpus,index,[])
    needed={row[1] for row in pending}
    if completion.exists():
        built=json.loads(completion.read_text())
        assert built["index_sha256"]==sha(index.read_bytes()) and not needed
    else:
        assert needed==new_ids and plan["changed_documents"]==4 and plan["api_requests_required"]==1
        if audit.exists():
            old=json.loads(audit.read_text())
            assert old.get("requests_attempted",old.get("actual_api_calls",0))==0, "The one approved request was already attempted; no automatic retry"
        save(directory/"approved-plan.json",{**plan,"approved_max_api_calls":1,"approved_scope":"four new source metadata documents only"})
        built=build(corpus,index,[],apply=True,allow_paid_api=True,max_api_calls=1,audit_path=audit)
        assert built["actual_api_calls"]==1
        save(audit,{**built,"pass":True,"approval":"Owner approved at most one new-source embedding request on 2026-11-09"})
        save(completion,built)
    stored=read_index(index)
    assert {row["id"]:row["sha256"] for row in docs}=={key:row["sha256"] for key,row in stored.items()}
    existing=read_index_from_bytes(remote_before,directory)
    for key,old in existing.items():
        if key not in new_ids:
            assert key in stored and stored[key]["sha256"]==old["sha256"]
            assert all(abs(left-right)<1e-12 for left,right in zip(old["vector"],stored[key]["vector"]))
    snapshot=BytesIO()
    with ZipFile(snapshot,"w",ZIP_DEFLATED) as bundle:
        bundle.writestr("index.json",remote_before)
    backup=HOME+"/.config/mobile-web-service/common02/chokepoint-index-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+".zip"
    api.file(backup,snapshot.getvalue())
    assert sha(api.file(backup))==sha(snapshot.getvalue())
    api.file(REMOTE_INDEX,index.read_bytes())
    assert sha(api.file(REMOTE_INDEX))==sha(index.read_bytes())
    # Existing cached questions check index coverage without new provider calls.
    protocol=json.loads((WORKSPACE/"docs/testing/embedding-protocol.json").read_text())
    checks=[]
    for item in protocol["queries"]:
        result=call(client,origin,"POST","/api/v1/history/ask/",json={"question":item["question"],"date_basis":"processed",
                    "include_candidates":True,"semantic":True,"cache_only":True,"generate":False})
        assert result["retrieval"]["api_requests"]==0 and result["llm"]["status"]=="not_requested"
        assert result["retrieval"]["status"]=="ranked"
        assert any(keyword.casefold() in row["source"].casefold() for row in result["evidence"] for keyword in item["expected_source_keywords"])
        checks.append({"id":item["id"],"retrieval":result["retrieval"],"sources":[row["source"] for row in result["evidence"]]})
        time.sleep(5.2)
    licence=(WORKSPACE/"docs/testing/licenses/ChokePoint.txt").read_bytes()
    api.file(BASE+"/shared/private_tracking/CHOKEPOINT_LICENSE.txt",licence)
    assert sha(api.file(BASE+"/shared/private_tracking/CHOKEPOINT_LICENSE.txt"))==sha(licence)
    proof={"pass":True,"verified_utc":stamp(),"environment":"WSL against PythonAnywhere","production_verified":True,
           "index_documents":len(stored),"new_documents":4,"previous_vectors_reused":len(stored)-4,
           "actual_embedding_api_calls":built["actual_api_calls"],"actual_llm_api_calls":0,
           "verification_paid_api_calls":0,"usage":built["usage"],"index_sha256":sha(index.read_bytes()),
           "previous_index_backed_up":True,"private_query_cache_preserved":True,"checks":checks,
           "photos_or_face_features_sent_to_api":False,"licence_retained_with_derivatives":True}
    save(WORKSPACE/"evidence/history/chokepoint-expanded-embedding-cloud.json",proof)
    print(json.dumps(proof,ensure_ascii=False),flush=True)


def read_index_from_bytes(raw,directory):
    target=directory/"previous-index.json"
    target.write_bytes(raw)
    return read_index(target)


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use the WSL project virtualenv"
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["preflight","observations","embeddings"])
    parser.add_argument("--approved-one-embedding-call",action="store_true")
    args=parser.parse_args()
    lock=(auth.DEFAULT_DIR/"deployment.lock").open("w")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if args.stage=="preflight":
        preflight()
    elif args.stage=="observations":
        observations()
    else:
        embeddings(args.approved_one_embedding_call)


if __name__=="__main__":
    main()
