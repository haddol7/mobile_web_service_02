"""Serve only the isolated history fixture until the verification driver closes stdin."""
import json
import os
from pathlib import Path
import platform
import sys
from socketserver import ThreadingMixIn
from threading import Thread
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
    raise SystemExit("Run inside WSL.")
latest = json.loads((ROOT/"evidence/history/latest-fixture.json").read_text())
directory = (ROOT/latest["fixture"]).resolve()
if not directory.is_relative_to((ROOT/"evidence/private/history").resolve()) or not (directory/"db.sqlite3").is_file():
    raise SystemExit("Invalid isolated history fixture.")
os.environ.update(DJANGO_SETTINGS_MODULE="photoblog.settings", DJANGO_DEBUG="true",
    DJANGO_DB_PATH=str(directory/"db.sqlite3"), DJANGO_MEDIA_ROOT=str(directory/"media"),
    HISTORY_MEDIA_ROOT=str(directory/"history-images"), BLOG_OWNER_USERNAME="daejinha")
sys.path.insert(0, str(ROOT/"PhotoBlogServer"))
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler
events = []
class Quiet(WSGIRequestHandler):
    def log_message(self, *_): pass
    def log_request(self, code="-", size="-"):
        events.append({"method":self.command, "path":self.path.split("?")[0], "status":int(code)})
class Server(ThreadingMixIn, WSGIServer):
    daemon_threads = True
server = make_server("0.0.0.0", 0, StaticFilesHandler(get_wsgi_application()),
                     server_class=Server, handler_class=Quiet)
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
print(json.dumps({"ready":True, "port":server.server_port}), flush=True)
try:
    for line in sys.stdin:
        if line.strip() == "stop": break
finally:
    server.shutdown(); server.server_close()
    (ROOT/"evidence/history/device-server-http.json").write_text(json.dumps({"requests":events},indent=2)+"\n")
