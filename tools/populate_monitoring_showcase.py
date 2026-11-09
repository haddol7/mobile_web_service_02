"""Import sampled real inference; dataset-based review remains visibly distinguished."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid5,NAMESPACE_URL
import cv2
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence/private/monitoring-showcase/v2"


def prepare():
    data=json.loads((OUT/"collection.json").read_text());entries=[]
    for case in data["cases"]:
        rows=[json.loads(line) for line in (ROOT/case["log"]).read_text().splitlines()]
        useful=[r for r in rows if r["faces"]]
        selected={useful[0]["frame_index"],useful[-1]["frame_index"]}
        selected.update(useful[round((len(useful)-1)*n/4)]["frame_index"] for n in (1,2,3))
        if case["expected"]:
            bound=[r for r in useful if any(f["body_track_id"] is not None and f["candidate_profile_id"]==case["expected"] for f in r["faces"])]
            selected.add(max(bound,key=lambda r:max(f["similarity"] for f in r["faces"]))["frame_index"])
        session=uuid5(NAMESPACE_URL,"monitoring-showcase-v2/"+case["sha256"]).hex
        config={"id":session,"source_label":case["name"],"source_kind":"video","recording_started_at":None,
                "model_versions":{"yolov5":"7.0","face_model":"buffalo_l","face_policy":"candidate-2","demo_provenance":"public_video_scenario_v2"},
                "profiles":[{"id":p["id"],"name":p["name"]} for p in data["profiles"]],
                "purpose":"demo","source_reference":"VoxCeleb2/"+case["identity"]+"/"+case["source_video_id"]}
        capture=cv2.VideoCapture(str(ROOT/case["path"]));fps=capture.get(cv2.CAP_PROP_FPS)
        for row in useful:
            if row["frame_index"] not in selected: continue
            index=round(row["video_seconds"]*fps);capture.set(cv2.CAP_PROP_POS_FRAMES,index);ok,image=capture.read();assert ok
            encoded,raw=cv2.imencode(".jpg",image,[cv2.IMWRITE_JPEG_QUALITY,80]);assert encoded
            key=hashlib.sha256(f'{session}:{row["frame_index"]}'.encode()).hexdigest()
            (OUT/(key+".jpg")).write_bytes(raw.tobytes())
            frame={k:row[k] for k in ("frame_index","video_seconds","processed_at_utc","tracks","faces","crossings","image_size")}
            frame["captured_at"]=None
            entries.append({"id":key,"case":case["case"],"expected":case["expected"],
                            "packet":{"schema_version":1,"session":config,"frame":frame,"post_id":None}})
        capture.release()
    (OUT/"packets.json").write_text(json.dumps(entries,ensure_ascii=False,indent=2))
    return data,entries


def local(data,entries):
    folder=ROOT/"evidence/private/history"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f");folder.mkdir(parents=True)
    os.environ.update(DJANGO_SETTINGS_MODULE="photoblog.settings",DJANGO_DEBUG="true",BLOG_OWNER_USERNAME="daejinha",
                      DJANGO_DB_PATH=str(folder/"db.sqlite3"),DJANGO_MEDIA_ROOT=str(folder/"media"),HISTORY_MEDIA_ROOT=str(folder/"history-images"))
    sys.path.insert(0,str(ROOT/"PhotoBlogServer"));import django;django.setup()
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.core.files.base import ContentFile
    from blog.models import PersonProfile,PersonTrack
    from blog.history_serializers import PacketSerializer
    from blog.history_services import ingest,review_track
    from blog.services import create_post
    call_command("migrate",interactive=False,verbosity=0)
    password=secrets.token_urlsafe(24);owner=get_user_model().objects.create_user("daejinha",password=password)
    (folder/"test-auth.json").write_text(json.dumps({"username":"daejinha","password":password}))
    for entry in entries:
        form=PacketSerializer(data=entry["packet"]);form.is_valid(raise_exception=True)
        ingest(actor=owner,packet=form.validated_data,upload=SimpleUploadedFile("frame.jpg",(OUT/(entry["id"]+".jpg")).read_bytes(),"image/jpeg"))
    for profile in data["profiles"]:
        p=PersonProfile.objects.get(pk=profile["id"]);p.reference_image.save("reference.jpg",ContentFile((OUT/profile["images"][1]).read_bytes()))
    reviewed=set()
    for entry in entries:
        if entry["case"] not in ("A-1","A-2","B-1"):continue
        for track in PersonTrack.objects.filter(session_id=entry["packet"]["session"]["id"],candidate_id=entry["expected"]):
            if track.pk in reviewed:continue
            review_track(actor=owner,track_id=track.pk,revision=track.revision,profile_key=entry["expected"],basis="dataset");reviewed.add(track.pk)
    create_post(actor=owner,values={"title":"관측 영상 예시","text":"실제 공개 영상 분석에서 보관한 사진입니다.",
        "image":SimpleUploadedFile("example.jpg",(OUT/(entries[0]["id"]+".jpg")).read_bytes(),"image/jpeg")})
    (ROOT/"evidence/history/latest-fixture.json").write_text(json.dumps({"fixture":str(folder.relative_to(ROOT))}))
    print(json.dumps({"fixture":str(folder.relative_to(ROOT)),"frames":len(entries),"profiles":len(data["profiles"]),"reviewed_dataset_tracks":len(reviewed)}),flush=True)


def cloud(data,entries):
    sys.path.insert(0,str(ROOT/"tools/deployment"));import pythonanywhere_auth as auth
    app=json.loads(auth.private_read(Path.home()/".config/mobile-web-service/common02/edge-auth.json"))
    origin=app["base_url"];client=requests.Session();client.headers["Authorization"]="Token "+app["token"]
    def call(method,path,**kwargs):
        r=client.request(method,origin+path,timeout=(5,30),allow_redirects=False,**kwargs)
        assert r.status_code in (200,201),f"Owner API {path} returned {r.status_code}"
        return r.json()
    baseline=call("GET","/api_root/Post/")
    for entry in entries:
        raw=(OUT/(entry["id"]+".jpg")).read_bytes()
        result=call("POST","/api/v1/history/ingest/",data={"packet":json.dumps(entry["packet"],ensure_ascii=False)},files={"image":("frame.jpg",raw,"image/jpeg")})
        assert result["id"]==entry["id"]
    for profile in data["profiles"]:
        current=call("GET","/api/v1/history/people/"+profile["id"]+"/")
        if not current["reference_available"]:
            call("POST","/api/v1/history/references/"+profile["id"]+"/",files={"image":("reference.jpg",(OUT/profile["images"][1]).read_bytes(),"image/jpeg")})
    for case in ("A-1","A-2","B-1"):
        entry=next(e for e in entries if e["case"]==case)
        rows=call("GET","/api/v1/history/frames/?session="+entry["packet"]["session"]["id"]+"&limit=24")["results"]
        seen=set()
        for row in rows:
            for track in row["tracks"]:
                if track["id"] in seen or track["reviewed"] or track["candidate"]!=entry["expected"]:continue
                seen.add(track["id"])
                call("PATCH",f'/api/v1/history/tracks/{track["id"]}/',json={"revision":track["revision"],"profile":entry["expected"],"basis":"dataset"})
    assert call("GET","/api_root/Post/")==baseline
    people=[call("GET","/api/v1/history/people/"+p["id"]+"/") for p in data["profiles"]]
    assert all(p["source_count"]==2 and p["reference_available"] and len(p["timeline"])==2 for p in people)
    ask=call("POST","/api/v1/history/ask/",json={"question":"어떤 영상에서 발견됐어?","profile":"showcase-v2-a","include_candidates":True,"date_basis":"processed"})
    assert ask["facts"]["source_count"]==2 and len(ask["evidence"])==2 and ask["facts"]["unknown_date_frames"]>0
    assert len({e["session_id"] for e in ask["evidence"]})==2
    proof={"verified_utc":datetime.now(timezone.utc).isoformat(),"origin":origin,"production_verified":True,
           "actual_video_sessions_added":8,"real_sampled_images_added":len(entries),"enrolled_profiles":3,
           "unknown_identity_videos":2,"capture_dates_preserved_unknown":True,"existing_public_posts_preserved":True,
           "dataset_confirmation_explicit":True,"all_profiles_have_two_distinct_source_videos":True,
           "question_facts":ask["facts"],"question_evidence_ids":[e["id"] for e in ask["evidence"]],
           "profiles":[{k:p[k] for k in ("key","name","source_count","confirmed_tracks","candidate_tracks","reference_available")} for p in people],"pass":True}
    (ROOT/"evidence/history/showcase-cloud.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(proof,ensure_ascii=False),flush=True)


if __name__=="__main__":
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    parser=argparse.ArgumentParser();parser.add_argument("--cloud",action="store_true");args=parser.parse_args()
    dataset,packets=prepare()
    cloud(dataset,packets) if args.cloud else local(dataset,packets)
