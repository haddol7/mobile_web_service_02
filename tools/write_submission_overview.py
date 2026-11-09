"""Write the current submission overview without changing historical evidence."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = """# 공통평가 02 감시 시스템

컴퓨터공학과 하대진 2020105671

YOLOv5가 새 객체의 출현을 감지하면 Django 서버에 검출 사진을 저장하고 Android와 모바일 웹에서 조회한다. 사람 추적과 얼굴 후보 비교, 인물별 관측 이력 및 근거 기록 질문을 추가했다.

- 운영 주소: https://daejinha.pythonanywhere.com/
- 공통평가 02 전용 저장소: https://github.com/haddol7/mobile_web_service_02
- 보고서: 루트의 `모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx`
- 평가 대응표: [요구사항과 증빙](docs/assessment-requirements.json)
- 검증 기준일: 2026년 11월 10일

## 구성과 기본 기능

| 폴더 | 역할 |
|---|---|
| PhotoBlogServer | Django 서버, REST API, SQLite, 운영자 웹 |
| PhotoViewer | Android 클라이언트 |
| YOLOv5 | 원본 검출기, 객체 출현 비교, 사람 추적과 전송 |
| docs | 평가 요구사항, 실행 설명과 자료 이용 조건 |
| evidence | 실제 실행 결과와 캡처 |
| laptop | 노트북용 실행 메뉴와 검사 |

공통평가 01과 별도 저장소이며 기본 Post API의 7개 필드와 Android 동기화를 유지한다. `YOLOv5/baseline/detect.py`는 변경하지 않은 Ultralytics v7.0 원본이다. 원본 커밋과 파일 해시는 docs/upstream/provenance.json에 있다.

이전 프레임에 없던 객체 종류가 나타나면 320 x 240 JPEG와 검출 내용을 서버에 전송한다. 로컬 및 무료 PythonAnywhere 서버에서 API와 사진 목록을 확인하고 Android에서 같은 사진을 조회한다. 노트북의 실제 카메라 0번을 입력으로 원본 검출기를 실행한 증빙도 포함한다.

## 추가 기능

평가표의 추가 기능은 두 항목으로 구성했다.

1. Edge Client의 인물 추적과 관측 기록 전송: Norfair 몸 추적, Supervision 통과 집계, InsightFace Buffalo L 얼굴 후보 비교, 중복 방지와 재전송.
2. Server의 인물 이력과 근거 기록 질의: 날짜와 인물별 이력, 운영자 확인, 텍스트 임베딩 검색과 LLM 답변 및 대화 복원.

웹과 Android의 메뉴는 관측 기록, 인물 확인, AI 질문이다. 사진에는 몸과 얼굴 검출 박스, 추적 번호 및 후보와 확인 상태를 표시한다. 기존 사진 자료는 /photos/와 Post API에서 조회한다.

11월 9일 운영 검증 기준 사진 500장과 분석 실행 40개를 저장했다. ChokePoint 공식 등록 사진 58장으로 29명을 등록했고 전체 비교 갤러리는 34명이다. 재분석 횟수와 원본 영상 수, 추적 수와 실제 사람 수를 구분한다. 얼굴 후보는 운영자 확인 전까지 확정하지 않는다.

## 실행

Windows에 하나의 소스 트리를 두고 Django와 Python 및 Edge 추론은 WSL2 Ubuntu에서 /mnt 경로로 실행한다. 가상환경은 Linux 홈의 ~/.venvs/mobile_web_service_02에 둔다. Android Studio, Gradle, Emulator와 ADB는 Windows에서 실행한다. 운영은 무료 PythonAnywhere, 모델 추론은 Edge CPU에서 수행한다.

노트북 이전 ZIP을 사용한다면 [노트북 안내](laptop/START_HERE.md)를 따른다. laptop/START.cmd에서 설치, 검사, 영상 분석, 원본 웹캠 실행과 운영 전송을 선택한다. 운영 데이터는 기존 서버에서 조회한다.

소스를 새로 받은 경우 WSL Ubuntu의 프로젝트 루트에서 `bash tools/setup_edge.sh`와 `bash tools/setup_person_analysis.sh`로 공식 가중치와 의존성을 준비한다. Python 3.12 이상 및 Python venv와 빌드 의존성이 필요하다. 가상환경의 Python으로 PhotoBlogServer/manage.py migrate를 실행하고 runserver 127.0.0.1:8020으로 서버를 연다. 로컬 운영자 계정은 createsuperuser --username daejinha로 만든다.

원본 검출은 가상환경의 Python으로 `tools/run_edge.py --baseline --source YOLOv5/data/images/bus.jpg --device cpu`를 실행한다. 실제 카메라는 장치와 프레임을 확인한 뒤 --source 0 --view-img를 사용한다. 노트북의 MJPEG 입력 보조 스크립트와 원본 실행 로그는 evidence/notebook-20261110/02_웹캠_증빙에 있다.

운영 전송에는 --server https://daejinha.pythonanywhere.com 옵션과 비공개 YOLO_API_TOKEN 또는 YOLO_USERNAME 및 YOLO_PASSWORD 환경변수를 사용한다. 이력 전송에는 --person-tracking --person-history를 추가한다. 라이브러리 실행과 등록 사진 구성은 docs/testing/person-libraries.md, 자료 이용 조건은 docs/testing/licenses에 정리했다.

## 검증

| 항목 | 실제 결과 |
|---|---|
| WSL Django | 250개 통과 |
| 실제 HTTP 엔진 | 전체 중 15개를 별도 재실행 |
| WSL Edge | 30개 통과 |
| 웹 단위 | 76개 통과 |
| Windows Android | JVM 40개, Lint 오류 0개 및 경고 9개 |
| 실제 노트북 웹캠 | 카메라 0번, 640 x 480 MJPEG, person 0.71 |
| 노트북 환경 | 파일 615개 및 등록 사진 34명 73장 읽기, Django 250개와 이전 도구 9개 통과 |
| 운영 | 관측 사진 500장, 분석 실행 및 임베딩 문서 각각 40개 |

HTTP 15개는 전체 Django 사례에 포함되므로 중복 합산하지 않는다. 노트북 WSL, 기존 PC의 WSL과 Android, PythonAnywhere 검증을 환경 및 날짜로 구분한다. [검증 현황](docs/verification-status.md)과 evidence의 실제 실행 기록에서 확인할 수 있다.

얼굴 비교는 개발 인물과 겹치지 않는 24명과 원본 576프레임으로 검증했다. 원본 조건의 등록 인물 연결은 104/288에서 272/288로 증가했다. 변형 조건은 같은 프레임에서 파생했으며 모든 환경의 오류율 보장과 구분한다. 설정과 보류 기준은 보고서 B13에 있다.

## AI 질문과 보고서

인물과 날짜 조건을 적용한 뒤 text-embedding-3-small 512차원 벡터와 제목 일치로 관련 영상 최대 5개를 선택한다. 운영 LLM인 gpt-4o-mini는 집계와 근거 기록으로 설명을 작성한다. 질문과 답변은 운영자별로 저장한다.

사용자가 질문을 보내면 유료 검색 및 답변 생성이 연결될 수 있다. 자동 테스트는 모의 처리와 캐시를 사용한다. Codex의 유료 임베딩 및 LLM 테스트는 별도 승인을 받는다. 키는 비공개 설정에 두고 GitHub와 보고서에 포함하지 않는다. PythonAnywhere 배포 인증과 앱 로그인 인증은 별개다.

Word에는 실제 캡처의 원본 바이트가 포함돼 있다. Git에서 제외된 작업용 그림은 문서용 Python 환경에서 tools/restore_report_figures.py로 복원할 수 있다. tools/build_report.py와 tools/audit_report.py는 원본 평가표 보존, 증빙 및 그림 해시를 검사한다. 문서 수정 후 Word 렌더링으로 전체 페이지를 검수한다.
"""

STATUS = """# 공통평가 02 검증 현황

2026년 11월 10일 기준. 평가 항목별 완료 상태와 증빙은 docs/assessment-requirements.json에 있다. 보고서 구조와 그림 검사는 evidence/report-review.json, 최종 페이지 검수는 evidence/report-layout-review.json에 기록한다.

## 기본 연동

원본 YOLOv5 v7.0과 공식 가중치 해시를 확인하고 사람 4명과 버스 1대를 검출했다. 첫 출현과 연속 장면 및 재등장에 따른 등록을 검증했다. 로컬 API 및 사진 목록, Android와 모바일 웹의 같은 검출 사진 조회를 확인했다.

PythonAnywhere의 실제 YOLO 등록 게시글은 8번이다. 기본 API HTTP 200, 브라우저 사진 목록과 상세, Android 이미지 해시와 표시를 확인했다. 기존 게시글과 계정 및 사진을 보존했다. 증빙은 evidence/cloud, evidence/ui-audit/cloud와 보고서 B09에 있다.

11월 10일 노트북의 Acer HD User Facing 웹캠을 USB/IP로 WSL2 Ubuntu에 연결했다. 실제 /dev/video0를 MJPEG로 읽고 수정하지 않은 원본 검출기로 사람을 검출했다. person 0.71 출력 프레임과 원시 검출값, 원본 해시 및 로그를 확보했다. 전달 파일 18개의 SHA256이 모두 일치했다. 증빙은 evidence/notebook-20261110과 보고서 B08이다.

## 테스트와 환경

- 기존 PC WSL: Django 250개, 실제 HTTP 15개, Edge 30개 통과.
- Windows: 웹 단위 76개, Android JVM 40개, Lint 오류 0개와 경고 9개.
- 노트북 WSL: 전용 가상환경과 CPU 모델, 파일 615개와 등록 사진 73장 검사, Django 250개 및 이전 도구 9개 통과.
- 노트북 실제 입력: 실시간 웹캠 사람 검출과 동봉 영상 240프레임 분석.
- 노트북 로컬 HTTP: /api_root/, /api_root/Post/, /photos/ 모두 200.
- PythonAnywhere: 실제 사진 등록과 Android 조회, 관측 및 인물 이력, 질문 및 대화, 비공개 이미지 권한 확인.

HTTP 15개는 전체 Django 사례의 별도 HTTP 재실행이다. 테스트 총수에 중복 합산하지 않는다. 노트북 카메라 검증과 저장 영상 검사, 기존 PC의 Android 검증은 각각 구분한다.

## 추가 기능

Edge 인물 추적과 관측 기록 전송, Server 인물 이력과 근거 기록 질의 두 항목이다. 검출 박스, 운영자 확인, 날짜별 이력, 임베딩 검색, 실제 LLM 답변 및 대화 복원이 같은 서비스에서 연결된다.

11월 9일 운영 검증에서 사진 500장, 분석 실행 및 임베딩 문서 각각 40개를 확인했다. ChokePoint 등록 인물은 29명, 전체 갤러리는 34명이다. 일반 구간 정답 대응 359건 중 후보 일치 358건, 보류 1건과 오연결 0건이었다. 검출 표본의 결과이며 전체 검출률과 구분한다. 같은 영상의 재분석은 원본 영상 수에 중복 집계하지 않고 후보와 확인을 구분한다.

기존 실제 LLM 생성과 임베딩 호출은 승인된 실행 기록으로 보존한다. 이번 보고서 마무리와 노트북 검증에서는 유료 AI API를 호출하지 않는다. 근거는 evidence/history, evidence/ui-audit와 docs/testing에 있다.

## 제출

필수 폴더는 PhotoBlogServer, PhotoViewer, YOLOv5이며 보고서는 루트에 둔다. 공통평가 02 전용 저장소는 https://github.com/haddol7/mobile_web_service_02 이다. 실제 소스 및 보고서 업로드 결과는 evidence/github-upload.json에서 확인한다.
"""

if __name__ == "__main__":
    (ROOT/"README.md").write_text(README, encoding="utf-8")
    (ROOT/"docs/verification-status.md").write_text(STATUS, encoding="utf-8")
    print("Submission overview and verification documentation updated.")
