# 관측 사진의 검출 박스

관측 목록과 상세 사진, 인물별 발견 장면과 AI 답변의 근거 사진에 저장된 사람 및 얼굴 검출 영역을 표시한다. 사람 몸은 파란색 박스와 추적 번호로, 얼굴 후보는 주황색 박스와 인물 이름 및 유사도로 표시한다. 확인된 얼굴은 초록색이며 데이터셋 확인은 정답 확인으로 구분한다. 인물 미확인 또는 몸 추적에 연결되지 않은 얼굴은 회색으로 표시한다. 유사도 수치는 동일 인물일 확률과 구분한다.

API의 image_url은 기존 비공개 사진 경로에 boxes=1을 지정한다. 웹과 Android는 같은 URL의 사진을 받는다. 서버는 저장된 몸 좌표와 얼굴 좌표를 실제 게시 사진 크기에 맞춰 비례 변환하고 이미지 안으로 자른다. 원본 크기 정보가 없거나 영역 좌표가 유효하지 않으면 해당 박스를 그리지 않는다. 얼굴 추론을 다시 실행하거나 표시용 좌표를 임의로 만들지 않는다.

원본 이미지 파일과 DB는 그대로 보관한다. boxes=1 사진은 요청 시 Pillow로 만든 별도 응답이고 boxes가 없는 기존 경로는 원본을 반환한다. 얼굴 비교용 track 경로와 등록 얼굴 사진에는 박스를 넣지 않는다. 기존 운영자 권한과 private, no-store 정책을 유지한다. 한글 라벨은 Android에서도 쓰는 Pretendard 글꼴과 OFL 이용 조건을 함께 배포한다.

WSL에서 `python PhotoBlogServer/tools/verify_content.py`를 실행해 Django 테스트 250개와 실제 HTTP 검사 15개가 통과했다. 이 중 새 검사 다섯 개는 사진 축소에 따른 좌표 변환, 경계 밖 좌표, 잘못된 크기, 확인 및 미확인 색상, 원본 보존과 비공개 접근, 전체 사진과 얼굴 잘라보기의 구분을 확인한다. Windows의 `node tools/verify-mobile-web.mjs`에서도 기존 웹 검사 76개가 통과했다. Android 에뮬레이터의 작은 화면에서 WebView 전체 화면 검사 1개가 통과했고 관측 사진의 박스 및 상세 창을 캡처했다. 실행 자료는 evidence/ui-audit/after-web.json에 있다.

`tools/preview_detection_boxes.py`는 실제 저장된 출입 영상 사진과 검출 좌표로 16개 박스의 한글 표기를 점검하는 미리보기를 만든다. 미리보기와 운영 캡처는 evidence/private/detection-boxes에 보관한다. 배포 도구 tools/deployment/deploy_detection_boxes.py는 허용한 파일의 해시와 복구 사본을 확인한 뒤 운영 사진의 박스 수, 원본과의 구분, 비인증 접근 차단을 검사한다. 배포 증빙은 evidence/ui-audit/detection-boxes-deployment.json이다.

이름표는 사람과 얼굴 박스 주변의 여섯 위치를 비교해 기존 이름표 및 얼굴과 겹치는 면적이 작은 곳에 배치한다. 실제 운영 브라우저에서 관측 목록과 상세 사진을 확인하고 production-list.jpg 및 production-detail.jpg로 보관한다.

이번 기능은 기존 분석 결과를 표시한다. 임베딩 갱신, LLM 생성 및 모델 API 호출은 0회다.
