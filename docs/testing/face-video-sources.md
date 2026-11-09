# 동일인 영상 시험 자료 조사

2026년 11월 8일 Hugging Face 공개 API와 HDTF 제작자의 GitHub를 확인했다. 계정 로그인이나 신청서 제출 없이 샘플 영상 8개를 내려받았다. WSL Ubuntu의 프로젝트 가상환경에서 OpenCV로 총 1,235프레임을 끝까지 디코딩했고, 8개 영상의 첫 프레임도 직접 검토했다. 아래는 자료 확보 기록이다. 이후 실제 비교 결과는 [라이브러리 적용 기록](person-libraries.md)의 얼굴 모델 비교 및 오바마 클립 시험에 정리했다.

## 우선 사용할 후보

| 자료 | 실제 확인한 내용 | 활용 범위 |
| --- | --- | --- |
| [mortal9826/VoxCeleb2-test-data](https://huggingface.co/datasets/mortal9826/VoxCeleb2-test-data) | MP4 ZIP 안에 영상 36,237개와 인물 ID 118개가 있다. 인물 3명에 대해 서로 다른 원본 영상 ID 두 개씩, 총 6개 샘플을 받았다. | 서로 다른 원본 영상의 얼굴 비교를 시작할 후보 |
| [saeed-5959/hdtf](https://huggingface.co/datasets/saeed-5959/hdtf) | `BarackObama_001.mp4`부터 `BarackObama_044.mp4`까지 44개 파일을 목록에서 확인했고, 첫 파일과 마지막 파일을 받았다. 두 샘플은 각각 512x512, 248프레임, 9.92초다. | 첫 클립 3장 등록과 마지막 클립 248프레임 전체의 실제 동일인 후보 비교에 사용 |
| [MRzzm/HDTF](https://github.com/MRzzm/HDTF) | 제작자가 원본 YouTube URL과 구간, 얼굴 영역 및 처리 방법을 제공한다. README에는 CC BY 4.0을 명시한다. | 미러 파일의 원래 출처와 처리 방식 대조 |

VoxCeleb2 샘플은 크기가 약 8.9GB인 ZIP 전체 대신 필요한 파일 구간만 읽었다. ZIP에서 전송받은 바이트는 5,508,471바이트이고, 선택한 6개 파일의 CRC 검사를 통과했다. 각 파일의 SHA256, 고정 저장소 리비전, 원본 영상 ID와 디코딩 결과를 로컬 검증 기록에 남겼다.

두 Hugging Face 저장소는 커뮤니티 미러다. 원제작자의 공식 배포본과 구분해 출처를 기록한다. 이번 조사에서는 신청을 요구하는 저장소에 접근하거나 신청서를 제출하지 않았다.

## 시험 자료를 나눌 때 주의할 점

HDTF의 [공식 WDA 원본 목록](https://github.com/MRzzm/HDTF/blob/main/HDTF_dataset/WDA_video_url.txt)에서 BarackObama 항목은 원본 URL 하나다. 확보한 두 클립도 같은 의상과 배경을 보인다. 따라서 44개 파일을 서로 다른 촬영 44건으로 세거나, 이들만 나눠 서로 다른 촬영의 동일인 판별 성능을 주장하지 않는다.

VoxCeleb2는 인물 ID와 원본 영상 ID가 폴더에 남아 있다. 등록용과 비교용을 원본 영상 ID 단위로 분리할 수 있다. 같은 원본의 재업로드나 겹치는 장면이 있는지도 본 시험 구성 전에 확인한다. 실제 촬영 날짜와 실제 방문 횟수는 이 자료의 검증 범위에 포함하지 않는다.

인물 3명의 샘플은 입력 확인용 소규모 자료다. 정확도를 측정할 때는 인물 수와 촬영 조건을 늘리고, 등록되지 않은 인물도 포함한다. 원본 영상 분리와 평가 집합을 고정한 뒤 모델 비교를 실행한다.

## 그 밖의 검색 결과

- `global-optima-research/HDTF`에는 약 5.24GB의 `videos.zip`이 있고 카드에는 원본 영상 400개라고 설명한다. 오바마 파일을 개별적으로 받을 수 있는 미러를 먼저 검사했다.
- `blueskyheaven/voxceleb2-mp4-binary`에는 영상 바이트와 `speaker_id`, `file_name` 필드가 있지만 원본 영상 ID를 구분하는 필드는 카드에서 확인되지 않는다. 원본 경로가 보존된 ZIP 후보를 우선한다.
- `yibo01/Trump-HQ`에서 확인한 것은 약 20MB의 LoRA 자료 ZIP이다. 실제 트럼프 영상 데이터셋으로 확인된 자료 수에 포함하지 않는다.
- GitHub의 `vitay/YouTubeFacesDB`는 기존 자료를 읽는 코드다. 별도 신청 없이 받을 수 있는 원본 영상 배포처로 세지 않는다.

## 로컬 기록

샘플 파일과 파일별 검사 기록은 Git에서 제외한 `evidence/private/hf-video-candidates`에 보관한다. `download-verification.json`에 고정 리비전과 파일별 해시가 있고 `contact-sheet.jpg`에 첫 프레임 검토 이미지가 있다. 조사 스크립트와 API 조회 결과는 상위 작업 폴더의 `.local`에 보관한다. 이번 작업에서 운영 서버와 모델 구현은 변경하지 않았다.
