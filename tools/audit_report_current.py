"""Audit the refreshed report against original assessment slots and recorded evidence."""
from datetime import date, datetime, timezone
import argparse
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


def main(local_only=False):
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
    if "2" not in unfinished and not local_only:
        upload = record(requirements["report_state"].get("github_verification", "evidence/github-final-report.json"))
        check("github_upload_verified", upload.get("latest_source_and_report_verified") and upload.get("remote_head_matches_commit"))
        check("github_report_hash_current", upload.get("report_sha256") == digest(REPORT))
        committed_report = subprocess.check_output(["git", "show", upload["report_commit"] + ":" + REPORT.name], cwd=ROOT)
        check("github_report_commit_bytes", hashlib.sha256(committed_report).hexdigest() == digest(REPORT))
    body = "\n".join(p.text for p in doc.paragraphs)
    from report_page_map import section_location
    page_map = record("docs/report-page-map.json")
    check("page_map_bound_to_current_report", page_map["report_sha256"] == digest(REPORT))
    check("page_map_all_sections", set(page_map["sections"]) == {f"B{i:02d}" for i in range(1,38)})
    page_index = next(table for table in doc.tables if table.cell(0,0).text == "평가 항목")
    check("page_index_all_assessment_rows", [row.cells[0].text for row in page_index.rows[1:]] == [str(i) for i in range(1,10)] + ["10-1","10-2"])
    check("printed_page_basis_explained", "문서 하단에 인쇄된 번호" in body)
    check("page_index_basic_code_location", page_index.cell(4,2).text == section_location(["B03"]))
    check("page_index_cloud_image_location", page_index.cell(9,2).text == section_location(["B09"], "B09 3-4", select=lambda pages: pages[-2:]))
    check("page_index_final_RAG_location", "B37" in page_map["sections"] and section_location([f"B{i:02d}" for i in [13,14,15,16,*range(26,38)]], "B13-16, B26-37") == page_index.cell(11,2).text)
    final_generation = record("evidence/history/final-release-generation-20261110.json")
    check("final_release_actual_generation", final_generation["pass"] and final_generation["response"]["llm"]["status"] == "generated" and final_generation["response"]["mode"] == "rag")
    check("one_generation_no_new_embedding", final_generation["generation_http_attempts"] == 1 and final_generation["generation_usage_delta"] == 1 and final_generation["new_embedding_api_requests"] == 0)
    check("final_generation_same_deployed_code", final_generation["active_release_after"]["release"] == requirements["deployment"]["release"] and all(digest(ROOT/"PhotoBlogServer"/path) == value for path,value in final_generation["active_release_before"]["source_sha256"].items()))
    check("actual_generation_displayed", final_generation["response"]["llm"]["text"] in body)
    photo = final_generation["photo_verification"]
    check("final_generation_browser_photo", photo["http_status"] == 200 and photo["browser_image_src_matches_returned_evidence"] and digest(ROOT/photo["capture_path"]) == photo["capture_sha256"])
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
    from report_basic_sections import BASIC_EVIDENCE
    guide = record("docs/basic-evidence-guide.json")
    check("basic_guide_matches_source", guide["figures"] == BASIC_EVIDENCE)
    check("original_basic_ids_covered", guide["requirement_ids"] == [str(i) for i in range(1,10)])
    check("individual_photo_explanations", all(len(row["explanation"]) >= 2 and all(p in body for p in row["explanation"]) for row in BASIC_EVIDENCE))
    captures = record("evidence/basic-verification-20261110/report-expansion-captures.json")
    check("actual_current_VSCode_images", captures["new_source_screenshots"] == 4 and all(
        digest(ROOT / row["path"]) == row["sha256"] and digest(ROOT / row["visible_source"]) == row["source_sha256"]
        for row in captures["screenshots"]))
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
        "unfinished_assessment_ids": unfinished, "submission_ready": not local_only and not unfinished and requirements["report_state"]["submission_ready"],
        "http_cases_are_subset_of_full_suite": True,
        "new_paid_api_calls_in_report_refresh": final_generation["generation_usage_delta"],
        "new_embedding_api_calls_in_report_refresh": final_generation["new_embedding_api_requests"],
        "basic_figures_with_individual_explanations": len(BASIC_EVIDENCE), "github_snapshot_verified": not local_only}
    target = ROOT / ("evidence/private/report-expansion-20261110/local-report-review.json" if local_only else "evidence/report-review.json")
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key: value for key,value in summary.items() if key not in ("checks", "report_sha256")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-only", action="store_true", help="Authoring audit only; leave the public audit and remote snapshot untouched")
    main(local_only=parser.parse_args().local_only)
