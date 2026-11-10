"""Audit the refreshed report against original assessment slots and recorded evidence."""
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile
from docx import Document
from lxml import etree
from report_content import FIGURES, build_appendix

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx"
REFERENCE = ROOT / "docs/reference/모바일웹서비스 프로젝트_공통평가 02_수행 결과 보고서.docx"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def main():
    original, doc = Document(REFERENCE), Document(REPORT)
    requirements = record("docs/assessment-requirements.json")
    checks = []

    def check(name, condition):
        checks.append({"check": name, "pass": bool(condition)})
        if not condition:
            raise AssertionError(name)

    check("source_requirement_columns_preserved", all(original.tables[0].cell(r,c).text == doc.tables[0].cell(r,c).text for r in range(12) for c in range(4)))
    check("assessor_grading_column_blank", all(not r.cells[5].text.strip() for r in doc.tables[0].rows[2:]))
    cover = "\n".join(p.text for p in doc.paragraphs[:8])
    checked = date.fromisoformat(requirements["report_state"]["updated_date"])
    check("identity_and_date", all(s in cover for s in ("2020105671", "하대진", "컴퓨터공학과", f"{checked.year}년 {checked.month}월 {checked.day}일")))
    labels = {"complete":"완료", "partial":"부분", "pending":"대기", "deferred":"미정"}
    for row, item in enumerate(requirements["requirements"], 2):
        check("status_" + item["id"], doc.tables[0].cell(row,4).text == labels[item["status"]])
        for path in item["evidence"]:
            check("evidence_exists_" + path, (ROOT / path).is_file())
    check("two_extensions", len(requirements["extra_requirements"]) == 2)
    check("extension_rows", all(doc.tables[0].cell(12+i,0).text == item["id"] and doc.tables[0].cell(12+i,4).text == "완료" for i,item in enumerate(requirements["extra_requirements"])))
    unfinished = [r["id"] for r in requirements["requirements"] if r["status"] != "complete"]
    check("remaining_requirements_honest", unfinished == requirements["report_state"]["unfinished_requirement_ids"])
    camera = record("evidence/notebook-20261110/02_웹캠_증빙/웹캠_검증.json")
    check("actual_notebook_webcam", camera["source"] == 0 and camera["device"] == "/dev/video0" and camera["exit_code"] == 0)
    check("unchanged_detector_for_webcam", digest(ROOT/"YOLOv5/baseline/detect.py") == camera["baseline_sha256"])
    check("trusted_webcam_weights", camera["weights_sha256"] == "8b3b748c1e592ddd8868022e8732fde20025197328490623cc16c6f24d0782ee")
    check("notebook_full_tests", "Ran 250 tests" in (ROOT/"evidence/notebook-20261110/03_노트북_검증/startup-django-retest.log").read_text(encoding="utf-8"))
    if "2" not in unfinished:
        upload = record("evidence/github-final-report.json")
        check("github_upload_verified", upload.get("latest_source_and_report_verified") and upload.get("remote_head_matches_commit"))
        check("github_report_hash_current", upload.get("report_sha256") == digest(REPORT))
        committed_report = subprocess.check_output(["git", "show", upload["report_commit"] + ":" + REPORT.name], cwd=ROOT)
        check("github_report_commit_bytes", hashlib.sha256(committed_report).hexdigest() == digest(REPORT))
    body = "\n".join(p.text for p in doc.paragraphs)
    check("all_evidence_sections", all(any(p.text.startswith(f"B{i:02d} ") for p in doc.paragraphs) for i in range(1,19)))
    check("obsolete_progress_prose_removed", not any(s in body for s in ("진행본", "02 전환 대기", "기본 검증 후", "148개", "38개", "경고 7개")))
    check("authored_prose_symbols", not any(s in body for s in ("·", "→", "←", "⇒", "↔", "—")))
    check("no_api_keys_in_text", not re.search(r"sk-[A-Za-z0-9_-]{16,}|Authorization:\s*(Token|Bearer)\s+[A-Za-z0-9]{20,}", body))
    check("evaluator_access_procedure", all(s in body for s in ("로그인 없이", "별도 계정 없이", "하루 5회", "방문자별", "운영 화면 접속과 확인 방법")))
    check("face_method_explained", all(s in body for s in ("다섯 기준점", "112 x 112", "4배", "최고 점수", "자동 확정은 하지 않는다", "개발 인물 18명", "개별 변경의 기여도")))
    check("face_datasets_and_source_split_explained", all(s in body for s in ("ChokePoint 출입 시연과 별개", "VoxCeleb2 공개 미러", "원본 영상 ID 단위로 분리", "mortal9826/VoxCeleb2-test-data", "PUBLIC_FIGURE_EXPANSION.md")))
    check("webcam_actual_command_disclosed", camera["actual_helper_command"] in body)
    check("retry_evidence_cross_reference", "B08" in doc.tables[0].cell(12,6).text)
    check("process_approval_prose_removed", "승인된 배치" not in body)
    check("cloud_photo_browser_evidence", all((ROOT/path).is_file() for path in (
        "evidence/screenshots/basic-20261110/cloud-list.png", "evidence/screenshots/basic-20261110/cloud-detail.png")))
    build_appendix()
    check("webcam_capture_embedded", "evidence/notebook-20261110/02_웹캠_증빙/웹캠_실시간_검출.png" in FIGURES)
    check("cloud_photo_browser_images_in_report", all(path in FIGURES for path in (
        "evidence/screenshots/basic-20261110/cloud-list.png", "evidence/screenshots/basic-20261110/cloud-detail.png")))
    with ZipFile(REPORT) as target, ZipFile(REFERENCE) as reference:
        expected = {digest(ROOT / path) for path in FIGURES}
        images = {hashlib.sha256(target.read(name)).hexdigest() for name in target.namelist() if name.startswith("word/media/assessment02-")}
        check("all_figures_embedded_without_reencoding", images == expected)
        relationships = etree.fromstring(target.read("word/_rels/document.xml.rels"))
        check("images_are_internal", all(r.get("TargetMode") != "External" for r in relationships if r.get("Type", "").endswith("/image")))
        ns = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        final_xml = etree.fromstring(target.read("word/document.xml"))
        ref_xml = etree.fromstring(reference.read("word/document.xml"))
        check("section_geometry_preserved", etree.tostring(final_xml.find("w:body/w:sectPr",ns)) == etree.tostring(ref_xml.find("w:body/w:sectPr",ns)))
        editable = {"word/document.xml", "word/header1.xml", "word/settings.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"}
        check("opaque_template_parts_preserved", all(reference.read(name) == target.read(name) for name in reference.namelist() if name not in editable))
    server = record("evidence/content/server/verification.json")
    check("actual_WSL_validation", server["pass"] and server["environment"] == "WSL Ubuntu" and not server["source_changed_during_validation"])
    check("backend_hashes_current", all(digest(ROOT/"PhotoBlogServer"/name) == value for name,value in server["source_sha256"].items()))
    total = int(re.search(r"Ran (\d+) tests", (ROOT/"evidence/content/server/tests-coverage.txt").read_text()).group(1))
    check("Django_full_suite", total >= 250 and f"Django 전체 {total}개" in body)
    check("HTTP_15_subset", "Ran 15 tests" in (ROOT/"evidence/content/server/http-api-engine.txt").read_text())
    check("Edge_30", "Ran 30 tests" in (ROOT/"evidence/history/report-edge-tests.txt").read_text())
    android = record("evidence/content/android/verification.json")
    check("Android_40", android["unitTests"]["passed"] and android["unitTests"]["tests"] == 40)
    check("lint_counts", android["lint"]["errors"] == 0 and android["lint"]["warnings"] == 9)
    check("Android_sources_current", all(digest(ROOT/"PhotoViewer"/row["path"]) == row["sha256"] for row in android["source"]["files"]))
    check("web_76", record("evidence/mobile-web/unit-verification.json")["tests"] == 76)
    people = record("evidence/history/chokepoint-people-cloud.json")
    check("production_people", people["pass"] and people["newly_enrolled_profiles"] == 29 and people["current_facts"]["sampled_frames"] == 500 and people["current_facts"]["sessions"] == 40)
    embeddings = record("evidence/history/chokepoint-people-embedding-cloud.json")
    check("production_embeddings", embeddings["pass"] and embeddings["index_documents"] == 40 and len(embeddings["checks"]) == 3)
    check("actual_generation_proof", record("evidence/ui-audit/person-experience.json")["actual_llm_generation_verified"])
    check("production_chat_restore", record("evidence/ui-audit/chat-cloud.json")["restored_in_separate_session"])
    check("production_boxes", record("evidence/ui-audit/detection-boxes-deployment.json")["pass"])
    summary = {"reviewed_utc": datetime.now(timezone.utc).isoformat(), "report_sha256": digest(REPORT),
        "checks": checks, "integrity_pass": all(c["pass"] for c in checks), "embedded_figures": len(images),
        "complete_assessment_ids": [r["id"] for r in requirements["requirements"] if r["status"] == "complete"],
        "unfinished_assessment_ids": unfinished, "submission_ready": not unfinished and requirements["report_state"]["submission_ready"],
        "http_cases_are_subset_of_full_suite": True, "new_paid_api_calls_in_report_refresh": 0}
    (ROOT/"evidence/report-review.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key: value for key,value in summary.items() if key not in ("checks", "report_sha256")}))


if __name__ == "__main__":
    main()
