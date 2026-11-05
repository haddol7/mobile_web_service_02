# 공통평가 02 객체 검출 사진 블로그

현재 보고서는 진행본이다. 웹캠 실측과 PythonAnywhere 검증을 마친 뒤 최종 확정한다.

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
$PY tools/verify_video_flow.py
$PY tools/check_environment.py
(cd PhotoBlogServer && $PY tools/verify_content.py)
```

`verify_yolo_pipeline.py`는 실제 모델로 버스 사진, 같은 사진, 빈 화면, 버스 사진을 순서대로 검출한다. 별도 검증 DB에 게시글 2개가 생기는지, 공개 API의 7개 필드가 유지되는지, 저장한 JPEG와 HTTP로 조회한 JPEG가 일치하는지 검사한다. 이 검증의 DB와 사진은 Git에서 제외한 `evidence/private/local`에 보관한다.

Windows Android 검증은 `PhotoViewer/tools/verify-android.ps1`로 빌드, JVM 단위 테스트, Lint를 실행한다. `YoloSyncTest`는 특정 검출 게시글의 이미지 해시를 확인하고 실제 앱의 목록과 상세 화면을 캡처한다.

빌드 후 Windows에서 다음 명령으로 검증용 WSL 서버 실행, 앱 설치, 실제 게시글 조회와 이미지 해시 검사, 모바일 웹 캡처를 함께 수행한다. 작업이 끝나면 이 명령이 실행한 서버는 종료된다. Android 에뮬레이터가 실행 중이어야 하며 Chrome 최초 실행 동의는 사용자가 직접 완료해야 한다.

```powershell
./tools/verify-mobile-flow.ps1 -CaptureWeb
```

`verify_video_flow.py`는 30프레임의 실제 영상 입력에서 중복 전송 억제와 재등장 시 전송을 검증한다. 인증 실패 시 게시글이 추가되지 않고 사진이 로컬에 남는지도 검사한다. 임시 DB를 사용하므로 기존 검증 게시글이나 운영 게시글에 영향을 주지 않는다. 클라우드 검사 도구의 HTTP 등록과 기존 데이터 보존 절차도 이 임시 서버에서 확인하며 운영 검증으로 집계하지 않는다.

`check_environment.py`는 WSL 전용 가상환경, CPU 연산, OpenCV, 공식 모델 파일 해시와 pip 의존성을 확인한다. 검증 기록은 각각 `evidence/video-flow`, `evidence/mobile-flow`, `evidence/environment`에 저장한다.

`tools/verify_cloud_pipeline.py`는 지정된 PythonAnywhere API에 검출 사진을 등록하고 기존 게시글과 사진의 바이트가 유지되는지 확인하는 도구다. 사용자에게서 별도로 제공받은 앱 API 인증 설정만 사용한다. 비공개 WSL 홈의 `~/.config/mobile-web-service/common02/edge-auth.json`에 `base_url`, `username`, `token` 설정이 필요하며 현재는 이 설정이 없다. 설정 없이는 업로드를 시도하지 않는다. PythonAnywhere 배포 API 인증과 블로그의 게시글 등록 인증은 별개다.

## 진행 현황

로컬 YOLO 추론과 Django 등록을 검증했다. Android 빌드와 단위 테스트 38개, Lint 오류 0개와 경고 7개를 확인했고 에뮬레이터에서 앱과 모바일 웹의 목록 및 상세 화면을 캡처했다. Django 테스트 148개와 Edge 단위 테스트 8개가 통과했다. HTTP 15개는 전체 148개 중 별도 엔진으로 재실행한 사례다. 실제 영상 30프레임에서도 첫 출현과 재등장에서만 총 2개가 등록됐고 인증 실패 처리도 확인했다. 웹캠 실측과 PythonAnywhere의 02 운영 확인은 남아 있다. 평가용 추가 편의 기능은 기본 동작을 마친 뒤 별도로 선정한다.

PythonAnywhere 전환은 2026년 11월 5일 승인을 받았다. 현재 운영 서버의 핵심 API, 모델, 마이그레이션 16개 파일이 후보와 동일하다. 기존 DB와 미디어를 공유하고 별도 릴리스 및 백업을 만드는 방식이다. 현재는 콘솔 API의 HTTP 412 응답으로 배포 시작 전 단계에서 멈춰 있으며 기존 운영 소스가 유지되고 있다.

코드와 실제 캡처, 현재 검증 내용이 담긴 Word 보고서를 이 저장소에 업로드했다. 보고서의 완료 여부는 확보한 증빙을 기준으로 작성했으며 웹캠과 02 클라우드 검증 항목은 후속 검증 대상으로 표시했다.
