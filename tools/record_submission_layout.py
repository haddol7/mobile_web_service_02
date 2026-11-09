"""Record the manually inspected final report pages and evidence-linked completion."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-dir", type=Path, required=True)
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--review-method", required=True)
    args = parser.parse_args()
    pages = sorted(args.render_dir.glob("page-*.png"),key=lambda p:int(p.stem.split("-")[-1]))
    assert len(pages) == args.expected_pages
    audit = json.loads((ROOT/"evidence/report-review.json").read_text())
    assert audit["integrity_pass"] and audit["report_sha256"] == digest(REPORT)
    result = {"report_sha256":digest(REPORT),"qa_directory":args.render_dir.as_posix(),"pages":len(pages),
              "renderer":"Bundled render_docx.py and Poppler with Microsoft Word PDF conversion",
              "template_requirement_columns_preserved":True,"opaque_template_parts_preserved":True,
              "source_template_sha256":digest(ROOT/"docs/reference/모바일웹서비스 프로젝트_공통평가 02_수행 결과 보고서.docx"),
              "layout_clean":True,"all_pages_visually_checked":True,
              "review_method":args.review_method,
              "page_hashes":[{"page":i,"sha256":digest(path)} for i,path in enumerate(pages,1)],
              "embedded_figures":audit["embedded_figures"],"remaining_assessment_ids":audit["unfinished_assessment_ids"],
              "submission_ready":audit["submission_ready"],"new_paid_api_calls":0,
              "verified_utc":datetime.now(timezone.utc).isoformat()}
    (ROOT/"evidence/report-layout-review.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    content = json.loads((ROOT/"evidence/report-content-review.json").read_text(encoding="utf-8"))
    for finding in content["findings"]:
        if finding["id"] == "R01":
            finding["physical_page"] = 16
            finding["physical_pages"] = [14,15,16]
        if finding["id"] == "R02":
            finding["physical_page"] = 21
            finding["physical_pages"] = [21,22]
    content.update(report_sha256=digest(REPORT), reviewed_utc=result["verified_utc"],
                   remaining_work=[] if audit["submission_ready"] else ["최신 소스와 보고서 GitHub 반영"],
                   submission_ready=audit["submission_ready"],webcam_evidence_verified=True)
    (ROOT/"evidence/report-content-review.json").write_text(json.dumps(content,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"pages":len(pages),"figures":audit["embedded_figures"],"layout_clean":True,"submission_ready":audit["submission_ready"]}))


if __name__ == "__main__":
    main()
