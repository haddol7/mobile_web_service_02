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

큰 모델은 다음 명령으로 미리 준비할 수 있다. 실행 코드에서도 자동 다운로드를 지원한다.

```bash
$PY tools/prepare_person_models.py --model buffalo_l
```

참조 이미지 경로는 JSON 파일의 위치를 기준으로 읽는다. 프로필에는 유효한 얼굴 사진이 하나 이상 필요하다. 얼굴이 없거나 여러 개인 사진은 거부 사유를 기록하고 유효한 사진을 등록한다. 아래 ID는 지정한 서비스 식별자다.

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

현재 적용 위치는 WSL Edge다. 영구 인물 및 방문 이력 DB, Android 이력 화면과 RAG는 별도 구현 범위다. PythonAnywhere와 실물 웹캠 검증 상태는 기존 요구사항 기록을 따른다.
