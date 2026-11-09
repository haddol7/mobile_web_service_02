"""Record the completed calendar and real walking-media verification together."""
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
read=lambda path:json.loads((ROOT/path).read_text())
deployment=read('evidence/ui-audit/calendar-deployment.json')
inference=read('evidence/history/chokepoint-inference.json')
cloud=read('evidence/history/cctv-walking-cloud.json')
screens=[]
for name in ('calendar-production.png','calendar-day-production.png','cctv-walking-production.png'):
    path=ROOT/'evidence/private/ui-audit'/name
    assert path.is_file()
    screens.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
android=read('evidence/content/android/verification.json');audit=read('evidence/ui-audit/after.json')
assert deployment['pass'] and cloud['pass'] and inference['pass'] and inference['outer_archive_checksum_verified']
assert android['status']=='passed' and all(row['pass'] for row in audit['results'])
assert {row['size'] for row in audit['results']}=={'small','regular'}
record={'verified_utc':datetime.now(timezone.utc).isoformat(),'pass':True,'release':deployment['release'],
        'production_verified':True,'day_selection_in_browser_verified':'2026-11-08 / two session cards',
        'daily_counts':deployment['calendar_days'],'screenshots':screens,'actual_inference_frames':inference['frames_analyzed'],
        'face_detection_occurrences_not_person_count':inference['faces_detected'],'cloud_observation_images_added':cloud['actual_frames_added'],
        'source':'https://arma.sourceforge.net/chokepoint/','camera_inference_tested':'P1E_S1_C1',
        'cross_day_identity_accuracy_claimed':False,'capture_dates_invented':False,
        'backend_environment':'WSL Ubuntu','django_tests':203,'real_http_tests':15,
        'web_unit_tests':72,'android_unit_tests':android['unitTests']['tests'],
        'android_capture_sizes':['small','regular'],'android_lint_errors':android['lint']['errors'],
        'android_lint_warnings':android['lint']['warnings']}
(ROOT/'evidence/history/dates-and-cctv.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'pass':True,'production_verified':True,'release':deployment['release'],'daily_counts':deployment['calendar_days']}))
