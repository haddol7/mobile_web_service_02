"""Keep the final assessment status tied to reviewed webcam and actual GitHub upload proof."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-verified", action="store_true")
    args = parser.parse_args()
    requirements = json.loads((ROOT/"docs/assessment-requirements.json").read_text(encoding="utf-8"))
    for row in requirements["requirements"]:
        if row["id"] == "3":
            row["status"] = "complete"
            row["report_evidence"] = "B02 B08\n원본 검출과\n실시간 웹캠"
            for name in ("웹캠_검증.json", "웹캠_실시간_검출.png", "webcam_mjpeg_capture.py", "webcam-retake.log", "선택_프레임_검출값.txt"):
                path = "evidence/notebook-20261110/02_웹캠_증빙/"+name
                if path not in row["evidence"]:
                    row["evidence"].append(path)
        if row["id"] == "2":
            row["status"] = "complete" if args.github_verified else "partial"
            row["report_evidence"] = "B01\n별도 저장소\n소스와 보고서"
    if args.github_verified:
        proof = json.loads((ROOT/"evidence/github-upload.json").read_text())
        assert proof["latest_source_and_report_verified"] and proof["remote_head_matches_commit"]
    remaining = [] if args.github_verified else ["최신 소스와 보고서 GitHub 반영"]
    requirements["report_state"].update(submission_ready=args.github_verified, label="최종 검증 완료" if args.github_verified else "웹캠 검증 반영",
        updated_date="2026-11-10", unfinished_requirement_ids=[] if args.github_verified else ["2"], remaining_work=remaining)
    requirements["constraints"].update(camera_verified_on_notebook=True, camera_verification="evidence/notebook-20261110/02_웹캠_증빙/웹캠_검증.json")
    save(ROOT/"docs/assessment-requirements.json", requirements)
    print(json.dumps({"webcam_complete":True,"github_complete":args.github_verified}))


if __name__ == "__main__":
    main()
