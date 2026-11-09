"""Provision approved server-only LLM/auth settings using the official deployment API."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
import time

import requests
import pythonanywhere_auth as auth
from pythonanywhere_deploy import API,BASE,DOMAIN,HOME,WORKSPACE,wait_ready


def main():
    if not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in WSL.")
    private=auth.secure_directory(Path.home()/".config/mobile-web-service/common02")
    llm_raw=auth.private_read(private/"llm.json")
    llm=json.loads(llm_raw)
    if llm.get("provider")!="openai" or not llm.get("api_key"):
        raise SystemExit("Approved OpenAI configuration is required.")
    api=API(auth.load_credentials());state=json.loads(api.file(BASE+"/active.json"))
    if state.get("phase")!="verified":
        raise SystemExit("Activate and verify the approved source before provisioning runtime settings.")
    console=48736170
    def run(code,python="python3.13"):
        nonce=secrets.token_hex(12)
        script=HOME+"/.common02-runtime-"+nonce+".py"
        result=HOME+"/.common02-runtime-"+nonce+".json"
        log=HOME+"/.common02-runtime-"+nonce+".log"
        wrapped="from pathlib import Path\nimport json,os\ntry:\n"+"\n".join("    "+line for line in code.splitlines())
        wrapped+="\n    outcome={'pass':True}\nexcept Exception as error:\n    outcome={'pass':False,'error_type':type(error).__name__}\n"
        wrapped+=f"Path({result!r}).write_text(json.dumps(outcome))\n"
        api.file(script,wrapped.encode())
        wait_ready(api,console)
        command="umask 077; "+shlex.quote(python)+" "+shlex.quote(script)+" > "+shlex.quote(log)+" 2>&1\n"
        api.request("POST",f"/consoles/{console}/send_input/",{"input":command})
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            raw=api.file(result,missing_ok=True)
            if raw:
                outcome=json.loads(raw)
                if not outcome.get("pass"):
                    raise RuntimeError("Remote runtime setup failed: "+outcome.get("error_type","unknown"))
                return
            time.sleep(2)
        raise RuntimeError("Remote runtime setup timed out; inspect the private job before retrying.")
    remote_dir=HOME+"/.config/mobile-web-service/common02"
    remote_llm=remote_dir+"/llm.json"
    remote_auth=remote_dir+"/edge-auth.json"
    storage=BASE+"/shared/private_tracking"
    run(f"""import shutil
directory=Path({remote_dir!r})
directory.mkdir(parents=True,exist_ok=True,mode=0o700)
directory.chmod(0o700)
target=Path({remote_llm!r})
if target.exists() and target.stat().st_size:
    backup=target.with_name('llm-backup-'+{secrets.token_hex(8)!r}+'.json')
    shutil.copy2(target,backup)
    backup.chmod(0o600)
if not target.exists():
    descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    os.close(descriptor)
target.chmod(0o600)
history=Path({storage!r})
history.mkdir(parents=True,exist_ok=True,mode=0o700)
history.chmod(0o700)""")
    api.file(remote_llm,llm_raw)
    assert hashlib.sha256(api.file(remote_llm)).digest()==hashlib.sha256(llm_raw).digest()
    code=f"""import sys
Path({remote_llm!r}).chmod(0o600)
sys.path.insert(0,{state['source']!r})
from deploy.production import load_environment
load_environment(Path({(HOME+'/.config/common01-auto/production.json')!r}),Path({state['source']!r}))
import django
django.setup()
from django.conf import settings
assert settings.HISTORY_MEDIA_ROOT.resolve()==Path({storage!r}).resolve()
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
owner=get_user_model().objects.get(username='daejinha',is_active=True)
token,created=Token.objects.get_or_create(user=owner)
target=Path({remote_auth!r})
target.write_text(json.dumps({{'base_url':'https://{DOMAIN}','username':'daejinha','token':token.key}}))
target.chmod(0o600)"""
    run(code,state["virtualenv"]+"/bin/python")
    incoming=private/(".edge-auth-"+secrets.token_hex(8))
    auth.private_write(incoming,api.file(remote_auth));os.replace(incoming,private/"edge-auth.json")
    app=json.loads(auth.private_read(private/"edge-auth.json"))
    api.request("POST",f"/webapps/{DOMAIN}/reload/",{})
    response=None
    for attempt in range(6):
        time.sleep(3)
        response=requests.get(app["base_url"]+"/api/v1/history/frames/?limit=1",headers={"Authorization":"Token "+app["token"]},timeout=(5,20),allow_redirects=False)
        if response.status_code==200:break
    assert response.status_code==200,"Authenticated history read failed."
    observed=len(response.json()["results"])
    answer=requests.post(app["base_url"]+"/api/v1/history/ask/",headers={"Authorization":"Token "+app["token"]},
        json={"question":"현재 기록에서 선 통과는 몇 건인가요? 기록이 없으면 그 사실만 알려주세요.","generate":True},timeout=(5,25),allow_redirects=False)
    assert answer.status_code==200,"Production question API failed."
    generated=answer.json()
    record={"verified_utc":datetime.now(timezone.utc).isoformat(),"environment":"PythonAnywhere production with WSL API client",
        "origin":app["base_url"],"release":state["release"],"history_api_status":response.status_code,
        "history_records_present":bool(observed),"persistent_history_storage_verified":True,
        "llm_provider":llm["provider"],"llm_model":llm["model"],"actual_llm_generation_verified":generated["llm"]["status"]=="generated",
        "llm_mode":generated["mode"],"question_status":answer.status_code,
        "facts":generated["facts"],"llm_text":generated["llm"]["text"],"key_in_source_tree":False,
        "production_verified":True}
    record["pass"]=record["actual_llm_generation_verified"]
    (WORKSPACE/"evidence/history/cloud-runtime.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(record,ensure_ascii=False))
    if not record["pass"]:raise SystemExit(1)


if __name__=="__main__":main()
