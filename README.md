# 공통평가 02 객체 검출 사진 블로그

YOLOv5가 객체를 검출하면 Django 사진 블로그에 검출 사진을 등록하고 Android 앱에서 확인한다. 강의의 ChangeDetection 방식에 따라 이전 프레임에 없던 객체 종류가 나타날 때 전송한다. 같은 종류가 계속 보이는 동안에는 전송하지 않으며, 사라졌다가 다시 나타나면 새로 등록한다. 사람의 신원을 구별하거나 침입 여부를 별도로 판정하는 기능은 아니다.

컴퓨터공학과 하대진 2020105671

제출 저장소는 https://github.com/haddol7/mobile_web_service_02 이다. 공통평가 01 저장소와 분리했다.

## 구성

- `PhotoBlogServer` Django 서버와 REST API
- `PhotoViewer` Android 클라이언트
- `YOLOv5` CPU에서 실행하는 Edge 클라이언트
- `docs` 평가 원문에서 정리한 요구사항과 검증 현황
- `evidence` 실제 테스트 결과와 화면 캡처

YOLOv5는 Ultralytics v7.0의 소스를 사용한다. 원본 커밋과 파일 해시는 `docs/upstream/provenance.json`에 기록했다. `YOLOv5/baseline/detect.py`는 수정하지 않은 원본이며 `YOLOv5/detect.py`는 Django 전송을 연결한 코드다. 원본의 GPL-3.0 라이선스는 `YOLOv5/LICENSE`에 있다. 모델은 공식 사전 학습 가중치를 사용하며 별도 학습은 하지 않는다.

## 실행 환경

소스는 Windows에 두고 Django와 YOLO는 WSL Ubuntu에서 실행한다. 본 PC에는 `/home/daeha/.venvs/mobile_web_service_02` 환경을 구성했다. Android 빌드와 에뮬레이터 검증은 Windows에서 한다. Android 패키지 이름은 `com.haddol7.photoviewer.assessment02`이며 01 앱과 함께 설치할 수 있다.

WSL 의존성 준비 스크립트는 `bash tools/setup_edge.sh`다. Python 3.12 이상을 사용하고 Python 패키지는 전용 가상환경에 설치한다. OpenCV 실행에 필요한 WSL의 `libgl1`, `libglib2.0-0`은 본 PC에 준비했다.

## 검출과 서버 전송

WSL에서 이 저장소로 이동한 뒤 실행한다.

```bash
PY=$HOME/.venvs/mobile_web_service_02/bin/python
$PY tools/run_edge.py --baseline --source 0 --device cpu
$PY tools/run_edge.py --source 0 --device cpu --server http://127.0.0.1:8020
```

서버 전송에는 비공개 환경변수 `YOLO_API_TOKEN` 또는 `YOLO_USERNAME`, `YOLO_PASSWORD`가 필요하다. 사용자 이름과 비밀번호를 사용할 때 `/api-token-auth/`에서 토큰을 받은 뒤 `/api_root/Post/`에 multipart JPEG를 등록한다. 이 서버의 인증 방식은 DRF Token이다. 비밀번호와 토큰은 코드, 명령 인자, 보고서, Git 저장소에 넣지 않는다. 원격 서버에는 HTTPS를 사용한다.

웹캠은 WSL에서 `/dev/video*` 장치로 확인되어야 한다. 현재 웹캠은 추후 연결 예정이며 정지 이미지 검증으로 웹캠 증빙을 대신하지 않는다.

## 검증

```bash
PY=$HOME/.venvs/mobile_web_service_02/bin/python
(cd YOLOv5 && $PY -m unittest discover -s tests -p test_changedetection.py -v)
$PY tools/verify_yolo_pipeline.py
(cd PhotoBlogServer && $PY tools/verify_content.py)
```

`verify_yolo_pipeline.py`는 실제 모델로 버스 사진, 같은 사진, 빈 화면, 버스 사진을 순서대로 검출한다. 별도 검증 DB에 게시글 2개가 생기는지, 공개 API의 7개 필드가 유지되는지, 저장한 JPEG와 HTTP로 조회한 JPEG가 일치하는지 검사한다. 이 검증의 DB와 사진은 Git에서 제외한 `evidence/private/local`에 보관한다.

Windows Android 검증은 `PhotoViewer/tools/verify-android.ps1`로 빌드, JVM 단위 테스트, Lint를 실행한다. `YoloSyncTest`는 특정 검출 게시글의 이미지 해시를 확인하고 실제 앱의 목록과 상세 화면을 캡처한다.

## 진행 현황

로컬 YOLO 추론과 Django 등록을 검증했다. Android 빌드와 단위 테스트 38개, Lint가 통과했고 에뮬레이터에서 실제 검출 게시글의 목록과 상세 표시를 확인해 캡처했다. Django 테스트 148개와 HTTP 테스트 15개, Edge 단위 테스트 8개가 통과했다. 웹캠 실측과 PythonAnywhere의 02 운영 확인, 보고서 최종 검토를 이어서 진행한다. 평가용 추가 편의 기능은 기본 동작을 마친 뒤 별도로 선정한다.

PythonAnywhere 전환은 2026년 11월 5일 승인을 받았다. 현재 운영 서버의 핵심 API, 모델, 마이그레이션 16개 파일이 후보와 동일하다. 기존 DB와 미디어를 공유하고 별도 릴리스 및 백업을 만드는 방식이다. 현재는 콘솔 API의 HTTP 412 응답으로 배포 시작 전 단계에서 멈춰 있으며 기존 운영 소스가 유지되고 있다.

코드와 실제 캡처, 현재 검증 내용이 담긴 Word 보고서를 이 저장소에 업로드했다. 보고서의 완료 여부는 확보한 증빙을 기준으로 작성했으며 웹캠과 02 클라우드 검증 항목은 후속 검증 대상으로 표시했다.
