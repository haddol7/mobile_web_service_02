# 공통평가 02 검증 현황

2026년 11월 10일 기준. 평가 항목별 완료 상태와 증빙은 docs/assessment-requirements.json에 있다. 보고서 구조와 그림 검사는 evidence/report-review.json, 최종 페이지 검수는 evidence/report-layout-review.json에 기록한다.

## 기본 연동

원본 YOLOv5 v7.0과 공식 가중치 해시를 확인하고 사람 4명과 버스 1대를 검출했다. 첫 출현과 연속 장면 및 재등장에 따른 등록을 검증했다. 로컬 API 및 사진 목록, Android와 모바일 웹의 같은 검출 사진 조회를 확인했다.

PythonAnywhere의 실제 YOLO 등록 게시글은 8번이다. 기본 API HTTP 200, 브라우저 사진 목록과 상세, Android 이미지 해시와 표시를 확인했다. 기존 게시글과 계정 및 사진을 보존했다. 증빙은 evidence/cloud, evidence/ui-audit/cloud와 보고서 B09에 있다.

11월 10일 노트북의 Acer HD User Facing 웹캠을 USB/IP로 WSL2 Ubuntu에 연결했다. 실제 /dev/video0를 MJPEG로 읽고 수정하지 않은 원본 검출기로 사람을 검출했다. person 0.71 출력 프레임과 원시 검출값, 원본 해시 및 로그를 확보했다. 전달 파일 18개의 SHA256이 모두 일치했다. 증빙은 evidence/notebook-20261110과 보고서 B08이다.

## 테스트와 환경

- 기존 PC WSL: Django 277개, 실제 HTTP 15개, Edge 30개 통과.
- Windows: 웹 단위 76개, Android JVM 40개, Lint 오류 0개와 경고 9개.
- 노트북 WSL: 전용 가상환경과 CPU 모델, 파일 615개와 등록 사진 73장 검사, Django 250개 및 이전 도구 9개 통과.
- 노트북 실제 입력: 실시간 웹캠 사람 검출과 동봉 영상 240프레임 분석.
- 노트북 로컬 HTTP: /api_root/, /api_root/Post/, /photos/ 모두 200.
- PythonAnywhere: 실제 사진 등록과 Android 조회, 관측 및 인물 이력, 질문 및 대화, 비공개 이미지 권한 확인.

HTTP 15개는 전체 Django 사례의 별도 HTTP 재실행이다. 테스트 총수에 중복 합산하지 않는다. 노트북 카메라 검증과 저장 영상 검사, 기존 PC의 Android 검증은 각각 구분한다.

## 운영 보호

로그인과 관리자 및 토큰 발급의 실패 제한, AI 설명 하루 3회와 임베딩 하루 100회 한도를 구현했다. 한국 시간 자정에 새 한도를 적용하며 카운터는 비공개 SQLite에 유지한다. 보호 상태를 조회하지 못하면 인증과 유료 호출을 차단한다. 기존 250개 검사에 관련 사례 27개를 추가했다. 운영자만 사용량을 조회할 수 있으며 캐시 검색과 대화 복원은 새 유료 호출로 집계하지 않는다.

WSL 전체 277개, 웹 76개와 별도 배포 범위 검사 3개가 통과했다. 실제 모델 호출은 0회다. 구현과 설정은 docs/security-controls.md, 검증은 evidence/security에 있다. 현재 Wi-Fi 회선에서 PythonAnywhere 미국 서버 연결이 거부돼 이 보완 사항의 운영 반영은 대기 상태다. 검증된 패키지를 준비했으며 기존 운영 파일은 유지된 상태다.

## 추가 기능

Edge 인물 추적과 관측 기록 전송, Server 인물 이력과 근거 기록 질의 두 항목이다. 검출 박스, 운영자 확인, 날짜별 이력, 임베딩 검색, 실제 LLM 답변 및 대화 복원이 같은 서비스에서 연결된다.

11월 9일 운영 검증에서 사진 500장, 분석 실행 및 임베딩 문서 각각 40개를 확인했다. ChokePoint 등록 인물은 29명, 전체 갤러리는 34명이다. 일반 구간 정답 대응 359건 중 후보 일치 358건, 보류 1건과 오연결 0건이었다. 검출 표본의 결과이며 전체 검출률과 구분한다. 같은 영상의 재분석은 원본 영상 수에 중복 집계하지 않고 후보와 확인을 구분한다.

기존 실제 LLM 생성과 임베딩 호출은 승인된 실행 기록으로 보존한다. 이번 보고서 마무리와 노트북 검증에서는 유료 AI API를 호출하지 않는다. 근거는 evidence/history, evidence/ui-audit와 docs/testing에 있다.

## 제출

필수 폴더는 PhotoBlogServer, PhotoViewer, YOLOv5이며 보고서는 루트에 둔다. 공통평가 02 전용 저장소는 https://github.com/haddol7/mobile_web_service_02 이다. evidence/github-upload.json은 최초 소스와 보고서의 푸시 검증 기록이다. 최신 보고서의 고정 커밋과 SHA256은 evidence/github-final-report.json에서 확인한다. 이 기록은 해당 커밋의 보고서 원본을 검증하며 이후 검증 기록만 추가한 커밋과 구분한다.
