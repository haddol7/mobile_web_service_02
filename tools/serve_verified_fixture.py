"""Serve the verified local photo fixture until the Windows driver closes stdin."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
from threading import Thread
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler

root=Path(__file__).resolve().parents[1]
if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
    raise SystemExit('Run the backend fixture server inside WSL.')
private=root/'evidence/private/local'
if not (private/'db.sqlite3').is_file():
    raise SystemExit('Create the isolated fixture with tools/verify_yolo_pipeline.py first.')
os.environ.update(DJANGO_SETTINGS_MODULE='photoblog.settings',DJANGO_DEBUG='true',
                  DJANGO_DB_PATH=str(private/'db.sqlite3'),DJANGO_MEDIA_ROOT=str(private/'media'))
sys.path.insert(0,str(root/'PhotoBlogServer'))
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler

events=[]
class Handler(WSGIRequestHandler):
    def log_message(self,*_):pass
    def log_request(self,code='-',size='-'):
        events.append({'method':self.command,'path':self.path.split('?')[0],'status':int(code)})
class Server(ThreadingMixIn,WSGIServer):
    daemon_threads=True

server=make_server('0.0.0.0',0,StaticFilesHandler(get_wsgi_application()),server_class=Server,handler_class=Handler)
thread=Thread(target=server.serve_forever,daemon=True);thread.start()
print(json.dumps({'ready':True,'port':server.server_port,'environment':'WSL Ubuntu'}),flush=True)
try:
    for line in sys.stdin:
        if line.strip()=='stop':break
finally:
    server.shutdown();server.server_close()
    out=root/'evidence/mobile-flow';out.mkdir(parents=True,exist_ok=True)
    (out/'server-http.json').write_text(json.dumps({'finished_utc':datetime.now(timezone.utc).isoformat(),
        'environment':'WSL Ubuntu','requests':events},indent=2),encoding='utf-8')
