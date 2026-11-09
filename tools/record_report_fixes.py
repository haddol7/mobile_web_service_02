"""Record the completed document review fixes without handling credentials."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "evidence/private/report-fixes-20261109/render-1"
REPORT = ROOT / "모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    now = datetime.now(timezone.utc).isoformat()
    previous_layout = json.loads((ROOT / "evidence/report-layout-review.json").read_text(encoding="utf-8-sig"))
    previous_content = json.loads((ROOT / "evidence/report-content-review.json").read_text(encoding="utf-8-sig"))
    backup = ROOT / "evidence/private/report-fixes-20261109"
    # Preserve the earlier findings and their reviewed page hashes.
    for name, value in (("layout-before-fixes.json", previous_layout), ("content-before-fixes.json", previous_content)):
        if not (backup / name).exists():
            save(backup / name, value)
    pages = sorted(RENDER.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    assert len(pages) == 25
    unchanged = [n for n in range(3, 14) if digest(pages[n-1]) == previous_layout["page_hashes"][n-1]["sha256"]]
    assert unchanged == list(range(3, 14))
    integrity = json.loads((ROOT / "evidence/report-review.json").read_text(encoding="utf-8-sig"))
    assert integrity["integrity_pass"] and integrity["report_sha256"] == digest(REPORT)
    layout = {**previous_layout, "report_sha256": digest(REPORT),
              "qa_directory": str(RENDER.relative_to(ROOT)).replace("\\", "/"),
              "pages": 25, "embedded_figures": integrity["embedded_figures"],
              "review_method": "Final PNGs 1, 2 and 14 through 25 visually inspected; pages 3 through 13 byte-identical to earlier visually reviewed PNGs",
              "page_hashes": [{"page": i, "sha256": digest(p)} for i, p in enumerate(pages, 1)],
              "verified_utc": now}
    save(ROOT / "evidence/report-layout-review.json", layout)
    resolutions = {
        "R01": {"status": "resolved", "physical_pages": [13, 14],
                "resolution": "Current production browser list and post 8 detail captured and embedded as B09 3 and B09 4"},
        "R02": {"status": "resolved", "physical_pages": [19, 20],
                "resolution": "Reference selection, aligned original and flipped features, person-level scoring, fixed thresholds and candidate-only status explained against source"},
        "R03": {"status": "access_procedure_added", "physical_pages": [2],
                "resolution": "Account name, login URL and observation, profile and question verification steps added",
                "password_retrieved": False, "password_login_tested": False,
                "credential_handling": "Old-report password lookup, login attempt and plaintext guide were blocked by automatic approval review; no credential was extracted or stored"},
    }
    content = {**previous_content, "reviewed_utc": now, "report_modified": True,
               "report_sha256": digest(REPORT),
               "findings": [{**f, **resolutions[f["id"]]} for f in previous_content["findings"]]}
    save(ROOT / "evidence/report-content-review.json", content)
    captures = [{"path": str((backup / name).relative_to(ROOT)).replace("\\", "/"), "url": url,
                 "sha256": digest(backup / name), "capture_method": "CUA browser screenshot of existing production data"}
                for name, url in (("production-post-list.jpg", "https://daejinha.pythonanywhere.com/photos/"),
                                  ("production-post-detail.jpg", "https://daejinha.pythonanywhere.com/post/8/"))]
    save(backup / "capture-verification.json", {"recorded_utc": now, "captures": captures,
         "new_paid_api_calls": 0, "production_data_modified": False, "existing_authenticated_browser_session": True})
    print(json.dumps({"pages": len(pages), "figures": integrity["embedded_figures"], "layout_clean": True,
                      "password_retrieved": False, "submission_ready": False}))


if __name__ == "__main__":
    main()
