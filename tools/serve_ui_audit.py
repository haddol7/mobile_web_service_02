"""Disposable copy of the history fixture for Android UI captures; no external LLM calls."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import sys
from socketserver import ThreadingMixIn
from threading import Thread
from unittest.mock import patch
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
    raise SystemExit("Run in WSL.")
original = (ROOT / json.loads((ROOT/"evidence/history/latest-fixture.json").read_text())["fixture"]).resolve()
if not original.is_relative_to((ROOT/"evidence/private/history").resolve()):
    raise SystemExit("Invalid isolated fixture.")
directory = ROOT/"evidence/private/ui-audit"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
directory.mkdir(parents=True)
with sqlite3.connect(original/"db.sqlite3") as source, sqlite3.connect(directory/"db.sqlite3") as target:
    source.backup(target)
shutil.copy2(original/"test-auth.json", directory/"test-auth.json")
shutil.copytree(original/"media", directory/"media")
os.environ.update(DJANGO_SETTINGS_MODULE="photoblog.settings", DJANGO_DEBUG="true",
    DJANGO_DB_PATH=str(directory/"db.sqlite3"), DJANGO_MEDIA_ROOT=str(directory/"media"),
    HISTORY_MEDIA_ROOT=str(original/"history-images"), HISTORY_CHAT_ROOT=str(directory/"chat"), BLOG_OWNER_USERNAME="daejinha",
    HISTORY_LLM_CONFIG="", HISTORY_LLM_API_KEY="ui-fixture-not-a-credential", HISTORY_LLM_MODEL="ui-fixture")
sys.path.insert(0,str(ROOT/"PhotoBlogServer"))
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler

def fixture_generation(question, retrieved):
    return {"status":"generated", "text":f'기록된 선 통과는 {retrieved["facts"]["passages"]}건입니다. '
        '서로 다른 사람 수나 방문 횟수는 이 기록만으로 알 수 없습니다. 촬영 날짜를 모르는 자료는 날짜를 추정하지 않습니다.',
        "evidence_ids":[row["id"] for row in retrieved["evidence"][:3]]}

def fixture_semantic(question, frames, **kwargs):
    # Exercise the client opt-in and result presentation without a provider call.
    keys=[str(key) for key in frames.order_by().values_list("session_id",flat=True).distinct()[:5]]
    return {"strategy":"semantic","status":"ranked" if keys else "empty",
            "scope":"semantic_top_5","api_requests":0,"query_cache_hit":True,
            "session_ids":keys,"matched_sessions":len(keys),"fixture":True}

events=[]
class Quiet(WSGIRequestHandler):
    def log_message(self,*_): pass
    def log_request(self,code="-",size="-"):
        events.append({"method":self.command,"path":self.path.split("?")[0],"status":int(code)})
class Server(ThreadingMixIn,WSGIServer):
    daemon_threads=True
server=make_server("0.0.0.0",0,StaticFilesHandler(get_wsgi_application()),server_class=Server,handler_class=Quiet)
with patch("blog.history_api.generate",side_effect=fixture_generation), \
     patch("blog.history_embeddings.rank",side_effect=fixture_semantic), \
     patch("blog.history_embeddings.urlopen",side_effect=AssertionError("Paid APIs are disabled in UI tests.")):
    Thread(target=server.serve_forever,daemon=True).start()
    print(json.dumps({"ready":True,"port":server.server_port,"fixture":directory.relative_to(ROOT).as_posix(),
                      "llm_mode":"deterministic UI fixture; no external calls"}),flush=True)
    try:
        for line in sys.stdin:
            if line.strip()=="stop": break
    finally:
        server.shutdown();server.server_close()
        (directory/"http.json").write_text(json.dumps({"requests":events},indent=2)+"\n")
