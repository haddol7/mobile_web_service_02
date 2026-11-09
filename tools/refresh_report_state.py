"""Refresh assessment traceability from existing completed evidence, without API calls."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / "docs/assessment-requirements.json"
    data = json.loads(path.read_text())
    for row in data["requirements"]:
        if row["id"] == "2":
            row.update(status="partial", report_evidence="B01\n별도 저장소\n최신본 업로드 확인")
        elif row["id"] == "3":
            row.update(status="partial", report_evidence="B02 B08\n원본 검출 확인\n웹캠 실측 필요")
        elif row["id"] == "8":
            row.update(status="complete", report_evidence="B09\n운영 API 200")
        elif row["id"] == "9":
            row.update(status="complete", report_evidence="B09 B10\n운영 사진과\n모바일 동기화")
        elif row["id"] == "10":
            row.update(status="complete", report_evidence="B10부터 B17\n추적과 전송\n이력과 AI 질의")
            row["evidence"] = [
                "evidence/history/verification.json", "evidence/history/llm-verification.json",
                "evidence/ui-audit/person-experience.json", "evidence/ui-audit/chat-cloud.json",
                "evidence/history/chokepoint-people-summary.json", "evidence/history/chokepoint-people-cloud.json",
                "evidence/history/chokepoint-people-embedding-cloud.json",
                "evidence/ui-audit/detection-boxes-ui.json", "evidence/ui-audit/detection-boxes-deployment.json"]
    data["extra_requirements"] = [
        {"id": "10-1", "role": "Edge Client", "name": "인물 추적과 관측 기록 전송",
         "description": "몸 추적, 얼굴 후보 비교, 선 통과 기록, 중복 방지와 재전송",
         "status": "complete", "report_evidence": "B11 B12 B17\n등록과 실제 분석\n검출 박스"},
        {"id": "10-2", "role": "Server", "name": "인물 이력과 근거 기록 질의",
         "description": "날짜와 인물별 이력, 확인 상태, 의미 검색과 LLM 답변, 대화 복원",
         "status": "complete", "report_evidence": "B10 B13부터 B16\n운영 조회와 질문\nAndroid 확인"}]
    deployment = json.loads((ROOT / "evidence/ui-audit/detection-boxes-deployment.json").read_text())
    assert deployment["pass"] and deployment["production_verified"]
    data["deployment"].update(release=deployment["release"], verified_date="2026-11-09",
                              verification="evidence/ui-audit/detection-boxes-deployment.json")
    data["report_state"] = {"submission_ready": False, "label": "검증 결과 갱신",
                            "updated_date": "2026-11-09", "unfinished_requirement_ids": ["2", "3"],
                            "remaining_work": ["최신 소스와 보고서 GitHub 반영", "실제 웹캠 실행과 캡처"]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": [r["id"] for r in data["requirements"] if r["status"] == "complete"],
                      "partial": ["2", "3"], "extra_features": 2}))


if __name__ == "__main__":
    main()
