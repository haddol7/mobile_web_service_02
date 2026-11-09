# 공개 인물 원본 자료 확장

트럼프는 서로 다른 원본 10개와 관측 사진 56장, 오바마는 원본 10개와 관측 사진 57장을 운영 서버에서 조회할 수 있다. 기존 원본 2개씩에 새로운 촬영 원본 8개씩을 추가했다. 신규 원본은 총 16개, 3,191,115,358바이트로 약 3.19GB다. 각 인물의 추가 원본 8개는 촬영 날짜가 서로 다르다.

공식 공개 영상 전체를 내려받고 파일 크기, SHA256, 중복 바이트와 전체 프레임 디코딩을 확인했다. 날짜와 행사, 원본 파일을 대조했다. 원본은 Windows 작업 폴더의 비공개 자료 디렉터리에 보관한다. PythonAnywhere에는 실제 분석 사진 90장을 추가했다. 공개 게시글과 기존 등록 사진은 보존했다.

## 원본별 검증

| 인물 | 원본 표기 촬영일 | 원본 출처 | 전체 길이 | 실제 분석 프레임 | 추가 사진 |
| --- | --- | --- | ---: | ---: | ---: |
| 오바마 | 2013-04-18 | [DVIDS 287224](https://www.dvidshub.net/video/287224/president-obama-visits-boston) | 10.9분 | 20 | 5 |
| 오바마 | 2014-03-26 | [DVIDS 324601](https://www.dvidshub.net/video/324601/president-obama-palais-des-beaux-arts) | 42.5분 | 20 | 6 |
| 오바마 | 2014-09-05 | [DVIDS 359270](https://www.dvidshub.net/video/359270/president-obama-press-conference-nato-wales-summit) | 26.0분 | 20 | 5 |
| 오바마 | 2014-09-26 | [DVIDS 362956](https://www.dvidshub.net/video/362956/president-obama-global-health-security-agenda-summit) | 10.2분 | 20 | 6 |
| 오바마 | 2015-02-19 | [DVIDS 391729](https://www.dvidshub.net/video/391729/president-obama-remarks-white-house-summit-countering-violent-extremism-arabic-audio) | 21.4분 | 20 | 6 |
| 오바마 | 2015-07-06 | [DVIDS 413783](https://www.dvidshub.net/video/413783/president-barack-obamas-statement-press) | 19.5분 | 20 | 6 |
| 오바마 | 2016-04-01 | [DVIDS 456872](https://www.dvidshub.net/video/456872/president-obama-remarks-nuclear-security-summit) | 10.3분 | 20 | 6 |
| 오바마 | 2016-11-14 | [DVIDS 493194](https://www.dvidshub.net/video/493194/arabic-president-obama-addresses-us-commitment-nato-white-house) | 0.8분 | 20 | 6 |
| 트럼프 | 2017-02-01 | [DVIDS 508029](https://www.dvidshub.net/video/508029/swearing-secretary-state-rex-tillerson) | 8.3분 | 20 | 5 |
| 트럼프 | 2017-05-22 | [DVIDS 526302](https://www.dvidshub.net/video/526302/president-trump-delivers-remarks-with-israeli-prime-minister-netanyahu) | 11.8분 | 20 | 6 |
| 트럼프 | 2017-11-07 | [DVIDS 563342](https://www.dvidshub.net/video/563342/president-trump-japan-departure-broll-highlights) | 5.6분 | 20 | 5 |
| 트럼프 | 2018-09-21 | [DVIDS 628029](https://www.dvidshub.net/video/628029/president-trump-remarks-and-signing-ceremony) | 20.3분 | 20 | 5 |
| 트럼프 | 2018-10-11 | [DVIDS 632165](https://www.dvidshub.net/video/632165/president-trump-delivers-remarks-interagency-task-force-monitor-and-combat-trafficking-persons-annual-meeting) | 9.9분 | 20 | 6 |
| 트럼프 | 2020-01-08 | [DVIDS 733563](https://www.dvidshub.net/video/733563/president-trump-remarks-media) | 9.7분 | 20 | 5 |
| 트럼프 | 2020-03-11 | [DVIDS 742724](https://www.dvidshub.net/video/742724/president-trump-will-address-nation) | 9.5분 | 20 | 6 |
| 트럼프 | 2020-07-10 | [DVIDS 759368](https://www.dvidshub.net/video/759368/president-trump-receives-briefing-southcom-enhanced-counternarcotics-operations) | 33.5분 | 20 | 6 |

실제 모델 분석은 선정한 구간의 총 320프레임이다. 얼굴 후보 탐색으로 비교 구간을 정하고 기존 YOLOv5, Norfair와 Buffalo L로 얼굴이 사람 추적 번호에 연결되는지 확인했다. 등록 집합은 기존 인물 A, B, C와 트럼프, 오바마의 5프로필이며 candidate-2 기준을 사용했다. 연결된 후보가 있고 다른 프로필 후보와 섞이지 않은 사진을 골라 운영 이력에 저장했다. 이 자료는 시연 장면을 선정한 결과로, 프레임의 무작위 표본 정확도와 구분한다. 각 인물의 원본 수는 프레임 수나 방문 횟수와 구분한다.

날짜별 목록은 실제 분석일 기준이다. 원본 표기 촬영일은 장면 제목과 수집 기록에 보관하고 정확한 원본 촬영 시각은 미상으로 유지한다. 화면의 영상 초는 선정한 비교 영상의 재생 위치이며 원본 시작 위치는 추론 기록에 있다. 새 기록은 운영자가 얼굴 비교 화면에서 확인할 후보 상태다.

## 운영 검증

패킷 직렬화 검사 후 운영자 API로 저장했다. 원본 수와 인물별 이력을 확인하고, 각 인물의 기록 질문에서 10개 원본의 근거가 고르게 조회되는지 확인했다. 같은 패킷 재전송에서는 새 사진이 생기지 않았다. 새 관측 이미지의 무인증 접근은 거부됐다. 기존 공개 게시글은 동일했다.

수집과 모델 실행은 WSL Ubuntu 가상환경, 저장 및 조회 검사는 실제 PythonAnywhere에서 수행했다. 기존 서버와 Android API를 사용해 자료를 추가했다. 원본 파일, 장면 이미지와 등록 사진은 Git에서 제외한다. 수집한 DVIDS 페이지의 Public Domain 표기와 [이용조건](https://www.dvidshub.net/about/copyright)을 확인하고 출처 HTML을 원본과 함께 보관한다.

```bash
python tools/collect_expanded_figure_sources.py
python tools/prepare_expanded_figures.py scan
python tools/prepare_expanded_figures.py infer
python tools/populate_expanded_figures.py
python tools/document_figure_expansion.py
```

수집 증빙은 `evidence/history/public-figure-expanded-collection.json`, 실제 추론은 `public-figure-expanded-inference.json`, 운영 검증은 `public-figure-expanded-cloud.json`이다. 검토용 실제 원본 화면은 `evidence/private/public-figure-expanded/source-review.jpg`에 있다. 최초 등록과 네 구간의 검증은 [최초 시연 자료](PUBLIC_FIGURE_DEMO.md)에 보관한다.
