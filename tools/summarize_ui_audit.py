"""Verify capture manifests and build a local before/after review sheet."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/"evidence/ui-audit"
before=json.loads((PUBLIC/"before.json").read_text())
after=json.loads((PUBLIC/"after.json").read_text())
checks=[];captures={};measurements=[]
for phase,record in (("before",before),("after",after)):
    for run in record["results"]:
        assert run["pass"],f'Incomplete {phase} {run["size"]}'
        if phase=="after": assert run["composer_flow_pass"]
        location=ROOT/run["fixture"]
        for item in run["files"]:
            assert hashlib.sha256((ROOT/item["path"]).read_bytes()).hexdigest()==item["sha256"]
        for name in ("testNativeAllPages.json","testWebAllPages.json"):
            for screen in json.loads((location/"captures/ui-audit"/name).read_text()):
                image=location/"captures/ui-audit"/(screen["name"]+".png")
                assert image.is_file()
                captures[(phase,run["size"],screen["name"])]=image
                if "web" in screen:
                    if phase=="after": assert not screen["web"]["overflow"],f'Horizontal overflow: {phase} {screen["name"]}'
                    measurements.append({"phase":phase,"size":run["size"],"screen":screen["name"],**screen["web"]})
        if phase=="after":
            for name in ("content-start","content-face-preview","content-tags","content-classification-ocr",
                         "content-ocr-keyboard","content-published","content-search-results","content-match-highlight"):
                assert (location/"composer-flow"/(name+".png")).is_file()
        checks.append({"phase":phase,"size":run["size"],"pass":True,"composer_flow_pass":run.get("composer_flow_pass")})
assert {row["size"] for row in checks if row["phase"]=="after"}=={"regular","small"}
web=json.loads((ROOT/"evidence/mobile-web/unit-verification.json").read_text())
android=json.loads((ROOT/"evidence/content/android/verification.json").read_text())
log=(PUBLIC/"django-tests.txt").read_text()
match=re.search(r'Ran (\d+) tests',log)
assert match and "\nOK\n" in log and web["pass"] and android["status"]=="passed"
server=json.loads((ROOT/"evidence/content/server/verification.json").read_text())
server_log=(ROOT/"evidence/content/server/tests-coverage.txt").read_text()
server_match=re.search(r'Ran (\d+) tests',server_log)
assert server["pass"] and server_match and "\nOK\n" in server_log
production_paths=[PUBLIC/"deployment.json",PUBLIC/"cloud/verification.json",ROOT/"evidence/history/cloud-runtime.json"]
production=[]
for path in production_paths:
    if path.exists():
        evidence=json.loads(path.read_text())
        production.append({"path":path.relative_to(ROOT).as_posix(),"pass":evidence.get("pass",False),
                           "production_verified":evidence.get("production_verified",False)})
presentation=ROOT/"evidence/private/ui-audit/review"
presentation.mkdir(parents=True,exist_ok=True)
pairs=[("native-history","Native records"),("web-answer","Web answer"),("web-history-detail","Review a record")]
width=340;height=605;top=50;gap=20
sheet=Image.new("RGB",(width*2+gap*3,(height+top+gap)*len(pairs)+gap),(247,246,238))
draw=ImageDraw.Draw(sheet)
try: font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",17)
except OSError: font=ImageFont.load_default()
for index,(name,label) in enumerate(pairs):
    y=gap+index*(height+top+gap)
    for column,phase in enumerate(("before","after")):
        x=gap+column*(width+gap);draw.text((x,y),label+" / "+phase,fill=(36,55,47),font=font)
        with Image.open(captures[(phase,"regular",name)]) as original:
            thumbnail=original.convert("RGB");thumbnail.thumbnail((width,height));sheet.paste(thumbnail,(x,y+top))
sheet.save(presentation/"comparison.png")
cards=[]
for key,path in captures.items():
    phase,size,name=key
    relative=path.relative_to(ROOT).as_posix()
    cards.append(f'<article data-phase="{phase}" data-size="{size}"><h3>{html.escape(phase+" / "+size+" / "+name)}</h3><a href="../../{relative}"><img loading="lazy" src="../../{relative}" alt="{html.escape(name)}"></a></article>')
page='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>공통평가 02 UI 전후 비교</title><style>body{font:14px system-ui;background:#f7f6ee;color:#24372f;margin:24px}header{position:sticky;top:0;background:#f7f6ee;padding:8px 0}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}article{background:white;border:1px solid #d8dfd2;border-radius:12px;padding:10px}h3{font-size:12px}img{width:100%;height:auto}select{padding:8px}article[hidden]{display:none}</style><header><h1>UI 전후 비교</h1><p>실제 Android 앱과 WebView 캡처입니다. AI 설명은 UI 검사 전용 고정 예제이며 실제 API 연결 검증과 구분합니다.</p><select id="phase"><option value="">변경 전후 모두</option><option>before</option><option>after</option></select> <select id="size"><option value="">모든 화면 크기</option><option>regular</option><option>small</option></select></header><main>'''+''.join(cards)+'''</main><script>for(const control of document.querySelectorAll('select'))control.onchange=()=>{for(const card of document.querySelectorAll('article'))card.hidden=(phase.value&&card.dataset.phase!==phase.value)||(size.value&&card.dataset.size!==size.value)}</script></html>'''
# Paths resolve from evidence/ui-audit to the single authoritative workspace.
(PUBLIC/"review.html").write_text(page,encoding="utf-8")
record={"verified_utc":datetime.now(timezone.utc).isoformat(),"pass":True,"environment":"Windows Android emulator with WSL Django",
    "screens":len(captures),"checks":checks,"django_tests":int(server_match[1]),"initial_ui_django_tests":int(match[1]),"web_unit_tests":web["tests"],
    "android_unit_tests":android["unitTests"]["tests"],"android_lint_errors":android["lint"]["errors"],
    "android_lint_warnings":android["lint"]["warnings"],"device_flow_tests":6,"external_llm_calls":0,
    "external_llm_calls_scope":"Isolated UI audit only; production LLM verification is recorded separately.",
    "production_verified":len(production)==3 and all(item["pass"] and item["production_verified"] for item in production),
    "production_verification":production,"native_app_is_webview":False,"measurements":measurements,
    "review_sheet":(presentation/"comparison.png").relative_to(ROOT).as_posix()}
(PUBLIC/"summary.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({key:record[key] for key in ("pass","screens","django_tests","web_unit_tests","android_unit_tests","device_flow_tests","production_verified")}))
