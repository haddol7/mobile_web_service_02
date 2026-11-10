"""Additional evidence from the actual November 10 self webcam runs."""


def append_self_sections(doc, *, section, text, figure, pair, data_table, server_tests):
    def next_section(title):
        section(doc, title, new_page=False)
        doc.paragraphs[-1].paragraph_format.page_break_before = True

    next_section("B21 웹캠 검출과 서버 자동 등록")
    text(doc, "웹캠을 연결해 YOLO로 실시간 사람 검출을 확인했다. 서버 연동 모드에서는 프레임별 객체 종류를 비교하고 이전에 없던 종류가 검출되면 사진과 설명을 Django Post API로 자동 전송한다. 기본 객체 출현 비교 코드는 B03에 제시했다.")
    figure(doc, "evidence/screenshots/self-flow-20261110/webcam-log-vscode.png", 5.8,
           "그림 B21 실제 웹캠 실행에서 저장된 로그를 VS Code로 연 화면")
    text(doc, "로그의 REGISTERED_POST 9와 Django post 9 registered: person은 실제 웹캠 실행이 9번 사진을 자동 등록한 결과다. 아래의 연속된 1 person 출력은 이후 프레임에서도 사람이 검출됐음을 보여준다. 사용자가 사진마다 등록 버튼을 누른 것이 아니라 검출기의 출현 비교 조건에 따라 전송했다.")
    text(doc, "전송 기록의 POST /api_root/Post/ 응답은 201이었다. 서버 목록에서 9번 게시글을 다시 조회했고 저장된 JPEG가 전송 파일과 동일한지도 확인했다. 웹캠 검출, API 등록, 서버 저장과 웹 조회가 같은 사진으로 연결된다.")
    text(doc, "기본 검출 사진 등록과 사람 추적 및 얼굴 후보가 포함된 상세 관측 전송은 별도 처리다. 원본 YOLO 실행은 검출을 확인하는 모드이며 운영 서버 자동 등록은 서버 연동 모드에서 동작한다.", 9)
    text(doc, "실행 환경  WSL Ubuntu YOLO 및 PythonAnywhere Django\n기록  evidence/screenshots/self-flow-20261110/automatic-registration.json", 9)

    next_section("B22 자동 등록 사진과 실제 재진입 확인")
    pair(doc, ["evidence/screenshots/self-flow-20261110/browser-auto-post-9.png",
               "evidence/screenshots/self-flow-20261110/browser-reentry-post-14.png"],
         ["그림 B22 1 최초 웹캠 자동 등록 9번 사진", "그림 B22 2 화면 이탈 후 재진입 자동 등록 14번 사진"], (2.25, 2.25))
    text(doc, "두 화면은 Android Chrome에서 운영 주소와 해당 사진을 함께 확인한 원본 캡처다. 왼쪽은 최초 검출 때 등록된 9번, 오른쪽은 실제로 화면 밖으로 나간 뒤 돌아와 등록된 14번이다. Android 네이티브 앱의 화면과 구분한다.")
    text(doc, "재진입 시험에서는 먼저 12번 사진이 등록됐고 실제 이탈 이후 14번이 등록됐다. 각 서버 사진을 다운로드해 전송 JPEG의 SHA256과 대조한 결과 9번, 12번, 13번과 14번 모두 일치했다. 기존 게시글도 유지됐다.")
    text(doc, "이동 중 사람이 화면에 있는 상태에서 몸 검출이 잠깐 끊겼다가 복구되어 13번 사진이 추가 등록된 사례도 있었다. 강의의 객체 종류 출현 비교에 따른 사진 등록이며 사진 수를 실제 방문 횟수로 계산하지 않는다. 같은 인물 후보 연결과 최종 운영자 확인도 구분한다.")
    text(doc, "확인 주소  https://daejinha.pythonanywhere.com/post/9/\nhttps://daejinha.pythonanywhere.com/post/14/\n원본 및 대조 기록  evidence/screenshots/self-flow-20261110", 9)

    next_section("B23 본인 촬영 조건별 얼굴 후보 비교")
    pair(doc, ["evidence/screenshots/self-flow-20261110/check-shirt-input.jpg",
               "evidence/screenshots/self-flow-20261110/hood-input.jpg"],
         ["그림 B23 1 체크무늬 겉옷과 밝은 실내", "그림 B23 2 후드 겉옷과 어두운 실내"], (2.05, 2.05))
    text(doc, "별도로 촬영한 정면 등록 사진 3장을 비교 기준으로 사용했다. 기존 34명과 본인을 합친 35명 목록을 고정하고 이후의 독립적인 실시간 촬영을 비교했다. 아래 후보 일치는 촬영 대상이 본인인 이번 시험의 정답과 대조한 결과다.")
    data_table(doc, ["실제 촬영 조건", "분석 프레임", "검출 얼굴", "본인 후보", "다른 후보"], [
        ["체크무늬 겉옷과 밝은 실내", "22", "22", "22", "0"],
        ["후드 겉옷과 어두운 실내", "22", "22", "22", "0"],
        ["화면 이탈과 재진입", "99", "83", "83", "0"]], [2.5, .85, .85, .85, .85])
    text(doc, "첫 두 촬영의 유사도 범위는 각각 0.7624부터 0.8338, 0.8374부터 0.8964였다. 재진입 시험의 얼굴 미검출 16프레임에는 실제 빈 화면과 움직임이 포함된다. 등록 사진은 조회 프레임으로 재사용하지 않았다.")
    text(doc, "본인 1명의 대표 조건을 확인한 결과이며 일반 인식 정확도나 미등록 인물의 오연결률을 뜻하지 않는다. 후드와 조명을 함께 바꿨으므로 각각의 효과를 독립적으로 측정한 시험도 아니다. 운영 화면의 후보와 확인 결과는 B19와 B20에서 대조할 수 있다.", 9)

    next_section("B24 자동 등록 사진의 Android 앱 조회")
    pair(doc, ["evidence/screenshots/self-native-20261110/native-post-9.png",
               "evidence/screenshots/self-native-20261110/native-post-14.png"],
         ["그림 B24 1 Android 앱에서 조회한 자동 등록 9번", "그림 B24 2 같은 앱에서 조회한 재진입 등록 14번"], (2.25, 2.25))
    text(doc, "두 화면은 Windows의 Android API 35 에뮬레이터에서 실행한 실제 네이티브 앱 화면이다. 앱의 PhotoRepository가 PythonAnywhere API에서 받은 게시글로 상세 화면을 열고 사진을 내려받았다. 브라우저 화면을 앱 화면으로 대신하지 않았다.")
    text(doc, "9번 사진의 빨간 person 상자와 손을 얼굴 앞에 둔 모습은 B22의 최초 자동 등록 사진과 같다. 14번 사진의 왼쪽으로 돌아오는 모습과 얼굴 후보 상자도 B22 오른쪽과 동일하다. 두 다운로드 파일의 SHA256은 실제 Edge 전송 JPEG와 각각 일치했다.")
    text(doc, "서버 https://daejinha.pythonanywhere.com/\n원본 캡처와 요청 기록 evidence/screenshots/self-native-20261110", 9)

    next_section("B25 Android 동기화와 검증 결과")
    figure(doc, "evidence/screenshots/self-native-20261110/native-list.png", 2.6,
           "그림 B25 서버에서 받은 웹캠 사진의 Android 네이티브 목록")
    text(doc, "상단의 동기화 완료와 사진 10개 표시는 서버 응답으로 목록을 구성한 결과다. 첫 화면에서 재진입 사진과 앞선 촬영의 여러 사진을 확인할 수 있다. 이 화면은 동기화 완료 상태의 증빙이며 시작 화면으로 제출하지 않는다.")
    text(doc, "SelfWebcamSyncTest는 실제 서버의 9번과 14번 사진 지문, 앱 목록과 두 상세 화면을 확인해 통과했다. 모든 운영 요청은 읽기 전용 GET이었고 실제 최소 간격은 5.203초였다. 별도 Android JVM 검사 40개와 Lint도 통과했으며 Lint 오류는 0개다.", 9)

    next_section("B26 AI 답변의 숫자와 날짜 검증")
    figure(doc, "evidence/screenshots/self-flow-20261110/answer-count-check-vscode.png", 5.8,
           "그림 B26 숫자 표현을 해당 DB 집계 필드와 대조하는 실제 소스")
    text(doc, "답변에 사용한 숫자가 근거 어딘가에 존재하는지만 검사하면 다른 항목의 숫자를 바꾸어 말하는 오류를 놓칠 수 있다. 숫자와 함께 사용한 추적, 통과, 후보, 확인 프로필 및 영상 출처 표현을 해당 facts 필드와 대조하도록 보완했다.")
    data_table(doc, ["검사 조건", "입력 답변", "결과"], [
        ["추적 23개, 통과 6건", "선 통과는 23건입니다", "거절"],
        ["추적 23개, 통과 6건", "추적 23개, 선 통과 6건", "허용"],
        ["확인 추적 1개, 전체 추적 4개", "확인된 추적은 4개", "거절"],
        ["분석일 2026년 11월 10일", "촬영일이 2026년 11월 10일", "거절"]], [2.25, 2.65, .8])
    text(doc, "위 사례는 유료 모델 응답을 흉내 낸 로컬 회귀 검사다. 실제 LLM의 정답률을 측정한 결과와 구분한다. 검증을 통과하지 못한 생성 문구는 표시하지 않고 DB 기록에 따른 답변을 제공한다. 이 검사는 지원하는 숫자와 날짜 표현의 오류를 줄이며 모든 자연어 주장의 참을 보장하는 것은 아니다.", 9)

    next_section("B27 본인 기록의 RAG 검색 조건과 결과")
    figure(doc, "evidence/screenshots/rag-guards-20261110/scope-code.png", 5.8,
           "그림 B27 검색 조건과 영상 설명을 대조하는 실제 소스 및 실행 커버리지")
    text(doc, "하대진의 평소 모습, 모자 착용, 화면 이탈과 재진입 촬영을 RAG 색인에 반영했다. 촬영 설명과 인물 ID 및 날짜를 텍스트로 구성하고 고정 질문 3개와 함께 임베딩했다. text-embedding-3-small의 512차원 벡터를 사용했으며 이 배치의 실제 입력은 533토큰이었다. 사진과 얼굴 특징 벡터는 임베딩 API에 보내지 않았다.")
    text(doc, "인물과 날짜로 DB 범위를 먼저 제한하고 명시된 모자 착용이나 재진입 조건은 촬영 설명과 대조한다. 이 범위 안에서 임베딩 유사도와 제목 일치도를 함께 사용한다. 모자 조건은 촬영 설명에 저장한 메타데이터를 검색하는 것이며 사진에서 복장을 자동 판별한 결과는 아니다.")
    data_table(doc, ["실제 운영 고정 질문", "예상 출처", "반환 출처", "추가 API"], [
        ["하대진이 발견된 웹캠 촬영을 정리해줘", "3건", "3건", "0회"],
        ["하대진의 모자 착용 촬영을 찾아줘", "1건", "1건", "0회"],
        ["하대진의 화면 이탈과 재진입 촬영을 찾아줘", "1건", "1건", "0회"]], [3.4, .85, .85, .8])
    text(doc, "위 세 조회는 저장된 질문 벡터를 재사용했다. 별도의 운영 DB 검사 5개에서는 전체와 확인 기록 및 11월 10일에 3개 출처, 11월 9일과 11월 11일에 0개 출처를 확인했다. 날짜를 임의로 바꾸지 않았다. 고정 예제의 결과이며 일반 검색 정확도를 뜻하지 않는다.", 9)

    next_section("B28 실제 생성 답변과 근거 사진 대조")
    figure(doc, "evidence/screenshots/self-flow-20261110/rag-final-ai.png", 3.3,
           "그림 B28 운영 AI 답변과 선택된 근거 사진 부분", crop_bottom=.45)
    text(doc, "질문은 하대진의 모자 착용 촬영을 찾아달라는 내용이다. 실제 gpt-4o-mini 답변은 2026년 11월 10일의 본인 모자 착용 웹캠 인식 확인을 제시했고 근거 사진도 해당 촬영 한 장만 표시했다. 선택된 출처의 확인 프로필 1개와 사진의 얼굴을 DB 응답 및 원본 화면과 대조했다.")
    text(doc, "촬영 출처 1개, 확인된 인물 프로필 1개와 사진 1장은 서로 다른 항목이다. 사진 수나 추적 번호를 방문 횟수로 표현하지 않는다. 이 화면은 실제 생성에 성공한 한 질문의 내용 검증이며 모든 질문의 정답률을 보장하지 않는다.", 9)
    text(doc, "전체 원본 캡처와 응답은 evidence/screenshots/self-flow-20261110/rag-final-ai.png 및 evidence/history/self-rag-20261110.json에 보관했다. 그림은 하단의 빈 공간과 입력칸을 제외한 답변 영역이다.", 9)

    next_section("B29 AI 생성 실패 시 기록 조회 유지")
    figure(doc, "evidence/screenshots/self-flow-20261110/rag-db-fallback.png", 3.4,
           "그림 B29 실제 생성 실패 때 제공한 DB 답변과 세 촬영의 근거 사진 부분", crop_bottom=.42)
    text(doc, "초기 실제 생성 요청이 실패했을 때의 상단 답변이다. AI 연결을 받지 못해 저장 기록으로 답변했다는 안내와 함께 추적 기록 4개, 선 통과 0건 및 세 촬영의 사진을 표시했다. 이를 실제 LLM 생성 성공 화면으로 계산하지 않는다.")
    text(doc, "실패 유형은 연결, HTTP 응답, 형식 및 근거 검증 등으로 구분하고 제공자 응답 본문이나 인증값을 화면에 노출하지 않는다. 생성 대기 시간을 보완하고 B26의 검사를 적용했다. 이후 B28의 실제 생성 결과와 촬영 한 건의 근거를 별도로 확인했다.", 9)
    text(doc, "앞선 본인 기록 검증의 외부 API 사용은 임베딩 1회와 생성 시도 4회다. 최종 RAG 배포 후의 추가 생성 1회는 B37에 별도로 제시한다. 현재 서버 전체 생성 한도는 한국 날짜 기준 하루 10회다. 이후 새 기록이나 확인 상태가 바뀌면 색인 갱신 여부를 확인해야 하며 유료 색인을 자동으로 반복 생성하지 않는다.", 9)

    next_section("B30 최종 본인 확인 상태와 실시간 촬영 표시")
    figure(doc, "evidence/screenshots/self-flow-20261110/profile-live-final.png", 2.4,
           "그림 B30 운영자 확인 후 세 촬영의 최신 인물 이력", crop_bottom=.10)
    text(doc, "운영자 확인 후 하대진의 촬영 3건과 확인 추적 4개, 후보 0개가 표시된다. 재진입, 모자 착용과 평소 모습 모두 확인됨으로 조회된다. B19와 B20은 확인 전 과정의 캡처이며 이 그림은 그 이후의 상태다.")
    text(doc, "실시간 카메라와 분석일 기준 안내를 표시하고 각 촬영의 기록 사진 수를 구분했다. 실시간 기록에 존재하지 않는 영상 재생 초는 표시하지 않는다. 4개의 확인 추적은 한 사람의 세 촬영에서 생성된 기록이며 사람 4명이나 방문 4회를 뜻하지 않는다.", 9)

    next_section("B31 최종 서버 실행 결과와 코드 커버리지")
    figure(doc, "evidence/screenshots/rag-guards-20261110/tests-302.png", 5.8,
           "그림 B31 1 WSL에서 저장된 실제 전체 검사 로그의 마지막 결과")
    text(doc, f"RAG 회귀 보완 후 WSL 가상환경에서 python PhotoBlogServer/tools/verify_security.py를 실행했다. 전체 Django {server_tests}개와 별도 HTTP 엔진 15개가 통과했으며 HTTP 15개는 전체 사례에 포함된 재실행이다. 시스템 검사와 마이그레이션 일치 검사도 통과했다. 위 화면은 저장된 원본 실행 로그를 읽기 전용 로컬 브라우저로 연 것이다.", 9)
    next_section("B32 코드 커버리지와 검증 범위")
    figure(doc, "evidence/screenshots/rag-guards-20261110/coverage.png", 5.8,
           "그림 B32 같은 실행의 실제 Coverage HTML 보고서")
    text(doc, "전체 코드 커버리지는 93.7%다. 이번 보완에는 숫자와 날짜의 필드 대응, 촬영 질문 해석, 검색 조건 밖 출처 제외와 외부 API 실패 처리를 포함했다. 웹 단위 검사 76개와 Android JVM 40개도 통과했고 Android Lint는 오류 0개, 경고 9개였다. 커버리지는 실행된 코드 범위이며 모델의 인식 정확도나 모든 운영 상황의 성공률과 구분한다.", 9)
    text(doc, "B23은 실제 본인의 조건별 촬영, B24와 B25는 운영 사진의 네이티브 앱 조회, B27과 B28은 고정 질문 검색과 한 건의 실제 생성 내용 대조다. 자동 검사의 통과와 실제 화면 및 입력 자료의 대조를 각각 확인했다.\n원본 결과 evidence/content/server/verification.json\nAndroid 결과 evidence/content/android/verification.json", 9)
