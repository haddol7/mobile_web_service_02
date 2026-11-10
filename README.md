# 공통평가 02 감시 시스템

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
| PhotoBlogServer | Django 서버, REST API, SQLite, 관측 조회 웹 |
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
| 기존 PC WSL Django | 11월 10일 302개 통과 |
| 실제 HTTP 엔진 | 전체 중 15개를 별도 재실행 |
| WSL Edge | 30개 통과 |
| 웹 단위 | 76개 통과 |
| Windows Android | JVM 40개, Lint 오류 0개 및 경고 9개 |
| 실제 노트북 웹캠 | 카메라 0번, 640 x 480 MJPEG, person 0.71 |
| 노트북 환경 | 파일 615개 및 등록 사진 34명 73장 읽기, Django 250개와 이전 도구 9개 통과 |
| 출입 영상 검증 | 11월 9일 관측 사진 500장과 분석 실행 40개 |
| 본인 웹캠 연동 | 자동 등록 9번과 재진입 14번의 웹 및 Android 조회, 전송 사진 지문 일치 |
| 본인 RAG | 촬영 문서 추가 후 색인 43개, 회귀 사례 8건과 운영 조회 4건 통과 |

HTTP 15개는 전체 Django 사례에 포함되므로 중복 합산하지 않는다. 노트북 WSL, 기존 PC의 WSL과 Android, PythonAnywhere 검증을 환경 및 날짜로 구분한다. [검증 현황](docs/verification-status.md)과 evidence의 실제 실행 기록에서 확인할 수 있다.

얼굴 비교는 개발 인물과 겹치지 않는 24명과 원본 576프레임으로 검증했다. 원본 조건의 등록 인물 연결은 104/288에서 272/288로 증가했다. 변형 조건은 같은 프레임에서 파생했으며 모든 환경의 오류율 보장과 구분한다. 설정과 보류 기준은 보고서 B13에 있다.

## AI 질문과 보고서

보고서는 56페이지이며 원본 증빙 이미지 53장을 포함한다. B21부터 B25는 본인 웹캠의 서버 자동 등록과 Android 조회, B33부터 B36은 날짜 전체 대조와 부정 조건 안내 및 색인 상태에 따른 조회 범위 유지의 코드와 실행 결과다. 이 RAG 보완 검증의 추가 유료 API 호출은 0회다. 실제 생성 예시와 모의 제공자 및 격리 DB 검사, 운영 캐시 전용 조회는 본문에서 구분한다.

인물과 날짜 조건을 적용한 뒤 text-embedding-3-small 512차원 벡터와 제목 일치로 관련 영상 최대 5개를 선택한다. 운영 LLM인 gpt-4o-mini는 집계와 근거 기록으로 설명을 작성한다. 관측과 인물 조회 및 AI 질문은 로그인 없이 이용할 수 있다. 대화는 로그인 계정 또는 방문자 브라우저 세션별로 분리한다. 데이터 변경은 지정 운영자가 수행한다.

사용자가 질문을 보내면 유료 검색 및 답변 생성이 연결될 수 있다. AI 답변 생성은 서버 전체 한국 시간 기준 하루 5회, 임베딩은 하루 100회로 제한한다. 로그인 시도 횟수 제한은 해제했다. 자동 테스트는 모의 처리와 캐시를 사용한다. Codex의 유료 임베딩 및 LLM 테스트는 별도 승인을 받는다. 키는 비공개 설정에 두고 GitHub와 보고서에 포함하지 않는다. PythonAnywhere 배포 인증과 앱 로그인 인증은 별개다.

Word에는 실제 캡처의 원본 바이트가 포함돼 있다. Git에서 제외된 작업용 그림은 문서용 Python 환경에서 tools/restore_report_figures.py로 복원할 수 있다. tools/build_report.py와 tools/audit_report.py는 원본 평가표 보존, 증빙 및 그림 해시를 검사한다. 문서 수정 후 Word 렌더링으로 전체 페이지를 검수한다.
