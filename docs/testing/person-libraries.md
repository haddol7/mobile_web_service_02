# YOLOv5 라이브러리 적용 기록

2026년 11월 8일 Windows 소스 트리를 WSL Ubuntu의 전용 가상환경에서 실행했다. 기존 YOLOv5 검출 결과에 Norfair 2.3.0, Supervision 0.31.5와 InsightFace 2.1을 연결했다. 추적 진단에는 motmetrics 1.4.0을 사용한다. 모델은 공식 사전 학습 가중치이며 추가 학습은 없다.

## 적용한 동작

YOLOv5의 원본 이미지 좌표 사람 상자를 Norfair에 전달한다. 추적기는 영상 내 번호를 만들고 Supervision이 번호와 상자를 표시한다. 선택한 기준선의 통과도 Supervision으로 집계한다. 사람 이외 객체의 기존 표시, 객체 종류 출현 비교와 사진 전송을 유지한다.

얼굴 참조를 지정하면 InsightFace가 원본 프레임의 얼굴을 검출하고 정렬해 특징을 비교한다. 결과는 후보 또는 보류다. 얼굴과 전신 상자의 대응이 하나로 정해질 때만 추적 번호를 붙인다. 얼굴이 겹치는 두 사람 중 하나에게 강제로 연결하지 않는다. 얼굴 검출과 인식 모듈만 사용한다.

스트림마다 추적 상태를 분리한다. 실제 검출로 갱신되지 않은 예측 상자는 통과 집계에서 제외한다. 실행 결과 폴더의 `person-analysis`에는 세션, 프레임, 영상 내 상대 시각, 처리 시각, 추적 상자, 얼굴 후보와 통과 사건 번호를 JSONL로 기록한다. 처리 시각을 영상의 실제 촬영 시각으로 취급하지 않는다.

## 설치와 실행

기존 NumPy 1.26.4와 OpenCV 4.10 제약을 유지한다. 모델은 WSL 사용자 홈의 `.insightface`에 저장된다.

```bash
cd /mnt/c/Users/1/mobile_web_service/common02
bash tools/setup_person_analysis.sh
PY=$HOME/.venvs/mobile_web_service_02/bin/python

$PY tools/run_edge.py --source /path/to/video.mp4 --device cpu \
  --person-tracking --count-line 0.5 0 0.5 1

$PY tools/run_edge.py --source /path/to/video.mp4 --device cpu \
  --person-tracking --face-references /path/to/references.json \
  --face-model buffalo_l --face-stride 5
```

얼굴 비교의 기본 모델은 선택한 Buffalo L이다. 설치 스크립트도 같은 모델을 준비하며 실행 코드에서도 자동 다운로드를 지원한다. 기존 소형 모델 비교는 검증 도구에서 Buffalo S를 명시해 재현한다.

```bash
$PY tools/prepare_person_models.py --model buffalo_l
```

참조 이미지 경로는 JSON 파일의 위치를 기준으로 읽는다. 프로필에는 유효한 얼굴 사진이 하나 이상 필요하다. 현재 등록 정책은 작은 배경 얼굴을 제외하고, 주 얼굴의 면적이 다음 얼굴의 4배 이상이면 주 얼굴을 선택한다. 비슷한 크기의 얼굴이 여럿이면 대상 영역을 지정해야 한다. 선택할 수 없는 사진은 사유를 기록한다. 아래 ID는 지정한 서비스 식별자다.

```json
{
  "schema_version": 1,
  "profiles": [
    {"id": "reference-001", "images": ["front.jpg", "side.jpg"]}
  ]
}
```

`--server`를 함께 지정하면 기존 인증과 객체 출현 사진 등록을 사용한다. 인증 정보는 기존 비공개 환경변수로 전달한다. 기준선의 `in`, `out`은 끝점 순서에 따른 방향이며 실제 출입구의 입장과 퇴장은 설치 장면에서 정한다.

## 실제 검증

| 검사 | 결과 |
| --- | --- |
| 의존성 | `pip check` 통과. 기존 NumPy, OpenCV, PyTorch 유지 |
| 원본 검출기 | `baseline/detect.py`와 공식 YOLO 모델 해시 유지 |
| Edge 테스트 | 기존 8개와 새 11개, 총 19개 통과 |
| Django 테스트 | `manage.py test --noinput` 148개 통과 |
| 실제 보행자 영상 | TUD-Campus 71프레임, TUD-Stadtmitte 179프레임. 결과 영상 전체 디코딩 확인 |
| 라이브러리를 켠 HTTP 전송 | 30프레임 중 첫 출현과 재등장 사진 2건 등록. 연속 출현 중복 억제와 인증 실패 처리 확인 |
| 기존 실행 경로 | 추적을 끈 동일 30프레임 전송 시험 통과 |

정규화한 유효 정답과 IoU 0.5를 사용한 추적 진단에서 IDF1은 TUD-Campus 0.6395, TUD-Stadtmitte 0.7248이다. ID 변경은 각각 5회와 8회다. 평가 범위는 공식 MOT 리더보드와 구분한다. 트랙 번호 22개와 19개는 실제 사람 수가 아니다. 중앙 세로선의 통과 로그는 5건과 2건이며, 선의 사건 정답과 비교하는 평가는 후속 범위다.

## 얼굴 모델 비교

VoxCeleb2에서 두 인물의 등록 영상과 원본 영상 ID가 다른 질의 영상을 사용했다. 미등록 인물 한 명도 포함했다. 등록 사진은 각 등록 영상의 사전에 정한 세 프레임, 질의는 클립마다 균등 추출한 7프레임이다. 독립 질의 클립은 3개다. 질의 파일명은 해시로 바꾸고 정답은 별도 로컬 파일에 보관한다.

| 모델 | 등록 인물 첫 클립 | 등록 인물 둘째 클립 | 미등록 인물 클립 |
| --- | --- | --- | --- |
| Buffalo S | 후보 0건, 보류 7건 | 후보 0건, 보류 8건 | 후보 0건, 보류 7건 |
| Buffalo L | 올바른 후보 5건, 보류 2건 | 올바른 후보 1건, 보류 7건 | 후보 0건, 보류 7건 |

얼굴 검출 결과는 총 22건으로 21프레임과 다른 집계 단위다. 후보는 작은 자료의 클립 정답으로 확인했다. 두 모델에 같은 사진과 질의, 유사도 0.55와 서로 다른 프로필 간 차이 0.08을 사용했다. 이 기준은 서비스 정확도를 보장하는 보정값이 아니다. Buffalo L도 보류가 많다. 이번 결과는 모델 선택과 연동 확인용이며 새로운 인물로 구성할 최종 정확도 평가와 구분한다. 자동 동일인 확정은 켜지 않는다.

초기 연결의 640 고정 입력에서는 크게 잘린 참조 얼굴 일부를 찾지 못했다. InsightFace 2.1 기본 Auto는 128과 640 입력을 함께 사용한다. 이를 적용한 뒤 참조 6장 모두 검출했다. 소형 모델의 낮은 연결 점수는 별도로 기록하고 큰 모델과 같은 기준으로 비교했다.

## 증빙과 재검증

- `evidence/person-libraries/environment.json`, `environment-buffalo_l.json`: 실제 패키지, CPU 제공자와 모델 해시
- `evidence/person-libraries/unit-tests.json`, `unit-tests.txt`: 실제 Edge 테스트
- `evidence/person-libraries/integration.json`: YOLOv5 영상 처리와 추적 진단, 소형 모델 결과
- `evidence/person-libraries/face-model-comparison.json`: 동일 조건의 대형 모델 비교
- `evidence/person-libraries/upload-flow/verification.json`: 라이브러리를 켠 로컬 HTTP 등록
- 원본과 결과 영상, 참조 사진, 개별 로그: Git에서 제외한 `evidence/private/person-libraries`

```bash
(cd YOLOv5 && $PY -m unittest discover -s tests -v)
$PY tools/verify_person_libraries.py
$PY tools/compare_pretrained_faces.py
$PY tools/verify_video_flow.py --person-tracking
```

재사용한 공식 구현은 [Norfair YOLOv5 예제](https://github.com/tryolabs/norfair/tree/master/demos/yolov5), [Supervision](https://github.com/roboflow/supervision), [InsightFace](https://github.com/deepinsight/insightface/tree/master/python-package), [motmetrics](https://github.com/cheind/py-motmetrics)다. 라이선스는 각각 BSD 3-Clause, MIT, MIT, MIT이며 InsightFace 제공 모델의 비상업 연구용 조건은 코드 조건과 구분한다.

아래에 기록한 초기 적용 위치는 WSL Edge다. 이후 Django 이력 저장, Android 및 모바일 웹 조회와 DB 기반 질문 답변을 연결했다. 실제 LLM 생성과 PythonAnywhere, 실물 웹캠 검증 상태는 각각 구분한다.

## 2026년 11월 8일 기본 모델 적용

검출기 실행 인자, 얼굴 참조 비교와 모델 준비 도구의 기본값을 Buffalo L로 통일했다. 소형 모델 실험 도구는 Buffalo S를 명시해 기존 비교 조건을 유지한다.

WSL 전용 가상환경에서 `python -m unittest discover -s tests -v`를 YOLOv5 폴더에서 실행해 19개를 통과했다. `python tools/prepare_person_models.py`는 인자를 생략한 상태에서 Buffalo L의 검출과 인식 모델을 CPU로 로드했다. `python tools/verify_video_flow.py --person-tracking`은 실제 영상 30프레임을 처리하고 임시 Django 서버에 출현과 재등장 사진 2건을 등록했다. 연속 출현 억제, 잘못된 인증 거부와 실패 사진 보존도 통과했다. 이 전송 검사는 얼굴 참조를 지정하지 않은 추적 경로의 회귀 검사다. 얼굴 비교의 실제 영상 결과는 위 모델 비교 기록을 따른다.

이 단계의 검증은 Edge 실행 설정에 해당한다. 이후 연결한 이력 기능은 다음 절에 기록한다.

## 이력 저장과 기록 질의 연결

프로필, 실행 세션, 추적 번호, 확인 사진, 관측과 통과 사건을 별도 테이블로 저장한다. 기존 Post 필드와 등록 API는 유지한다. 마이그레이션 0005는 새 테이블과 제약만 추가한다. 서버에는 영상 인식 모델을 설치하지 않는다.

추적 번호는 세션 안에서만 유효하다. 얼굴 후보와 운영자 확인은 별도 필드이며 확인은 다른 세션으로 자동 전파하지 않는다. 확인 수정에는 revision을 사용한다. 촬영 시각이 없는 영상은 날짜 미상으로 저장하고 영상 상대 시각과 처리 시각을 구분한다. 실시간 영상은 프레임 수신 시각을 기록한다.

Edge의 `--person-history`는 기존 인증을 사용한다. 새 추적 번호, 후보 변경, 선 통과와 주기적 관측을 전송한다. 기본 주기는 영상 시각 10초다. 사진 전송은 기존 객체 출현 조건을 유지한다. 실패한 이력 패킷과 JPEG는 실행 폴더의 history-outbox에 남기며 토큰은 저장하지 않는다. 동일 기록 재전송은 중복을 만들지 않고 내용이 달라지면 HTTP 409로 거부한다. 재전송 도구는 지정한 인증 서버가 대기 패킷의 서버와 같은지도 검사한다.

```bash
$PY tools/run_edge.py --source /path/to/video.mp4 --device cpu \
  --server http://127.0.0.1:8020 --person-history \
  --count-line 0.5 0 0.5 1 --face-references /private/references.json
$PY tools/retry_person_history.py --server http://127.0.0.1:8020 \
  --outbox /path/to/run/history-outbox
```

촬영 시작 시각을 확인한 영상에만 `--recording-start 2026-11-08T09:00:00+09:00`처럼 지정한다. 예시 날짜를 실제 수집 영상의 촬영 날짜로 간주하지 않는다.

운영자 로그인 후 /history/에서 인물, 날짜와 후보 포함 여부로 조회한다. 모바일에서는 사진을 두 열로 표시하고 확인 창에서 추적 번호와 인물 연결을 검토한다. 이력 사진은 공개 media 경로와 분리하고 운영자 인증을 거쳐 조회한다. Android 앱에도 관측 기록 탭, 조회 조건, 질문과 인물 확인을 연결했다.

질문의 날짜와 인물 조건으로 ORM을 조회하고 통과 건수, 추적 기록 수, 확인된 프로필 수와 날짜를 직접 계산한다. 답변에는 근거 사진을 최대 12개 제공한다. 일부 사진만 화면에 보여도 집계는 전체 조회 조건에 대해 계산한다. 숫자와 날짜가 포함된 SQL을 LLM이 작성하거나 실행하지 않는다. 기록 없음은 실제 부재의 증거로 단정하지 않는다.

선택형 LLM 생성 경로는 조회한 숫자와 날짜 및 근거 기록 ID만 전달한다. 사진과 얼굴 특징 벡터는 전달하지 않는다. 11월 8일 기존 프로젝트의 사용자 승인 키를 WSL 홈의 비공개 설정에 연결해 OpenAI gpt-4o-mini를 실제 호출했다. Gemini 연결 경로도 유지하며 제공사와 모델은 서버 설정으로 선택한다. 외부 호출 실패 시에도 정식 DB 조회 결과는 유지한다.

| 환경과 명령 | 실제 결과 |
| --- | --- |
| WSL PhotoBlogServer에서 `HISTORY_LLM_CONFIG= python manage.py test --noinput` | Django 181개 통과. 이력 및 LLM 응답 검증 포함 |
| WSL YOLOv5에서 `python -m unittest discover -s tests -v` | Edge 24개 통과. 이력 전송 5개 포함 |
| WSL `python tools/verify_person_history.py` | 보행자 71프레임과 얼굴 영상 7프레임 처리. 2세션, 확인 사진 37장, 추적 번호 23개와 통과 사건 6건 저장 |
| 실제 HTTP 응답 유실과 재전송 | 저장 후 503을 주입하고 재전송. 중복 1건을 기존 기록으로 반환, 대기 패킷 0건 |
| 실제 조회와 질문 API | 집계와 DB 일치, 근거 사진 인증, 확인 수정 및 revision 충돌 확인 |
| Windows Android 빌드와 검증 | 단위 테스트 38개, Lint 오류 0개 |
| 실제 Android API35 기기 테스트 | 네이티브 앱과 WebView 2개 검사. 목록, 질문과 근거 확인 화면 캡처 |

숫자 23은 세션별 추적 번호 수이고 실제 서로 다른 사람 수가 아니다. 얼굴 후보 트랙은 1개이며 서비스 신원 판별 정확도를 측정한 결과와 구분한다. 이력 사진 37장은 촬영 날짜가 알려지지 않은 원본에서 생성했으므로 날짜 미상을 유지했다.

증빙은 `evidence/history/verification.json`, `mobile-verification.json`, `android-test.txt`와 `device-server-http.json`이다. 원본 데이터, 격리 DB, 기기 인증과 캡처는 Git에서 제외한 `evidence/private/history`에 보관한다. YOLO 전송 검사와 별도로 실제 LLM 호출 결과를 `llm-verification.json`에 기록했다. PythonAnywhere 배포는 이 로컬 검증에 포함하지 않는다.

실제 LLM 연결에서는 질문과 ORM 조회 결과를 제공하고 JSON 스키마로 답변과 조회된 근거 ID만 받는다. 첫 검사에서 모델이 후보 추적 수를 실제 사람 수로 잘못 설명해 이 응답을 수용하지 않았다. 필드 의미를 명시하고 숫자로 된 사람 수 추정을 거부하는 검사를 추가했다. 또 근거 ID를 누락한 응답이 있어 스키마에 허용된 ID 목록과 인용 개수 조건을 지정했다. 수정 후 실제 질문 3개는 통과 6건, 촬영 날짜 미상, 지정 날짜의 기록 없음으로 올바르게 설명했다. 등록된 사람 수나 방문 횟수는 이 자료만으로 추정하지 않도록 한다. 수량과 근거 ID 검사는 자유 문장의 모든 의미가 맞음을 보장하지 않으므로 정식 DB 집계 답변을 함께 표시한다.

API 키는 WSL 홈에 권한 600으로 보관한다. 키 값과 원본 프로젝트의 설정 파일은 저장소와 보고서에 포함하지 않는다. OpenAI 공식 [Chat Completions 명세](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)와 [Structured Outputs 안내](https://developers.openai.com/api/docs/guides/structured-outputs)를 기준으로 요청을 작성했다. 무료 PythonAnywhere의 공식 허용 목록에 `api.openai.com`이 있으나, 목록 확인을 실제 운영 서버의 호출 성공으로 처리하지 않는다.

## 오바마 클립 동일인 후보 비교

2026년 11월 8일 WSL 전용 가상환경에서 `python -u tools/verify_obama_identity.py`를 실행했다. HDTF 미러의 BarackObama_001.mp4에서 사전에 고정한 0, 124, 247프레임을 등록하고 BarackObama_044.mp4의 248프레임 전체를 실제 YOLOv5와 Buffalo L로 처리했다. 등록 사진과 픽셀이 완전히 같은 비교 프레임은 0개였다.

오바마 외에 기존 VoxCeleb2 등록 인물 두 명도 경쟁 프로필로 유지했다. 총 3프로필과 9장의 등록 사진이며 모두 유효하게 로드했다. 비교 파일명은 해시로 바꾸고 정답 라벨은 채점에만 사용했다. 기존 유사도 0.55와 서로 다른 프로필 간 차이 0.08을 변경하지 않았다.

| 비교 입력 | 전체 프레임 | 올바른 주 얼굴 후보 | 잘못 연결한 주 얼굴 후보 | 주 얼굴 보류 | 오바마로 연결 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 오바마 비교 클립 | 248 | 248 | 0 | 0 | 248 |
| 등록 대조 인물 A | 199 | 182 | 0 | 17 | 0 |
| 등록 대조 인물 B | 103 | 57 | 0 | 46 | 0 |
| 미등록 대조 인물 C | 106 | 0 | 0 | 106 | 0 |

모든 프레임에서 얼굴이 검출됐다. 표의 주 얼굴은 프레임에서 가장 넓은 검출 얼굴 하나로 사전에 정했다. 등록 대조 인물 B에서 추가 검출 7건이 있어 전체 얼굴 검출은 663건이고 주 얼굴 판정은 656건이다. 다른 인물에서 검출한 모든 얼굴을 확인해도 오바마 후보는 0건이었다.

오바마 주 얼굴의 유사도는 최소 0.80646, 중앙값 0.92116, 최대 0.96475였다. 이 중 246건은 YOLO 사람 추적 번호 하나와 연결됐고 초기 추적 준비 중 2건은 얼굴 후보만 기록했다. 결과 영상 네 개는 전부 다시 디코딩해 656프레임이 저장됐는지 확인했다. 모델 학습, 운영 서버 변경과 자동 신원 확정은 수행하지 않았다.

두 오바마 클립은 같은 원본 촬영의 분할일 가능성이 있다. 이번 시험은 그 조건에서의 실제 연동 결과이며 다른 촬영, 의상이나 날짜에서도 같은 정확도를 보장하는 시험으로 집계하지 않는다. 프레임이 연속되어 있으므로 248명을 독립적으로 평가한 자료로도 세지 않는다.

집계와 파일 및 코드 해시는 `evidence/person-libraries/obama-identity.json`에 보관한다. 등록 사진, 판정 로그, 전체 결과 영상과 실제 프레임으로 만든 비교 그림은 Git에서 제외한 `evidence/private/person-libraries/obama`에 보관한다.

## 새 인물 ID와 영상으로 확대한 검증

2026년 11월 8일 기존 VoxCeleb2 시험의 3개 인물 ID를 제외하고 18개 ID를 새로 선택했다. 자료는 이전에 사용한 공개 미러의 고정 리비전에서 받았다. 인물별 원본 영상 ID가 3개 이상인 ID를 정렬해 앞의 12개는 등록 대상으로, 다음 6개는 미등록 대상으로 고정했다. 영상과 모델 결과를 보고 쉬운 사람으로 교체하지 않았다.

등록 대상은 첫 원본 영상의 첫, 중간, 마지막 프레임 3장으로 등록을 시도했다. 비교용 원본 영상은 다른 ID 두 개씩이다. 미등록 인물도 서로 다른 원본 영상 두 개씩을 사용한다. 총 48개 영상을 받아 5,752프레임 전체를 디코딩했다. 비교 영상은 36개이고, 각 영상의 시작과 끝을 포함해 균등하게 선택한 12프레임씩 총 432프레임을 판정했다.

기준은 실행 전에 `expanded-face-protocol.json`에 고정했다. Buffalo L과 유사도 0.55, 프로필 간 차이 0.08을 유지했다. 프레임에서 가장 넓은 얼굴 하나를 주 얼굴로 집계한다. 원본, 밝기를 35%로 줄인 조건, 긴 변을 64픽셀로 축소했다가 원래 크기로 돌린 조건을 적용했다. 총 1,296건은 432개 원본 프레임에 세 조건을 적용한 수이며 독립적인 사람이나 촬영 1,296건이 아니다.

이 시험은 서비스가 사용하는 실제 FaceReferences.analyze와 match_embedding을 WSL CPU에서 실행한 얼굴 비교 모듈 검증이다. 이번 묶음에서 YOLO 본체와 DB 전송을 다시 실행한 것으로 집계하지 않는다. 기존 YOLO와 저장 API의 실제 영상 검증은 앞 절의 기록을 따른다.

| 조건 | 등록 대상 12명의 비교 프레임 | 올바른 후보 | 보류 | 잘못 연결한 후보 | 등록 실패 포함 연결률 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 원본 | 288 | 78 | 210 | 0 | 27.1% |
| 저조도 변형 | 288 | 70 | 218 | 0 | 24.3% |
| 저해상도 변형 | 288 | 61 | 227 | 0 | 21.2% |

미등록 6명의 비교 프레임은 조건마다 144개다. 세 조건 모두 144개를 보류했고 잘못된 후보는 0개였다. 모든 비교 조건에서 주 얼굴을 검출했으므로 위 보류는 얼굴 미검출로 생긴 결과가 아니다.

등록 대상 12명 중 11명이 등록됐다. 나머지 1명의 기준 사진 3장에서는 앞의 큰 얼굴과 배경의 작은 얼굴이 함께 검출돼 얼굴 1개 조건을 통과하지 못했다. 이 인물을 숨기거나 다른 인물로 교체하지 않고 표의 분모에 포함했다. 등록에 성공한 11명만 계산하면 원본 78/264인 29.5%, 저조도 70/264인 26.5%, 저해상도 61/264인 23.1%다.

등록된 인물의 원본 조건 보류 186건은 모두 최고 유사도가 0.55보다 낮았다. 그중 프로필 간 차이 0.08도 못 넘은 것은 5건이다. 원본 조건의 최고 유사도 중앙값은 약 0.489다. 문제를 얼굴 검출 누락이나 프로필 간 점수 차이만으로 설명할 수 없다. 등록된 사람을 다시 연결하지 못하는 비율이 크다는 것이 현재 결과의 핵심이다.

원본 조건에서 등록 대상의 비교 영상 24개 중 올바른 후보가 한 번이라도 나온 것은 11개다. 미등록 비교 영상 12개에는 잘못된 후보가 한 번도 나오지 않았다. 따라서 작은 시험의 오연결 0건만으로 안정적인 자동 신원 확정을 검증했다고 표현하지 않는다. 등록 대상 얼굴 선택, 참조 사진의 조건 다양성과 별도 조정 자료를 통한 기준 보정이 후속 개선 대상이다. 이번 검증 결과를 좋게 만들기 위한 기준 변경은 하지 않았다.

대표 프레임을 등록 사진과 비교 영상별로 배열한 검토 이미지 3장을 확인했다. 각도, 수염과 머리 모양, 배경과 화질의 차이가 보이며, 등록 실패 사례의 배경 얼굴도 확인했다. 일부 장면은 비슷한 복장과 배경을 보여 원본 영상 ID가 달라도 같은 방송을 다시 올렸을 가능성을 배제할 수 없다. 실제 촬영 날짜나 날짜를 넘긴 동일인 연결은 입증하지 않는다. 예상 인물은 데이터셋 ID를 기준으로 하며 별도의 실명 확인 결과가 아니다.

```bash
$PY tools/collect_face_validation.py
$PY tools/verify_face_generalization.py
$PY tools/plot_face_validation.py
$PY tools/audit_face_validation.py
```

수집, 고정 기준과 결과는 `evidence/person-libraries/expanded-face-collection.json`, `expanded-face-protocol.json`, `expanded-face-validation.json`에 저장했다. 결과 일관성과 등록 성공 여부를 분리한 계산은 `expanded-face-audit.json`, 그래프는 `expanded-face-results.png`다. 원본 영상, 등록 사진, 프레임별 판정과 출처 검토 이미지는 Git에서 제외한 `evidence/private/face-validation`에 보관한다. 판정 기록 1,296건의 중복, 원본 ID 분리, 이전 3개 ID 제외, 고정 기준 및 소스와 그림의 해시는 감사 도구로 확인했다.

## 얼굴 후보 비교 개선과 별도 인물 평가

앞 절의 18개 인물 ID를 개선용 자료로 전환했다. 기존 3개 ID와 개선용 18개 ID를 제외하고 새로운 24개 ID를 최종 평가용으로 고정했다. 12개는 등록 대상이고 12개는 미등록 대상이다. 등록은 첫 원본 영상의 첫, 중간, 마지막 3장으로 시도한다. 비교는 인물마다 다른 원본 ID 두 개씩이다. 총 60개 영상 중 비교 영상 48개에서 12프레임씩, 576개 원본 프레임을 선택했다. 두 방식에는 같은 등록 사진과 비교 프레임을 제공했다.

등록 정책은 20픽셀보다 작은 배경 얼굴을 제외한다. 여러 얼굴 중 주 얼굴의 면적이 다음 얼굴의 4배 이상이면 주 얼굴을 선택하고, 비슷한 크기의 얼굴이 여럿이면 보류한다. 참조 이미지 항목을 아래처럼 쓰면 정규화한 대상 영역 안의 얼굴 하나를 지정할 수 있다. 기존 문자열 경로도 지원한다.

```json
{"image":"group.jpg","target":[0.1,0.1,0.5,0.9]}
```

기존 Buffalo L 가중치를 유지하고 정렬한 112픽셀 얼굴과 좌우 반전 얼굴의 특징을 합해 정규화한다. [InsightFace 공식 검증 코드](https://github.com/deepinsight/insightface/blob/master/recognition/arcface_torch/eval/verification.py)도 원본과 반전 특징을 합해 정규화하는 방식을 제공한다. 별도 학습이나 새 인식 서버는 사용하지 않는다.

판정 기준은 개선용 18명 자료에서 선택했다. 잘못된 연결이 없는 범위에서 올바른 연결 수를 높이되, 단일 프로필 대조에서 다른 인물의 최고 점수보다 최소 0.05 높은 유사도 여유를 요구했다. 선택된 값은 유사도 0.29, 1, 2위 프로필 간 차이 0.10과 반전 특징 결합이다. 이 유사도는 확률이 아니다. 최종 24명 자료의 점수는 선택에 사용하지 않았다. 특징은 고정된 사전 학습 모델로 추출해 보관하고 같은 특징에서 이전 방식과 새 방식을 비교한다.

개선용 자료에서는 이전 78/288인 27.1%를 재현했고, 새 설정은 277/288인 96.2%였다. 최종 성능은 다음의 별도 24명 결과로 구분한다.

| 별도 인물 평가 조건 | 이전 올바른 후보 | 개선 후 올바른 후보 | 개선 후 보류 | 개선 후 오연결 |
| --- | ---: | ---: | ---: | ---: |
| 원본 | 104/288, 36.1% | 272/288, 94.4% | 16 | 0 |
| 저조도 변형 | 105/288, 36.5% | 269/288, 93.4% | 19 | 0 |
| 저해상도 변형 | 102/288, 35.4% | 267/288, 92.7% | 21 | 0 |

미등록 12명의 프레임은 조건마다 288개다. 전체 12개 프로필을 등록한 기본 평가에서는 세 조건 모두 잘못된 후보가 0개였다. 모든 비교 조건에서 주 얼굴을 검출했다. 새 등록 대상은 두 방식 모두 12명이 등록됐으며 등록 선택만 고친 대조군은 이전 방식과 결과가 같았다. 따라서 새 자료의 차이를 등록 인물을 더 추가해서 얻은 결과로 설명하지 않는다.

프로필이 적을 때도 확인했다. 새 12개 프로필에서 1개, 2개, 3개, 6개를 고르는 모든 조합을 검사했다. 반복 집계를 제거하면 같은 원본 1프레임이 세 조건에서 잘못된 후보에 연결된 사례가 남았다. 원본 단일 프로필 대조에서는 다른 사람 대조 6,624건 중 1건이다. 많은 조합의 반복을 서로 독립적인 사람 수로 세지 않는다. 오류가 남으므로 운영자 확인을 유지하며 이 조합 결과를 보고 기준을 다시 바꾸지 않았다.

기본 설정은 `YOLOv5/face_policy.json`의 candidate-2다. 설정에 기록한 모델 해시와 실제 인식 모델이 같은지 확인한다. 실행 세션에는 정책 버전과 특징 방식도 기록한다. `--face-legacy`는 이전 등록과 특징 및 판정 방식을 재현한다. 과거 모델 비교와 오바마 시험 도구는 이 옵션을 명시해 이전 기준을 유지한다.

```bash
$PY tools/collect_face_holdout.py
$PY tools/calibrate_face_policy.py
$PY tools/evaluate_face_improvement.py
$PY tools/audit_face_policy_galleries.py
$PY tools/plot_face_improvement.py
$PY tools/verify_person_history.py
$PY tools/verify_face_policy_checks.py
```

WSL Edge 단위 검사 30개가 통과했다. 새 기본 설정으로 실제 보행자 71프레임과 얼굴 영상 7프레임을 처리하고 Django에 이력 사진 37장과 통과 사건 6건을 저장했다. 얼굴 영상의 후보는 이전 5건에서 7건으로 늘었다. 재전송, 기록 및 근거 조회, 사진 인증과 필수 Post API 7개 필드도 확인했다. 원본 baseline/detect.py의 해시는 유지했다. Windows Android API35 기기 검사 2개도 통과했고 새 기록의 네이티브 앱과 실제 WebView 화면 5장을 캡처했다.

선택 기록은 `face-policy-calibration.json`, 별도 인물 결과는 `face-improvement-evaluation.json`, 적은 프로필 검사는 `face-policy-gallery-audit.json`, 최종 점검은 `face-improvement-checks.json`이다. 모두 `evidence/person-libraries`에 있으며 비교 그림은 `face-improvement-results.png`다. 개별 얼굴 특징과 영상은 Git에서 제외한 `evidence/private/face-improvement`에 보관한다.

이 결과는 데이터셋 ID와 근거리 얼굴 영상의 후보 연결률이다. 같은 영상의 프레임과 인위적 변형은 서로 독립적이지 않다. 원본 영상 ID가 달라도 같은 촬영의 재업로드 가능성은 남으며 실제 촬영 날짜와 날짜를 넘긴 방문 이력을 입증한 결과로 쓰지 않는다. PythonAnywhere 배포와 실제 LLM 인증 상태도 이 Edge 개선 검증과 구분한다.
