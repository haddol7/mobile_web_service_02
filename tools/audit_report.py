"""Audit the report against the unchanged course template and actual verification records."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zipfile import ZipFile
from docx import Document
from lxml import etree

root=Path(__file__).resolve().parents[1]
report=root/'모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx'
reference=root/'docs/reference/모바일웹서비스 프로젝트_공통평가 02_수행 결과 보고서.docx'
requirements=json.loads((root/'docs/assessment-requirements.json').read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def record(name):return json.loads((root/name).read_text(encoding='utf-8'))
original,doc=Document(reference),Document(report)
checks=[]
def check(name,condition):
    checks.append({'check':name,'pass':bool(condition)})
    if not condition:raise AssertionError(name)

check('requirement_columns_preserved',all(original.tables[0].cell(row,col).text==doc.tables[0].cell(row,col).text
      for row in range(len(original.tables[0].rows)) for col in range(4)))
check('assessor_grading_column_blank',all(not row.cells[5].text.strip() for row in doc.tables[0].rows[2:]))
check('student_identity',all(value in '\n'.join(p.text for p in doc.paragraphs[:6])
      for value in ['2020105671','하대진','컴퓨터공학과']))
check('draft_status_visible','진행본' in '\n'.join(p.text for p in doc.paragraphs[:9]))
labels={'complete':'완료','partial':'부분','pending':'대기','deferred':'미정'}
for row,item in enumerate(requirements['requirements'],2):
    check('status_'+item['id'],doc.tables[0].cell(row,4).text==labels[item['status']])
    for relative in item['evidence']:check('evidence_exists_'+relative,(root/relative).is_file())
    caption=item['report_evidence'].split('\n')[0]
    if re.fullmatch(r'B\d\d',caption):check('caption_'+item['id'],any(p.text.startswith(caption+' ') for p in doc.paragraphs))
check('unfinished_work_not_marked_complete',all(item['status']!='complete' for item in requirements['requirements'] if item['id'] in {'3','8','9','10'}))

with ZipFile(report) as z:
    images={hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if name.startswith('word/media/assessment02-')}
    expected=[root/'evidence/screenshots'/name for name in ['github-folder-structure.jpg','changedetection-vscode.png',
        'changedetection-upload-vscode.png','detect-hook-vscode.png','local-api-root.jpg','local-api-posts.jpg',
        'local-list.jpg','yolo-native-list.png','yolo-native-detail.png']]
    expected.append(root/'evidence/yolo-pipeline/original-image/bus.jpg')
    expected.extend(root/'evidence/mobile-flow'/name for name in ['yolo-mobile-web-list.png','yolo-mobile-web-detail.png'])
    check('all_twelve_figures_embedded_without_reencoding',images=={digest(path) for path in expected} and len(images)==12)
    rel=etree.fromstring(z.read('word/_rels/document.xml.rels'))
    check('no_external_image_relationships',all(node.get('TargetMode')!='External' for node in rel if node.get('Type','').endswith('/image')))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    xml=etree.fromstring(z.read('word/document.xml'))
    with ZipFile(reference) as src:
        source_xml=etree.fromstring(src.read('word/document.xml'))
        check('section_geometry_preserved',etree.tostring(xml.find('w:body/w:sectPr',ns))==etree.tostring(source_xml.find('w:body/w:sectPr',ns)))
        mutable={'word/document.xml','word/header1.xml','word/settings.xml','word/_rels/document.xml.rels','[Content_Types].xml'}
        check('opaque_template_parts_preserved',all(src.read(name)==z.read(name) for name in src.namelist() if name not in mutable))

server=record('evidence/content/server/verification.json')
check('actual_wsl_backend_validation',server['pass'] and server['environment']=='WSL Ubuntu' and not server['source_changed_during_validation'])
check('backend_sources_still_match_verification',all(digest(root/'PhotoBlogServer'/name)==value for name,value in server['source_sha256'].items()))
check('django_148_actual_log','Ran 148 tests' in (root/'evidence/content/server/tests-coverage.txt').read_text(encoding='utf-8'))
check('http_15_actual_rerun','Ran 15 tests' in (root/'evidence/content/server/http-api-engine.txt').read_text(encoding='utf-8'))
edge=record('evidence/edge-tests/verification.json')
check('edge_8_actual_wsl_test',edge['pass'] and edge['tests']==8 and all(digest(root/name)==value for name,value in edge['source_sha256'].items()))
android=record('evidence/content/android/verification.json')
check('android_38_jvm_tests',android['unitTests']['passed'] and android['unitTests']['tests']==38)
check('android_build_sources_match',all(digest(root/'PhotoViewer'/item['path'])==item['sha256'] for item in android['source']['files']))
check('lint_warning_count_disclosed',android['lint']['errors']==0 and android['lint']['warnings']==7)
sync=record('evidence/yolo-pipeline/android-sync.json')
pipeline=record('evidence/yolo-pipeline/verification.json')
check('actual_yolo_http_pipeline',pipeline['pass'] and len(pipeline['real_pipeline']['uploads'])==2 and not pipeline['webcam_tested'])
check('native_yolo_photo_proof',sync['list_visible'] and sync['detail_visible'] and sync['image_sha256']==pipeline['real_pipeline']['uploads'][0]['image_sha256']
      and 'OK (1 test)' in (root/'evidence/yolo-pipeline/android-sync-test.txt').read_text(encoding='utf-8'))
runtime=record('evidence/environment/wsl-runtime.json')
check('runtime_dependency_and_cpu_checks',runtime['pass'] and runtime['environment']=='WSL Ubuntu' and runtime['pip_check_exit_code']==0 and runtime['torch_cpu_tensor_ok'])
video=record('evidence/video-flow/verification.json')
check('actual_video_appearance_and_auth_failure',video['pass'] and video['frames']==30 and len(video['uploaded_posts'])==2
      and video['persistent_frames_suppressed'] and video['reappearance_uploaded'] and video['invalid_auth_rejected_and_frame_retained']
      and video['rejected_upload_did_not_change_posts'] and not video['webcam_tested'])
protocol=record(video['cloud_protocol_record'])
check('local_cloud_verifier_not_claimed_as_production',protocol['pass'] and protocol['existing_posts_preserved']
      and protocol['existing_photos_preserved'] and not protocol['production_verified'] and not protocol['source_transition_verified'])
mobile=record('evidence/mobile-flow/verification.json')
check('repeatable_native_and_mobile_web_flow',mobile['native_test_pass'] and mobile['web_captured']
      and mobile['image_sha256']==sync['image_sha256'] and all(digest(root/'evidence/mobile-flow'/item['file'])==item['sha256'] for item in mobile['screenshots']))
traffic=record('evidence/mobile-flow/server-http.json')['requests']
check('actual_mobile_web_http_responses',all(any(item['path']==path and item['status']==200 for item in traffic) for path in ['/', '/post/2/']))
bindings=record('evidence/verification-tools.json')
check('exercised_verification_tools_preserved',all(digest(root/name)==value for name,value in bindings['source_sha256'].items()))
summary={'reviewed_utc':datetime.now(timezone.utc).isoformat(),'report_sha256':digest(report),'checks':checks,
         'integrity_pass':all(item['pass'] for item in checks),'submission_ready':False,
         'complete_assessment_ids':[item['id'] for item in requirements['requirements'] if item['status']=='complete'],
         'unfinished_assessment_ids':[item['id'] for item in requirements['requirements'] if item['status']!='complete'],
         'http_cases_are_subset_of_full_suite':True,'embedded_figures':len(images)}
(root/'evidence/report-review.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in summary.items() if key not in {'checks','report_sha256'}},ensure_ascii=False))
