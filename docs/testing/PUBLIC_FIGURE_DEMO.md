# 트럼프와 오바마 시연 자료

현재 운영 원본 수와 관측 사진 수는 [원본 자료 확장 기록](PUBLIC_FIGURE_EXPANSION.md)에 정리했다. 아래는 최초 등록과 네 비교 구간의 검증 기록이다.

2026년 11월 9일 두 사람의 등록 사진과 실제 모델에서 검출한 관측 사진을 PythonAnywhere에 추가했다. 도널드 트럼프는 원본 영상 2개와 관측 사진 12장, 버락 오바마는 원본 영상 2개와 관측 사진 11장이 있다. 각 프로필의 발견 이력, 등록 얼굴과 관측 얼굴 비교, 인물 조건을 적용한 기록 질문을 운영 API와 브라우저에서 확인했다. 모든 새 추적은 운영자가 검토할 얼굴 후보 상태다.

## 원본과 구간

| 인물 | 원본 | 분석한 구간 | 분석 프레임 | 몸 추적과 연결된 해당 인물 후보 |
| --- | --- | --- | ---: | ---: |
| 도널드 트럼프 | [DVIDS 506134, Salute to Armed Services Ball](https://www.dvidshub.net/video/506134/president-trump-talks-troops-afghanistan-sas-ball) | 8초부터 17초 | 90 | 70 |
| 도널드 트럼프 | [DVIDS 512302, Langley Air Force Base](https://www.dvidshub.net/video/512302/president-trump-arriving-langley-air-force-base) | 228초부터 240초 | 60 | 26 |
| 버락 오바마 | [HDTF 커뮤니티 미러](https://huggingface.co/datasets/saeed-5959/hdtf), BarackObama_044.mp4 | 0초부터 9초 | 37 | 35 |
| 버락 오바마 | [DVIDS 358042, 공개 메시지](https://www.dvidshub.net/video/358042/president-obama-remarks-ebola-outbreak) | 10초부터 22초 | 120 | 118 |

검증 범위는 선택한 네 구간의 실제 얼굴 후보 검출과 저장 및 조회 연동이다. 307프레임에는 연속된 사진이 포함된다. 후보 검출 건수도 같은 얼굴의 반복 검출을 포함한다. 연설 및 이동 영상의 다른 인물은 개별 얼굴 검출과 비교 결과에 따라 처리한다. 이 네 구간에서 다른 등록 프로필로 연결된 후보는 0건이다. 시연용 사진은 중복 장면을 줄여 23장으로 골랐다.

트럼프 등록 사진은 DVIDS 506134의 1초, 3초, 5초에서 골랐고 비교 구간과 프레임을 분리했다. 오바마는 기존에 검증한 BarackObama_001.mp4의 0, 124, 247번 프레임을 등록했다. HDTF의 001과 044는 같은 원본 촬영에서 나뉜 구간일 수 있다. 별도 원본인 DVIDS 358042를 함께 사용했다. 등록 집합에는 기존 인물 A, B, C를 유지해 5개 프로필이 경쟁하도록 했다. 공군기지 원본은 여러 인물이 등장하므로 8초 간격의 얼굴 후보 탐색으로 실제 이동 구간을 찾았다.

## 실행과 보존

수집, OpenCV 전체 디코딩, SHA256 대조, YOLOv5와 Buffalo L 추론, 패킷 직렬화 검사는 WSL Ubuntu 프로젝트 가상환경에서 실행했다. 고정된 candidate-2 판정 기준과 사전 학습 모델을 사용했다. 관측 이미지는 원본 구간의 픽셀을 JPEG로 저장했다. 화면의 영상 초는 잘라낸 비교 영상의 재생 위치다. 원본 구간 시작 위치는 위 표와 추론 JSON에 남겼다. 정확한 원본 촬영 시각은 미상으로 유지하고 실제 처리 시각을 분석일로 저장했다.

`tools/collect_figure_dvids.py`로 정부 공개 원본 3개를 수집한다. DVIDS 페이지의 공개 재생 파일과 Public Domain 표기를 확인했고 출처 HTML과 이용조건 링크를 원본 옆에 보관한다. HDTF 원제작자는 [MRzzm/HDTF](https://github.com/MRzzm/HDTF)이며 커뮤니티 미러와 구분한다. 원본 영상, 등록 이미지와 관측 사진은 Git에서 제외된 비공개 디렉터리에 둔다. 얼굴 특징은 로컬 모델 비교에 사용한다.

`tools/prepare_public_figure_demo.py`는 등록 집합과 네 비교 구간을 준비하고 실제 추론을 확인한다. `tools/populate_public_figure_demo.py`는 직렬화 검증 후 운영자 API로 전송하며 재실행 시 같은 사진의 중복 생성을 막는다. 등록 사진과 관측 이미지는 운영자 인증으로 보호된다. 기존 공개 게시글이 동일한지도 확인했다. 운영 서버의 모델, DB 스키마와 소스 파일 변경 없이 기존 API를 사용했다.

수집 기록은 `evidence/history/public-figure-dvids-collection.json`, 추론 기록은 `public-figure-inference.json`, 운영 저장과 질문 조회 결과는 `public-figure-cloud.json`에 있다. 로컬 작업 디렉터리는 `evidence/private/public-figure-demo`이며 재사용할 5프로필 등록 집합은 그 안의 `references.json`이다.
