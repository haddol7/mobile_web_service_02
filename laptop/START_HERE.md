# 노트북에서 공통평가 02 실행

Windows 11 x64 노트북을 기준으로 준비한 개인 이전 패키지다. 압축 파일을 노트북의 `C:\Users\사용자\mobile-web-laptop` 같은 로컬 폴더에 완전히 푼다. ZIP 내부에서 바로 실행하지 않는다. Windows에서 소스를 관리하고 WSL2 Ubuntu에서 Python을 실행한다.

## 바로 사용할 기능

웹은 https://daejinha.pythonanywhere.com/ 에 접속해 기존 daejinha 계정으로 로그인하면 된다. 기존 관측 사진 500장, 분석 실행 40개와 등록 인물, 대화 기록은 운영 서버에 유지된다. 노트북으로 서버 DB를 옮기거나 재배포할 필요가 없다. AI 질문을 직접 보내면 기존 운영 서버의 API 설정으로 유료 호출이 발생할 수 있다.

Android용 `laptop/PhotoViewer-02.apk`를 함께 제공한다. Android 휴대폰 또는 Windows Android Emulator에 설치하고 기존 계정으로 로그인한다. iPhone에서는 모바일 웹을 사용한다. Android 소스 수정 및 빌드는 Windows Android Studio, JDK 17 이상, Android SDK 36과 Build Tools 36.1.0 환경에서 수행한다. SDK 경로는 노트북에서 설정하며 기존 컴퓨터의 local.properties는 복사하지 않는다.

## 처음 한 번 환경 설치

`common02\laptop\START.cmd`를 더블클릭하고 1번을 선택한다. WSL2 Ubuntu와 Python 가상환경을 확인하고 프로젝트 의존성을 설치한다. 인터넷이 필요하고 첫 설치에는 시간이 걸린다. Ubuntu에서 요청하는 sudo 비밀번호는 노트북의 Linux 사용자 비밀번호다.

WSL이 없는 노트북에서는 관리자 PowerShell에서 다음을 실행한다.

```powershell
wsl --install -d Ubuntu-24.04
```

재부팅 안내가 나오면 재부팅한다. Ubuntu-24.04를 한 번 열어 Linux 사용자 이름과 비밀번호를 만든 뒤 START.cmd에서 1번을 다시 실행한다. 기존 Ubuntu에서 Python 3.12 미만이면 Ubuntu-24.04를 설치해 사용한다. 기존 배포판은 지우지 않는다.

원하는 배포판을 직접 선택할 수도 있다.

```powershell
.\Start-Laptop.ps1 -Action Setup -Distribution Ubuntu-24.04
```

YOLO 및 Buffalo L 사전 학습 모델, 인물 34명의 등록 사진과 테스트용 출입 영상을 동봉했다. 모델 학습이 필요하지 않다. Python 가상환경은 Ubuntu 사용자 홈의 `~/.venvs/mobile_web_service_02`에 새로 만든다. 다른 PC의 가상환경 폴더는 복사하지 않는다.

## 메뉴 사용

| 번호 | 동작 | 운영 서버 변경 |
|---|---|---|
| 1 | WSL Python 환경과 의존성 설치 | 없음 |
| 2 | 패키지 SHA256, 원본 detect.py, CPU 모델과 등록 사진 검사 | 없음 |
| 3 | 동봉 보행 영상의 사람 추적과 얼굴 후보 비교 | 없음 |
| 4 | 원본 detect.py를 실제 카메라 0번으로 실행 | 없음 |
| 5 | 웹캠 검출 사진과 관측 기록을 운영 서버에 전송 | 새 기록 등록 |
| 6 | 지정 영상의 검출 사진과 관측 기록을 운영 서버에 전송 | 새 기록 등록 |
| 7 | 별도의 빈 DB로 로컬 Django 서버 실행 | 없음 |
| 8 | 기존 운영 웹사이트 열기 | 조회만으로는 없음 |

5번과 6번은 운영자 사용자 이름과 비밀번호를 터미널에서 입력한다. 입력한 비밀번호와 발급 토큰을 파일이나 ZIP에 저장하지 않는다. 배포용 PythonAnywhere API 토큰과 LLM 키는 이전 패키지에 포함하지 않는다. 이 실행 메뉴는 임베딩 생성이나 LLM 테스트를 호출하지 않는다. 새 영상의 의미 검색 색인 갱신은 별도 작업이다.

로컬 실행 결과와 환경 검사 기록은 `common02/.local/laptop/`에 저장한다. YOLO 결과는 `runs` 하위에 쌓이며 기존 실행은 덮어쓰지 않는다. 소스를 수정한 뒤에는 2번의 원본 파일 무결성 검사에서 변경 파일이 표시될 수 있다. 이는 설치 실패와 구분한다.

## 실제 웹캠 확인

Windows에서 카메라가 동작하더라도 WSL에 자동 연결되는 것은 아니다. 4번은 `/dev/video0`가 있고 실제 프레임이 읽히는지 먼저 확인한다. 카메라가 없으면 중단하며 녹화 영상으로 대체하지 않는다. 노트북 카메라가 USB 방식이 아닌 경우 USB/IP 연결이 불가능할 수 있고 추가 드라이버 확인이 필요하다. 현재 PC의 녹화 영상 검사 결과로 노트북 웹캠 검사를 완료 처리하지 않는다.

USB 카메라는 Microsoft의 WSL USB 연결 절차를 따른다. usbipd-win 설치와 장치 공유는 관리자 권한이 필요하다. 먼저 카메라의 실제 BUSID를 확인하고 해당 카메라만 연결한다. 아래의 `BUSID`는 목록에서 확인한 값으로 바꾼다.

```powershell
winget install --interactive --exact dorssel.usbipd-win
usbipd list
# 다음 bind 명령은 관리자 PowerShell에서 실행
usbipd bind --busid BUSID
# Ubuntu를 열어 둔 상태에서 실행
usbipd attach --wsl --busid BUSID
```

Ubuntu에서 `ls /dev/video*`와 `v4l2-ctl --list-devices`로 확인한다. 장치를 붙였는데도 `/dev/video0`가 없으면 USB 인식과 커널 카메라 드라이버 지원을 확인해야 한다. 자동으로 Windows Python으로 전환하지 않는다. WSL에 연결된 카메라는 그동안 Windows 앱에서 사용할 수 없다. 종료 후 `usbipd detach --busid BUSID`로 Windows에 돌려준다.

4번 실행 시 YOLO 창에 사람 또는 물체의 박스와 이름이 표시되는 장면을 캡처한다. 이는 공통평가의 원본 검출기 실시간 카메라 증빙이다. 강의 요구사항과 원본 파일 해시는 유지한다. 5번은 별도로 서버 전송을 확인하는 메뉴다. 카메라가 노트북에서 실제 검증된 뒤 보고서의 웹캠 항목을 갱신한다.

## 로컬 서버 개발

7번은 운영 DB와 분리한 `.local/laptop/db.sqlite3`에 마이그레이션하고 http://127.0.0.1:8020/ 을 연다. 초기에는 게시글과 계정이 없다. 로컬 운영자 계정이 필요하면 Ubuntu에서 아래처럼 생성한다. 비밀번호는 대화형으로 입력한다.

```bash
cd /mnt/c/실제/압축해제경로/mobile_web_service/common02
export DJANGO_DB_PATH="$PWD/.local/laptop/db.sqlite3"
export DJANGO_MEDIA_ROOT="$PWD/.local/laptop/media"
export HISTORY_MEDIA_ROOT="$PWD/.local/laptop/private_tracking"
export HISTORY_LLM_CONFIG=''
~/.venvs/mobile_web_service_02/bin/python PhotoBlogServer/manage.py createsuperuser --username daejinha
```

운영 데이터 조회와 기존 AI 질문은 운영 웹사이트를 사용한다. 로컬 서버에 유료 API 키를 자동 복사하지 않는다. 운영 서버 배포 인증과 GitHub 인증도 새 노트북에서 필요할 때 각각 연결한다.

## 패키지 범위와 검증

최신 작업 폴더의 소스와 공통평가 02 보고서, 모델, Android APK, 등록용 사진 및 테스트용 보행 클립을 포함한다. 전체 원본 영상 아카이브, 사적인 인증 설정, 실시간 DB, 브라우저 로그인 세션, 빌드 캐시는 포함하지 않는다. 등록 사진과 동봉 영상은 기존 프로젝트의 공개 연구 자료이며 자료별 이용 조건을 함께 제공한다. 개인 이전과 수업 시연용으로 보관한다.

이 패키지는 최신 작업본 스냅샷이다. GitHub 원격 저장소는 https://github.com/haddol7/mobile_web_service_02 이며 커밋과 푸시는 별도 작업이다. Codex로 이어서 작업하려면 압축 해제한 `mobile_web_service` 폴더를 열고 `laptop/RESUME.txt`를 전달한다.

공식 설치 안내: https://learn.microsoft.com/windows/wsl/install

공식 USB 연결 안내: https://learn.microsoft.com/windows/wsl/connect-usb
