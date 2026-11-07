# 프로젝트에 재사용할 기존 구현 조사

조사일은 2026년 11월 8일이다. 제작자의 공식 저장소와 문서, Hugging Face 모델 카드, PyPI 배포 메타데이터를 확인했다. 20개 Python 패키지의 현재 배포 버전과 의존성은 `evidence/reuse-research/package-metadata.json`에 기록했다. 이번 조사에서 패키지를 설치하거나 운영 서버를 변경하지 않았다. 아래 우선순위는 프로젝트 조건에 따른 판단이며, 우리 영상에서 측정한 성능 순위가 아니다.

## 적용 조건

기본 평가 흐름은 YOLOv5 Edge에서 검출한 사진을 Django에 전송하고 Android와 모바일 웹에서 확인하는 것이다. 이 흐름과 PythonAnywhere 서버를 유지한다. 추가 기능 후보는 사람의 이동과 등장 이력을 기록하는 기능, 기록을 근거로 질문에 답하는 기능이다. 라이브러리 수를 추가 기능 수로 세지 않는다.

모델은 공개 사전 학습 가중치를 사용한다. 사용자가 학습, 강화학습, 수동 설치를 할 것을 전제로 하지 않는다. 영상 추론과 모델 비교의 실행 위치는 WSL Edge다. 서버는 저장과 조회, 인증, 화면 및 질의 처리를 맡는 구성이 적합하다. [무료 PythonAnywhere 안내](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/)에는 512MiB 저장 공간과 웹 워커 1개가 명시되어 있으며, [외부 접속은 허용 목록](https://www.pythonanywhere.com/whitelist/)을 따른다. 콘솔의 CPU 사용량과 웹 앱의 제한을 같은 것으로 취급하지 않는다.

## 얼굴과 동일인 비교

| 기존 구현 | 제공하는 기능 | 프로젝트에서의 판단 |
| --- | --- | --- |
| [InsightFace FaceAnalysis](https://github.com/deepinsight/insightface/tree/master/python-package) | 얼굴 검출, 정렬, 사전 학습 특징 추출. ONNX Runtime CPU 지원 | YOLOv5 흐름에 얼굴 비교 기능을 붙이는 우선 비교 후보 |
| [InsightFace PersonAnalysis](https://github.com/deepinsight/insightface/blob/master/python-package/docs/person_analysis.md) | 등록 사진과 얼굴 및 전신 비교, 조건부 전신 참조 추가. CPU용 Cheetah S 제공 | 기능상 매우 가깝다. 자체 사람 검출기를 포함하므로 YOLOv5 유지와 연동 방식을 확인한 뒤 구조 채택 여부를 결정 |
| [DeepFace](https://github.com/serengil/deepface) | 얼굴 검증, 등록 집합 검색, 여러 사전 학습 모델의 공통 API | 모델을 같은 입력으로 비교하는 우선 후보. 현재 0.0.104는 ONNX Runtime이 기본이며 TensorFlow는 선택 의존성 |
| [OpenCV YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)와 [SFace](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) | 얼굴 검출, 5개 기준점 정렬, 특징 추출과 비교 | 현재 OpenCV를 활용할 수 있는 CPU 비교 기준. OpenCV 4.10에서는 4.x용 YuNet 모델을 선택해야 함 |
| [InspireFace](https://github.com/HyperInspire/InspireFace) | 얼굴 검출, 추적, 특징 비교와 FeatureHub, Python 및 Android SDK | 얼굴 중심 통합 SDK의 예비 후보. 학업용 모델 조건과 실제 사용 API를 확인해 비교 |
| [AdaFace와 CVLFace](https://github.com/mk-minchul/AdaFace) | 낮은 화질에 대응하는 얼굴 모델과 사전 학습 가중치 | 저화질 오답이 주된 문제로 확인되면 비교할 후보. 전처리와 참조 저장까지 완성된 서비스는 아님 |
| [CAFace](https://github.com/mk-minchul/caface) | 여러 프레임의 얼굴 특징을 합치는 학습 완료 모델과 영상 데모 | 단일 프레임보다 영상의 여러 얼굴을 활용하는 후보. 가중치 링크의 실제 접근, 백본 및 구형 환경 호환성을 먼저 확인해야 함 |
| [facenet-pytorch](https://github.com/timesler/facenet-pytorch) | MTCNN과 사전 학습 InceptionResnetV1 | 예비 기준 모델. 배포본 2.6.0은 torch 2.2 이상 2.3 미만을 요구하므로 현재 torch 2.6과 충돌 |
| [face_recognition](https://github.com/ageitgey/face_recognition) | dlib 기반 얼굴 인코딩과 비교 API | 간단한 기준 모델 후보. dlib 빌드와 다양한 얼굴 조건의 성능을 고려하면 우선순위는 낮음 |
| [Torchreid와 OSNet](https://github.com/KaiyangZhou/deep-person-reid) | 전신 재식별 모델과 가중치 | 전신 비교 대조군. 앞선 의상 변화 사진 실험에서 사용한 OSNet 모델은 자동 연결 기준에 미달했으며 얼굴 모델 평가와 구분 |
| [FastReID](https://github.com/JDAI-CV/fast-reid) | 전신 재식별 모델 모음과 추론 및 내보내기 도구 | 다른 사전 학습 전신 모델 비교용. 영구 인물 ID와 방문 DB를 제공하는 제품은 아님 |
| [CAL / Simple-CCReID](https://github.com/guxinqian/Simple-CCReID) | 의상 변화 재식별 연구 구현 | 문제 설정은 가깝지만 공식 README에서 바로 쓸 학습 완료 가중치를 확인하지 못했다. 직접 학습이 필요한 경로는 현재 작업 계획에서 제외 |

InsightFace의 Python 배포본은 2.1이다. PersonAnalysis의 참조는 객체 메모리에 보관되며, 공식 문서도 DB, 연속 추적, 익명 인물의 자동 생성, 과거 사건 관리가 SDK의 범위 밖이라고 설명한다. 등록 사진을 특징으로 바꾸는 일과 모델 파라미터 학습은 다르다. 프로젝트에서 필요한 DB와 사건 규칙은 별도로 연결해야 한다.

InsightFace 코드의 MIT 조건과 제공 모델의 비상업 연구용 조건은 구분한다. OpenCV Zoo의 해당 YuNet 디렉터리는 MIT, SFace 디렉터리는 Apache 2.0을 명시한다. 모델을 채택할 때는 실제 가중치의 조건과 출처를 함께 고정한다.

## 추적, 통과 집계와 검증

| 기존 구현 | 제공하는 기능 | 프로젝트에서의 판단 |
| --- | --- | --- |
| [Norfair](https://github.com/tryolabs/norfair) | 검출기와 독립적인 다중 객체 추적 | 현재 NumPy 1.26 환경에 맞는 추적 기준 후보. YOLOv5 상자를 전달하는 연결 코드가 필요 |
| [BoxMOT](https://github.com/mikel-brostrom/boxmot) | BoT-SORT, ByteTrack, OC-SORT 계열 등의 공통 추적 API와 외형 인코더 | 가림과 교차 비교에 적합한 후보. Python API로 기존 YOLOv5 검출을 입력할 수 있으나 최신 26.0.0은 NumPy 2.2 이상이 필요 |
| [Roboflow Trackers](https://github.com/roboflow/trackers) | SORT, ByteTrack, OC-SORT와 평가 도구 | 공통 입력으로 여러 추적기를 비교하기 좋은 후보. 배포본 2.7.0은 NumPy 2 이상이 필요 |
| [Supervision](https://github.com/roboflow/supervision) | 검출 결과 자료형, 선 및 영역 집계, 표시와 영상 처리 | 기존 도구를 활용해 통과 집계와 표시를 구성하는 우선 후보. 인물 신원 판별 모델을 대신하지 않음 |
| [deep-sort-realtime](https://github.com/levan92/deep_sort_realtime) | 검출 상자와 선택적 외형 특징을 받아 추적 | 현재 환경에서 비교할 예비 후보. 내부 기본 외형 모델만으로 날짜가 다른 동일인 연결을 보장하지 않음 |
| [ByteTrack 원본](https://github.com/FoundationVision/ByteTrack) | 공개 추적 알고리즘과 평가 코드 | 원형 참고와 대조군. 논문 저장소의 전체 YOLOX 설치 과정을 우리 서버의 필수 의존성으로 채택하지 않음 |
| [TrackEval](https://github.com/JonathonLuiten/TrackEval) | HOTA, IDF1 등 표준 추적 지표 | 추적 점수 계산을 재사용할 우선 검증 도구. Python 3.12의 최신 패키지는 NumPy 2.3.2 이상을 요구해 실행 환경을 분리해야 함 |
| [motmetrics](https://github.com/cheind/py-motmetrics) | MOT 오류와 식별 지표 계산 | 추적 검증의 예비 도구. HOTA를 포함한 비교에는 TrackEval을 우선 검토 |

추적기가 돌려주는 번호는 연속 영상의 궤적 번호다. 서비스의 인물 프로필과 같은 번호라고 가정하지 않는다. 통과 사건을 생성할 기준선, 가림 뒤 복귀, 중복 전송과 촬영 중단 처리 규칙은 서비스에서 정의하고 시험한다.

## 특징 검색, 기록 검색과 질의

| 기존 구현 | 제공하는 기능 | 프로젝트에서의 판단 |
| --- | --- | --- |
| [OpenCLIP](https://github.com/mlfoundations/open_clip) | 이미지와 문장을 비교하는 사전 학습 모델 | 옷 색이나 가방 같은 보이는 특징으로 후보를 찾는 선택 사항. 동일인 확정에는 사용하지 않음 |
| [SigLIP 2](https://huggingface.co/google/siglip2-base-patch16-224) | 이미지와 문장 검색, 추가 학습 없는 후보 문구 분류 | 외형 특징 검색의 비교 후보. Edge에서 대표 장면을 처리하는 용도이며 CPU 속도와 한국어 질의는 별도 실측 필요 |
| [Django ORM](https://docs.djangoproject.com/en/6.1/topics/db/aggregation/)과 SQLite | 날짜 필터, 횟수 집계, 기록 및 근거 사진 조회 | 현재 서비스에서 재사용할 기록 검색의 우선 구성 |
| [LangChain](https://docs.langchain.com/oss/python/langchain/structured-output) | 구조화된 질문 조건, 도구 호출과 근거 기반 응답 연결 | 날짜와 대상 조건을 검증해 ORM 조회와 연결하는 후보. LLM과 API 인증을 제공해주는 패키지는 아님 |
| [LlamaIndex](https://developers.llamaindex.ai/python/framework/understanding/rag/) | 검색과 답변 연결, 구조화 자료를 포함한 질의 구성 | LangChain의 대안. 둘을 동시에 넣기보다 한쪽의 필요한 모듈을 선택 |
| [SentenceTransformers](https://github.com/huggingface/sentence-transformers)와 [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | 한국어를 포함한 텍스트 임베딩 | 자유 문장 검색을 추가할 때의 후보. PythonAnywhere에 모델 전체를 탑재하는 구성을 우선하지 않음 |
| [BGE-M3](https://huggingface.co/BAAI/bge-m3) | 다국어 및 복합 텍스트 검색 | 더 큰 검색 모델의 예비 후보. 현재 규모와 무료 서버 조건에서는 우선순위가 낮음 |
| [FAISS](https://github.com/facebookresearch/faiss) | 특징 벡터 유사 검색 | 인물 참조가 많아질 때 Edge의 검색 후보. 날짜와 통과 횟수의 원장 DB로 사용하지 않음 |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | SQLite 내부 벡터 검색 확장 | 별도 DB 서비스를 줄일 수 있지만 PythonAnywhere의 확장 로드 지원을 확인하기 전까지 채택 보류 |
| [Qdrant Client Local Mode](https://github.com/qdrant/qdrant-client) | 별도 서버 없이 메모리 또는 파일에 벡터 저장과 검색 | 독립 시험용 후보. 운영 서버의 저장 공간과 동시 접근 검증이 필요 |
| [Chroma](https://github.com/chroma-core/chroma) | 임베딩 저장과 메타정보 필터 검색 | 로컬 시험 후보. 기본 모델 자동 다운로드와 의존성을 포함한 서버 적합성 확인 전에는 필수 구성으로 넣지 않음 |

강의 자료 49쪽은 RAG에 벡터 임베딩이 필수라고 하지 않는다. LangChain 공식 검색 문서도 기존 SQL DB에서 조회한 내용을 LLM 문맥에 넣는 구성을 설명한다. 따라서 날짜와 횟수는 ORM에서 계산하고, 조회 결과와 사진 기록 번호를 근거로 응답을 생성하는 구성이 프로젝트에 맞는다. 문장 생성까지 실제 모델을 호출해야 RAG의 생성 단계를 검증했다고 기록한다. 조회만 한 결과를 RAG 완료로 표시하지 않는다.

LLM 모델 제공자와 인증은 이번 조사에서 결정하거나 설정하지 않았다. 선택한 제공자의 API가 PythonAnywhere에서 실제 접속 가능한지, 인증과 비용 조건이 맞는지 확인해야 한다. 임의 SQL을 LLM이 직접 실행하는 구성을 기본안으로 삼지 않는다.

## 완성형 제품도 확인한 결과

| 기존 제품 | 가까운 기능 | 현재 프로젝트에 대한 판단 |
| --- | --- | --- |
| [Frigate](https://docs.frigate.video/configuration/face_recognition/) | 객체 기록, 얼굴 참조, 여러 프레임의 얼굴 결과 취합, 검색 화면 | 사용자 흐름 참고에 적합하다. Docker 기반 전체 제품으로 기본 Django 서버를 교체하는 경로는 평가 조건과 배포 조건에 맞지 않아 제외 |
| [CompreFace](https://github.com/exadel-inc/CompreFace) | 얼굴 등록과 검증, 검색 REST API | 완성도가 높지만 Docker Compose 서비스가 필요하다. 별도 인프라를 추가하는 구조는 현재 계획에 포함하지 않음 |
| [InsightFace Server](https://github.com/deepinsight/insightface/tree/master/server) | 얼굴 Collection과 Person 저장, 검색 API와 Web UI | 기능 참고 후보. Linux Docker 서비스 전체를 현재 Django 대신 배포하는 경로는 제외 |
| [Ollama](https://github.com/ollama/ollama) | 학습 완료 LLM의 로컬 추론과 API | 강의에도 등장하지만 모델 크기와 실행 프로세스, Edge와 클라우드 사이 요청 전달을 해결해야 한다. 무료 PythonAnywhere 안에서 직접 실행하는 구성을 채택하지 않음 |

## 다음 비교 시험의 우선순위

첫 얼굴 비교군은 InsightFace FaceAnalysis, DeepFace, OpenCV SFace다. PersonAnalysis는 얼굴과 전신을 결합한 기존 SDK의 비교군으로 검토하되 자체 검출 결과와 YOLOv5 결과를 어떻게 연동할지 확인한다. 이 네 후보 모두 공개 사전 학습 모델을 사용하는 경로를 전제로 한다.

추적은 현재 환경에 맞는 Norfair를 기준으로 놓고 BoxMOT 또는 Roboflow Trackers를 분리된 시험 환경에서 비교한다. 통과 표시와 집계는 Supervision을 활용하는 것이 우선이다. CAFace는 여러 프레임의 얼굴 정보가 필요한지 확인한 뒤 모델 접근과 호환성 검증을 통과하면 비교군에 추가한다.

모델과 추적 알고리즘은 재사용하고, 프로젝트 코드는 평가용 API 연결, 인증, 사건 중복 방지, 프로필과 관측 기록의 관계, 모호한 연결의 확인과 수정, Android 및 모바일 웹 화면을 담당한다. 실제 후보 채택은 같은 자료에서 정답과 오답, 미등록 인물 오연결, 보류 비율, CPU 처리 속도와 메모리를 측정한 뒤 결정한다.
