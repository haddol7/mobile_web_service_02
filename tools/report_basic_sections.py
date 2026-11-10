"""Explain each basic Assessment 02 evidence image against the original rubric."""

BASIC_EVIDENCE = []


def append_basic_sections(doc, *, text, section, figure, data_table, record, server_tests):
    BASIC_EVIDENCE.clear()
    current = "evidence/screenshots/basic-explained-20261110/"
    enlarged = "evidence/screenshots/final-review-20261110/"
    browser = "evidence/screenshots/basic-20261110/"

    def proof(label, items, path, width, caption, paragraphs, crop_bottom=0):
        figure(doc, path, width, caption, crop_bottom=crop_bottom)
        for paragraph in paragraphs:
            text(doc, paragraph)
        BASIC_EVIDENCE.append({"label": label, "assessment_ids": items, "path": path,
            "caption": caption, "explanation": paragraphs})

    section(doc, "기본 기능의 구현과 확인 순서")
    text(doc, "기본 기능은 Edge에서 검출한 사진을 Django에 등록하고 서버와 모바일에서 같은 결과를 확인하는 과정이다. Edge PC의 YOLOv5가 카메라나 영상의 객체를 검출한다. 직전 프레임에 없던 객체 종류가 나타나면 검출 박스를 그린 사진을 JPEG로 저장하고 인증된 Post API 요청으로 서버에 전송한다. Django는 사진과 제목 및 검출 내용을 저장하고 Android와 브라우저에 제공한다.")
    text(doc, "무료 PythonAnywhere는 API, 데이터 저장과 웹 조회를 담당한다. YOLOv5 추론은 WSL Ubuntu의 Edge PC에서 수행한다. 기본 전송의 판단 단위는 사람 수나 개인의 신원이 아니라 객체 종류의 출현 변화다. 사람 추적과 얼굴 후보 비교는 뒤의 추가 기능에서 설명한다.")
    data_table(doc, ["기본 항목", "확인할 구현과 실제 결과", "대응 증빙"], [
        ["1", "필수 세 폴더와 보고서를 별도 저장소 루트에 배치", "B01"],
        ["2", "공통평가 02 전용 GitHub URL과 제출 파일 업로드", "B01 및 원격 검증 기록"],
        ["3", "변경 없는 원본 detect.py와 실제 카메라 검출", "B02, B08 1과 2"],
        ["4", "객체 출현 비교, 사진 저장과 API 전송의 VS Code 화면", "B03 1부터 4"],
        ["5", "로컬 API 루트 및 등록 게시글 JSON 응답", "B04 1과 2"],
        ["6", "로컬 브라우저의 등록 사진 목록과 이미지", "B05 1과 2"],
        ["7", "전송된 같은 사진의 Android 및 모바일 웹 표시", "B07 1부터 5, B09 2"],
        ["8", "PythonAnywhere 운영 도메인의 API 응답", "B09 1"],
        ["9", "운영 브라우저의 등록 사진 목록과 상세 이미지", "B09 3과 4"]], [.75, 3.75, 1.4])
    text(doc, "증빙의 B번호는 본문과 그림을 찾기 위한 번호다. 평가표의 기본 항목 번호는 각 사진 설명에 따로 표시했다. 로컬 등록 시험, 영상 입력 시험과 운영 등록은 각각의 실행으로 기록했고 사진의 파일 동일성도 같은 실행의 서버와 클라이언트 사이에서 확인했다.")

    section(doc, "B01 제출 폴더 구조와 별도 저장소")
    text(doc, "기본 항목 1은 PhotoBlogServer, PhotoViewer, YOLOv5와 수행 결과 보고서의 루트 배치를 요구한다. 공통평가 02 전용 저장소는 https://github.com/haddol7/mobile_web_service_02 이며 공통평가 01의 middle_project 저장소와 분리했다.")
    proof("B01", ["1", "2"], "evidence/screenshots/github-folder-structure.jpg", 6.1,
        "그림 B01 기본 항목 1과 2에 대응하는 별도 저장소의 폴더 구성", [
        "사진의 저장소 이름은 mobile_web_service_02이고 브랜치는 main이다. 파일 목록에서 세 필수 폴더와 Word 보고서 항목을 확인할 수 있다. PhotoBlogServer는 Django API와 저장 및 웹 조회, PhotoViewer는 Android 클라이언트, YOLOv5는 Edge 검출과 전송을 담당한다. 실제 보고서 파일명은 모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx다.",
        "이 사진은 최초 업로드 당시의 루트 구성을 보여준다. 전용 저장소의 main 브랜치에 세 필수 폴더와 보고서를 함께 두었다. 해당 업로드 검증에서는 실제 원격 Word를 내려받아 당시 로컬 검수본과 SHA256을 비교했다. SHA256은 파일 내용으로 계산하는 지문이며 두 값이 같으면 두 문서의 바이트가 같다는 의미다."])
    text(doc, "기본 항목 1은 폴더 구성, 항목 2는 전용 저장소 URL과 당시 업로드 기록으로 확인했다. evidence/github-final-report.json은 해당 커밋의 이전 보고서 검증을 보관한다. 현재 RAG 보완본의 검증 지문과 배치 결과는 별도의 로컬 검수 기록으로 구분한다.", 9)

    section(doc, "B02 원본 YOLOv5 실행 결과")
    text(doc, "기본 항목 3은 변경 없는 detect.py의 실행과 객체 인식 결과를 요구한다. Ultralytics YOLOv5 v7.0 원본을 YOLOv5/baseline/detect.py에 별도로 보관했다. 원본 출처는 공식 커밋 915bbf294bb74c859f0b41f1c23bc395014ea679이며 파일과 공식 yolov5s.pt 가중치의 SHA256을 대조한 뒤 실행했다.")
    proof("B02", ["3"], "evidence/yolo-pipeline/original-image/bus.jpg", 3.0,
        "그림 B02 기본 항목 3의 원본 모델 정지 이미지 검출 결과", [
        "입력은 공식 예제 bus.jpg다. 사진의 빨간 박스와 person 라벨은 검출된 사람 네 명을, 초록 박스와 bus 라벨은 버스 한 대를 나타낸다. 라벨 옆 숫자는 해당 객체에 대한 모델의 신뢰 점수다. 여러 사진에 대한 전체 정확도와는 다른 값이다.",
        "원본 실행에서 객체가 검출되고 박스 및 클래스 이름이 표시되는 것을 확인했다. 원본 파일 확인과 정지 이미지 결과는 설치 및 모델 로딩의 근거이며, 강의 6쪽의 실제 카메라 0번 실행은 B08의 웹캠 사진과 실행 기록으로 함께 제시한다. 서버 전송용 변경 코드는 원본 보관본과 별도의 YOLOv5/detect.py에 구현했다."])
    text(doc, "원본 검출 명령  python tools/run_edge.py --baseline --source data/images/bus.jpg --device cpu\n원본 출처와 해시  docs/upstream/provenance.json\n실제 실행 결과  evidence/yolo-pipeline/verification.json", 9)

    section(doc, "B03 객체 출현 비교 코드")
    text(doc, "기본 항목 4에 대응하는 실제 VS Code 화면이다. changedetection.py의 초기화와 add 함수가 클래스별 현재 검출 상태를 이전 상태와 비교한다. 코드 화면은 11월 10일 최종 작업 소스에서 다시 캡처했다.")
    proof("B03 1", ["4"], enlarged + "changedetection-state-vscode.png", 6.1,
        "그림 B03 1 기본 항목 4의 객체 종류 상태 비교와 전송 조건", [
        "사진의 current는 현재 프레임에서 각 객체 종류가 검출됐는지를 0과 1로 표현한 배열이다. previous는 같은 입력 스트림의 직전 상태다. appeared에는 현재 값이 1이고 이전 값이 0인 종류만 들어간다. appeared가 비어 있으면 등록 없이 반환하고 새 종류가 있으면 send를 호출한다.",
        "따라서 사람이 계속 보이는 장면을 매 프레임 등록하지 않는다. 객체가 사라진 프레임에서 상태가 0으로 바뀐 뒤 다시 나타나면 새 등록 대상이 된다. 강의의 과거 0과 현재 1의 변화 조건을 구현한 부분이며, 개별 인물의 동일성을 판단하는 동작은 추가 인물 추적 기능에서 처리한다."])
    text(doc, "객체 출현 조건의 실제 등록 결과는 B05 2의 네 입력 실행 로그에서 확인한다.", 9)

    section(doc, "B03 검출 사진 저장과 HTTP 등록")
    proof("B03 2", ["4"], enlarged + "changedetection-upload-vscode.png", 6.1,
        "그림 B03 2 기본 항목 4의 JPEG 저장과 인증된 Post 요청", [
        "사진의 send 함수는 검출 박스가 그려진 프레임을 날짜별 detected 폴더에 저장한다. cv2.resize가 전송 사진을 320 x 240으로 맞추고 cv2.imwrite가 JPEG를 만든다. 새로 등장한 클래스 이름으로 title과 text를 구성하며 text에는 검출 시각도 기록한다.",
        "저장한 JPEG는 image 필드, 제목과 검출 설명은 일반 폼 필드로 묶어 /api_root/Post/에 multipart POST 요청으로 전송한다. 인증 헤더는 실제 Django 서버의 DRF Token 방식에 맞췄다. 인증값은 비공개 환경변수에서 전달받으며 제목과 사진을 서버에 등록하는 기본 기능은 강의 8쪽부터 10쪽의 흐름을 따른다.",
        "응답 코드가 201이고 응답 JSON에 정수 id가 있어야 등록 성공으로 반환한다. 실패한 요청의 사진 파일은 로컬에 남는다. 이 화면은 성공 여부를 검사하는 구현 코드이며 실제 실행 결과는 B05의 등록 로그와 로컬 조회 사진으로 연결한다. 서버의 작성자와 생성 및 게시 날짜는 서버에서 기록한다."])

    section(doc, "B03 검출 결과 배열과 표시 이미지")
    proof("B03 3", ["4"], enlarged + "detect-classes-vscode.png", 6.1,
        "그림 B03 3 기본 항목 4의 검출 클래스 배열과 박스 표시 연결", [
        "사진은 최종 detect.py의 추론 결과 처리 부분이다. 프레임마다 detected_current를 모두 0으로 만들고 검출된 cls에 해당하는 칸을 1로 설정한다. 같은 종류가 여러 개 검출돼도 해당 칸은 1이므로 기본 전송에서는 종류의 출현 유무를 비교한다.",
        "검출 좌표는 원본 프레임 크기로 변환하고 클래스 이름과 점수로 박스를 표시한다. 이 표시 이미지가 다음 그림의 changes.add에 전달된다. 클래스 상태를 계산하는 부분과 전송할 이미지가 만들어지는 위치를 함께 확인할 수 있어, 검출 결과와 서버 등록 코드가 분리된 채 남아 있지 않음을 보여준다."])

    section(doc, "B03 최종 추론 루프의 서버 전송 연결")
    proof("B03 4", ["4"], enlarged + "detect-upload-vscode.png", 6.1,
        "그림 B03 4 기본 항목 4의 최종 추론 루프와 등록 결과 처리", [
        "사진의 240번대 코드에서 changes.add에 클래스 이름, detected_current, 저장 위치와 표시 프레임 im0를 넘긴다. 등록에 성공한 반환값이 있을 때만 Django post와 게시글 번호를 로그로 출력한다. 실패 시에는 등록 성공을 출력하지 않고 로컬 파일 보존을 안내한다.",
        "주변의 person_tracking과 person_history 분기는 추가 인물 분석과 관측 이력 전송을 위한 코드다. 기본 Post 등록은 changes.add 경로로 유지한다. B03 1의 출현 비교와 B03 2의 저장 및 요청이 실제 추론 루프에서 호출되므로 기본 항목 4의 수정 코드가 실행 경로에 연결돼 있음을 확인했다."])

    section(doc, "B04 로컬 서버 API 확인")
    text(doc, "기본 항목 5는 로컬 서버의 API 브라우저 응답이다. 11월 10일 WSL 검증 서버를 Android Chrome에서 열어 주소와 상태 및 결과가 함께 보이도록 확인했다.")
    proof("B04 1", ["5"], browser + "local-api-root.png", 6.0,
        "그림 B04 1 기본 항목 5의 localhost API 루트와 HTTP 200", [
        "주소창의 localhost:8020/api_root/는 로컬 API 루트다. 응답 영역에 GET /api_root/, HTTP 200 OK와 JSON의 Post 링크가 보인다. Django REST Framework 라우터가 정상 응답하고 게시글 API의 위치를 제공하는 결과다.",
        "에뮬레이터의 localhost:8020은 ADB 포트 전달로 WSL의 검증 서버 36073 포트에 연결했다. Android 앱은 10.0.2.2:36073으로 같은 검증 서버에 접근했다. 서버 시작 시 임시 포트가 달라질 수 있으므로 주소와 함께 게시글 번호 및 파일 대조 결과를 기록했다. 실제 등록된 데이터는 다음 Post 목록 응답에서 확인한다."])

    section(doc, "B04 로컬 게시글 JSON 등록 결과")
    proof("B04 2", ["5", "6"], browser + "local-api-posts.png", 6.0,
        "그림 B04 2 기본 항목 5의 Post 목록과 실제 등록 데이터", [
        "이 화면은 localhost:8020/api_root/Post/의 조회 결과다. HTTP 200 아래에 id 2와 id 1의 두 게시글이 반환됐다. 제목은 YOLO: person, bus이고 text에는 검출 종류와 시각이 기록돼 있다. image는 서버가 제공하는 JPEG URL이다. 작성자와 생성 및 게시 날짜를 포함해 기본 일곱 응답 필드를 유지한다.",
        "Post 목록에 두 id와 각각의 image 경로가 반환되므로 검출 내용이 서버 게시글과 사진 경로로 저장됐음을 확인할 수 있다. 생성 요청의 성공 응답은 201이고 이 사진의 200은 저장 결과를 다시 조회한 응답이다. 등록 자료는 11월 5일의 실제 추론 시험 결과이며 11월 10일에 다시 열어 촬영했다. 두 게시글은 B05 목록과 B07 모바일 사진에 대응한다."])

    section(doc, "B05 로컬 목록과 저장 이미지 확인")
    proof("B05 1", ["6"], browser + "local-list.png", 6.1,
        "그림 B05 1 기본 항목 6의 localhost 등록 목록과 검출 이미지", [
        "주소창은 localhost:8020/photos/이고 화면의 사진 2와 사진 1 카드는 앞 JSON의 id 2와 id 1에 해당한다. 두 카드에 YOLO: person, bus 제목과 검출 박스가 포함된 사진이 표시된다. API에 저장한 제목과 image 파일을 서버의 웹 화면에서도 읽어 표시한 결과다.",
        "같은 bus 사진이 두 건 있는 이유는 최초 등장과 사라진 뒤 재등장을 별도로 등록했기 때문이다. 같은 장면이 계속되는 두 번째 입력에서는 추가 등록하지 않았다. 두 사진의 전송 JPEG와 서버 저장 및 HTTP 조회 파일의 SHA256이 일치했다. 화면에서 보이는 등록일은 11월 5일이고 이 목록의 재조회와 캡처는 11월 10일이다. 기본 Post 자료는 사진 보관함에서 확인하며 추가 관측 기록의 집계와 구분한다."])

    section(doc, "B05 실제 추론과 등록 실행 로그")
    proof("B05 2", ["4", "6"], enlarged + "local-upload-log.png", 6.0,
        "그림 B05 2 실제 WSL 검출과 게시글 등록의 저장 로그", [
        "11월 5일 WSL에서 실행한 server-registration.txt를 VS Code로 열어 캡처한 보조 증빙이다. 로그에는 네 입력의 추론 결과와 Django post 1 registered 및 Django post 2 registered가 있다. 첫 bus 입력과 마지막 재등장 입력에서 등록되고, 중간의 같은 bus와 빈 화면에서는 추가 등록이 출력되지 않았다. 마지막 Exit code: 0은 정상 종료를 뜻한다.",
        "이 실행은 공식 정지 이미지와 빈 프레임을 순서대로 입력한 시험이다. B08의 별도 30프레임 영상 시험과 실행을 구분한다. 원래 등록 때의 임시 서버 포트와 재조회 서버의 포트는 다르지만 게시글 1과 2의 자료와 JPEG를 보존해 대조했다. 이 사진은 기존 실제 실행 로그를 보여주며 B04의 JSON, B05 1의 웹 이미지와 같은 등록 결과를 연결한다."], crop_bottom=.20)
    data_table(doc, ["순서", "입력 장면", "이전 상태와 현재 상태", "등록"], [
        ["1", "사람과 버스 등장", "없음에서 검출됨으로 변화", "1번 게시글"],
        ["2", "같은 장면 유지", "검출됨 상태 유지", "추가 등록 없음"],
        ["3", "빈 화면", "검출됨에서 없음으로 변화", "추가 등록 없음"],
        ["4", "사람과 버스 재등장", "없음에서 검출됨으로 변화", "2번 게시글"]], [.45, 1.65, 2.6, 1.2])
    text(doc, "근거 기록  evidence/yolo-pipeline/verification.json과 server-registration.txt\n등록 사진의 SHA256  " + record("evidence/yolo-pipeline/verification.json")["real_pipeline"]["uploads"][0]["image_sha256"], 9)

    section(doc, "B06 자동 검증 결과")
    text(doc, "아래 검사는 코드의 분기, 서버 저장과 조회 및 클라이언트 처리를 보조 검증한 결과다. WSL 실행, Windows 검사와 실제 기기 화면을 구분해 기록했다. 각 기본 항목의 요구 사진은 해당 본문에 제시한다.")
    data_table(doc, ["구분", "검증 결과", "환경"], [
        ["Django 전체", f"{server_tests}개 통과", "WSL Ubuntu"],
        ["실제 HTTP 엔진", "전체 중 15개 별도 재실행 통과", "WSL Ubuntu"],
        ["Edge 단위", "30개 통과", "WSL Ubuntu"], ["웹 단위", "76개 통과", "Windows Node"],
        ["Android JVM", "40개 통과", "Windows"], ["Android Lint", "오류 0개, 경고 9개", "Windows"]], [1.3, 3.15, 1.45])
    text(doc, "HTTP 15개는 Django 전체 검사에 포함된 사례를 별도 HTTP 엔진으로 재실행한 결과다. 전체 검사 수에 중복 합산하지 않는다. 기본 등록 동작의 실제 입력과 출력은 B05 2, 모바일의 서버 및 사진 대조는 B07 5에서 확인한다.")

    section(doc, "B07 Android 기본 사진 목록")
    proof("B07 1", ["7"], browser + "android-native-list.png", 2.6,
        "그림 B07 1 기본 항목 7의 실제 Android 앱 사진 목록", [
        "Windows의 Android Emulator에서 실제 02 앱으로 WSL 서버를 조회한 화면이다. 상단의 동기화 완료와 사진 2개, 두 YOLO 카드의 제목과 검출 이미지가 보인다. 앱이 기본 Post API를 읽고 서버에 등록된 두 사진을 목록으로 표시한 결과다.",
        "접속 주소는 http://10.0.2.2:36073/이며 B04 브라우저와 같은 검증 서버다. 11월 10일 기기 검사에서 서버의 게시글 2번을 찾고 사진 바이트를 대조한 뒤 목록과 상세 표시를 확인했다. 따라서 이 사진은 단순 접속 안내 화면이 아니라 전송된 검출 사진이 실제 앱 목록에 나타난 기본 항목 7의 증빙이다."])

    section(doc, "B07 Android 기본 사진 상세")
    proof("B07 2", ["7"], browser + "android-native-detail.png", 2.6,
        "그림 B07 2 기본 항목 7의 Android 검출 사진 상세", [
        "앞 목록에서 YOLO 사진을 열면 사진 상세, 제목과 검출 박스 이미지 및 New objects 본문이 표시된다. 본문의 person, bus와 원래 검출 시각은 서버 게시글의 내용이다. 목록의 작은 미리보기에서 실제 저장 이미지와 본문을 확인하는 상세 화면까지 이동한 결과다.",
        "기기 검사는 게시글 2번의 image URL에서 내려받은 바이트의 SHA256을 로컬 전송 사진과 비교했다. 같은 제목을 임의로 표시한 화면이라는 판단을 피하기 위해 이미지 파일의 지문도 확인했다. 화면은 사진 표시를, B07 5의 검사 기록은 접속 주소와 대상 id 및 파일 대조를 각각 입증한다."])

    section(doc, "B07 Android 모바일 웹 목록")
    proof("B07 3", ["7"], browser + "local-mobile-list.png", 2.6,
        "그림 B07 3 기본 항목 7의 Android Chrome 사진 목록", [
        "이 사진은 네이티브 앱과 별도로 Android Chrome에서 연 로컬 웹 화면이다. 주소창의 localhost:8020/photos/와 두 열의 사진 카드가 보인다. 카드의 사진 번호 2와 1, 제목 및 박스 이미지는 B04 JSON과 B05 웹 목록의 같은 자료다.",
        "모바일에서도 서버에 저장된 JPEG가 표시되고 각 카드를 선택해 상세 화면으로 이동할 수 있다. localhost 주소는 ADB 전달로 WSL 서버에 연결했다. 네이티브 앱과 모바일 웹이 같은 기본 등록 자료를 각각의 화면에서 제공한다는 보조 증빙이며, 다음 그림에서 실제 상세 이미지를 확인한다."])

    section(doc, "B07 Android 모바일 웹 상세")
    proof("B07 4", ["7"], browser + "local-mobile-detail.png", 2.6,
        "그림 B07 4 기본 항목 7의 Android Chrome 게시글 2번 상세", [
        "주소창은 localhost:8020/post/2/다. 끝의 2는 API JSON과 앱 검사에서 확인한 게시글 2번이며, 화면에 YOLO 제목과 사람 및 버스의 검출 박스와 자동 등록 본문이 보인다. 서버의 목록에서 선택한 자료를 실제 상세 경로로 열어 확인했다.",
        "이 결과로 모바일 브라우저에서 서버에 전송된 사진과 설명을 모두 열람할 수 있음을 확인했다. 사진의 등록 시각은 원래 전송 시험의 시각이고 이 화면의 재조회일은 11월 10일이다. 네이티브 앱 두 장과 모바일 웹 두 장은 각각 같은 서버 자료의 목록 및 상세에 대응한다."])

    section(doc, "B07 Android 기기 검사 기록")
    proof("B07 5", ["7"], enlarged + "android-sync-record.png", 6.0,
        "그림 B07 5 실제 Android 기기의 서버와 사진 대조 결과", [
        "이 사진은 11월 10일 실제 기기 검사가 저장한 android-native-sync.json을 VS Code로 열어 확인한 것이다. server는 10.0.2.2:36073, post_id는 2이고 image_sha256은 B05의 로컬 전송 JPEG와 같다. list_visible과 detail_visible이 모두 true라서 목록과 상세를 확인한 상태를 기록했다.",
        "실제 검사 코드는 서버 목록에서 해당 게시글을 찾고 사진을 내려받아 해시를 비교한 뒤 앱 화면이 준비됐는지 검사한다. 이 기기 검사 1개가 통과했으며 화면 캡처와 함께 결과를 보관했다. read_only는 이 조회 검사가 새 게시글을 등록하지 않고 저장된 자료를 확인했다는 실행 범위다."], crop_bottom=.55)
    text(doc, "기기 검사와 화면  evidence/basic-verification-20261110/android-native-sync.json 및 android-native-sync.txt\n검사 코드  PhotoViewer/app/src/androidTest/java/com/haddol7/photoviewer/ui/YoloSyncTest.java", 9)

    section(doc, "B08 영상 입력과 전송 실패 처리")
    text(doc, "객체 출현 비교의 연속 입력 동작은 별도의 30프레임 영상으로도 확인했다. 공식 bus.jpg와 빈 프레임을 조합해 초당 5프레임으로 실제 YOLOv5에 입력했고 전송 대상은 기존 데이터와 분리한 WSL 검증 서버였다. 이 영상 시험은 B05의 네 입력 정지 이미지 시험과 별도 실행이다.")
    data_table(doc, ["입력 순서", "내용", "새 게시글"], [
        ["처음 6프레임", "빈 화면", "0개"], ["다음 12프레임", "사람과 버스가 연속 등장", "첫 프레임의 1개"],
        ["다음 6프레임", "빈 화면", "0개"], ["마지막 6프레임", "사람과 버스가 재등장", "1개"]], [1.35, 3.1, 1.45])
    text(doc, "이 실행에서 새 사진 두 개가 320 x 240 JPEG로 등록됐다. 연속 등장 구간에서는 최초 한 건만 전송했고 빈 구간을 지나 재등장할 때 한 건을 더 전송했다. 잘못된 인증값의 요청은 거부됐고 기존 게시글 수가 유지됐으며 실패 요청의 사진은 로컬에 남았다. 입력 변화와 실제 등록 건수가 기본 출현 비교 조건에 맞는지 확인한 결과다.")
    text(doc, "추가 관측 이력 전송의 재시도 검사에서는 같은 패킷 재전송과 서버 저장 후 응답 유실을 재현했다. 같은 기록이 중복 생성되지 않고 전송 완료 후 대기 패킷이 비워지는 것을 확인했다. 이 결과는 추가 기능의 전송 처리에 해당하며 기본 Post 전송의 파일 보존과 구분한다.")
    text(doc, "근거 기록  evidence/video-flow/verification.json, evidence/history/verification.json\n실행 환경  evidence/environment/wsl-runtime.json", 9)

    section(doc, "B08 원본 검출기의 실시간 웹캠 실행")
    text(doc, "기본 항목 3에서 참조한 강의 6쪽의 카메라 0번 실행이다. 11월 10일 노트북의 Acer HD User Facing 웹캠을 USB/IP로 WSL2 Ubuntu에 연결하고 /dev/video0에서 실제 프레임을 읽었다. 수정하지 않은 YOLOv5 v7.0 원본을 카메라 인덱스 0으로 실행했다.")
    proof("B08 1", ["3"], "evidence/notebook-20261110/02_웹캠_증빙/웹캠_실시간_검출.png", 4.0,
        "그림 B08 1 기본 항목 3의 실제 웹캠 원본 YOLOv5 검출 화면", [
        "사진은 640 x 480 실시간 카메라 입력에서 원본 검출기가 표시한 프레임이다. 사람을 둘러싼 박스와 person 0.71 라벨을 확인할 수 있다. 0.71은 선택 프레임의 검출 신뢰 점수이며 정량 정확도나 동일인 확인 점수로 해석하지 않는다. 강의의 실제 카메라 입력에서 객체 인식 화면을 확인한 증빙이다.",
        "카메라 입력을 MJPEG로 지정해 화면 형식에 맞췄고 보조 스크립트로 원본 검출기가 표시한 프레임을 저장했다. 원본 detect.py 파일은 공식 해시와 일치한다. WSL Ubuntu 24.04.2 LTS, Python 3.12.3과 PyTorch 2.6.0 CPU에서 실행했고 선택 프레임은 101번, 실제 사람 점수는 0.708044다. 검출값 파일 124개를 저장하고 정상 종료했다."])

    section(doc, "B08 웹캠 입력과 원본 실행의 검증 기록")
    proof("B08 2", ["3"], enlarged + "webcam-record.png", 6.0,
        "그림 B08 2 실제 카메라와 원본 검출기 실행의 저장 기록", [
        "웹캠_검증.json을 VS Code로 연 보조 증빙이다. camera와 device는 실제 카메라 및 /dev/video0, source는 0이다. dimensions는 640과 480이며 launcher에 --baseline과 --source 0이 기록돼 있다. baseline_sha256과 weights_sha256은 원본 코드와 공식 가중치를 대조한 값이다.",
        "selected_frame_index와 person_confidence는 앞 사진의 선택 프레임과 검출값에 대응하며 exit_code 0은 정상 종료를 뜻한다. 사진과 실행 기록으로 실제 카메라 입력의 원본 검출기 동작을 확인했다. 11월 10일 노트북 실행 결과의 원본 파일을 열어 캡처한 화면이다."], crop_bottom=.16)
    text(doc, "당시 실제 실행 명령\n" + record("evidence/notebook-20261110/02_웹캠_증빙/웹캠_검증.json")["actual_helper_command"], 9)
    text(doc, "보조 스크립트가 호출한 원본 실행기\npython tools/run_edge.py --baseline --source 0 --device cpu --view-img --nosave --save-txt --save-conf", 9)
    text(doc, "명령의 .local/laptop은 당시 실행 위치다. 보조 스크립트 원본은 evidence/notebook-20261110/02_웹캠_증빙/webcam_mjpeg_capture.py에 보관했다.", 9)

    section(doc, "B09 PythonAnywhere API 응답")
    proof("B09 1", ["8"], browser + "cloud-api-root.png", 6.0,
        "그림 B09 1 기본 항목 8의 실제 PythonAnywhere API 응답", [
        "주소창은 https://daejinha.pythonanywhere.com/api_root/이고 응답에 GET /api_root/, HTTP 200 OK와 운영 도메인의 Post 링크가 보인다. 요구된 PythonAnywhere 서버의 Django API가 실제 운영 주소에서 정상 응답한 결과다. 11월 10일 Android Chrome에서 이 화면을 다시 확인했다.",
        "이 사진은 운영 서버의 API 루트 접근과 라우팅을 입증한다. 등록된 사진의 실제 저장 및 표시는 뒤의 운영 목록과 상세 사진으로 확인한다. 모델 추론은 Edge PC에서 하고 무료 PythonAnywhere는 API 수신, 저장과 조회를 담당하도록 구성했다."])

    section(doc, "B09 운영 사진의 Android 동기화")
    proof("B09 2", ["7"], "evidence/ui-audit/cloud/yolo-native-detail.png", 2.3,
        "그림 B09 2 기본 항목 7의 운영 등록 사진 Android 확인", [
        "11월 8일 실제 PythonAnywhere 서버를 조회한 Android 상세 화면이다. 서버 주소는 https://daejinha.pythonanywhere.com이며 대상은 YOLO 게시글 8번이다. 화면의 제목, 검출 박스 이미지와 New objects 본문 및 시각이 운영에 등록한 결과와 대응한다.",
        "운영 검사에서 게시글 8번의 JPEG 해시를 API 다운로드와 앱에서 대조했다. 기존 게시글 세 건과 사진은 보존하고 새 검출 게시글을 등록한 결과다. 이 사진은 당시의 운영 앱 검사 화면이고 현재 메뉴 화면은 B16에 제시한다. 로컬 앱의 게시글 2번과는 별도 서버 및 별도 전송 실행의 자료다."])
    text(doc, "운영 전송 기록  evidence/cloud/verification.json\n운영 Android 검사  evidence/ui-audit/cloud/verification.json\n운영 JPEG의 SHA256  " + record("evidence/cloud/verification.json")["new_post"]["image_sha256"], 9)

    section(doc, "B09 PythonAnywhere 등록 사진 목록")
    proof("B09 3", ["9"], browser + "cloud-list.png", 6.0,
        "그림 B09 3 기본 항목 9의 운영 서버 등록 목록과 사진", [
        "주소창의 daejinha.pythonanywhere.com/photos/에서 기본 Post 자료의 목록을 열었다. 첫 카드의 사진 번호는 8이고 제목은 YOLO: person, bus다. 작은 이미지에도 사람과 버스 검출 박스가 표시돼 Edge 전송 결과가 운영 웹 목록에 포함됐음을 확인할 수 있다. 브라우저 재조회와 캡처는 11월 10일에 수행했다.",
        "다른 세 카드는 전환 전부터 보존한 기존 사진이고 이번 기본 전송의 대상은 첫 번째 버스 카드다. 이 기본 Post 자료 네 건은 추가 기능의 관측 사진 500장과 다른 저장 단위다. 첫 카드를 열면 다음 그림의 /post/8/ 상세로 이동해 실제 이미지와 본문을 확인할 수 있다."])

    section(doc, "B09 PythonAnywhere 검출 사진 상세")
    proof("B09 4", ["9"], browser + "cloud-detail.png", 6.0,
        "그림 B09 4 기본 항목 9의 운영 게시글 8번 실제 이미지와 본문", [
        "주소창은 daejinha.pythonanywhere.com/post/8/이다. 목록의 사진 8번을 선택한 상세 화면이며 YOLO: person, bus 제목, 검출 박스가 그려진 실제 JPEG와 New objects 본문 및 검출 시각이 함께 보인다. API에 사진 경로만 있는 상태를 넘어 운영 서버의 저장 파일과 게시글 내용을 브라우저에서 열었다는 증빙이다.",
        "이 게시글은 11월 8일 Edge에서 운영 서버로 전송했고 11월 10일 브라우저에서 다시 확인했다. 같은 운영 사진을 Android에서 연 결과는 B09 2다. 운영 등록 기록의 id 8과 사진 해시, 웹 목록과 상세 및 앱 표시를 연결해 기본 항목 9의 클라우드 목록 및 이미지 동작을 확인했다."])
    section(doc, "기본 기능 증빙의 실행별 연결")
    text(doc, "기본 기능은 검출 사진의 등록부터 API, 웹과 Android 표시까지 연결해 확인했다. 아래 표는 각 사진이 어느 실행에서 만들어졌는지를 정리한 것이다. 로컬 전송, 별도 영상 시험과 운영 전송을 구분하고 재조회한 화면은 원래 등록 결과에 연결했다. 근거 기록 경로는 evidence 폴더 기준이다.")
    data_table(doc, ["실행 자료", "게시글과 확인 범위", "근거 기록"], [
        ["로컬 네 입력 시험", "11월 5일 등록 1과 2, 11월 10일 웹 및 앱 재조회", "yolo-pipeline/verification.json"],
        ["별도 영상 시험", "30프레임의 최초 등장 및 재등장 등록 두 건", "video-flow/verification.json"],
        ["운영 전송", "11월 8일 게시글 8 등록과 Android 확인", "cloud/verification.json"],
        ["운영 브라우저", "11월 10일 API, 목록 및 게시글 8 상세 확인", "basic-verification-20261110/captures.json"]], [1.05, 2.65, 2.2])
    text(doc, "같은 bus 원본을 사용해도 실행별로 생성한 JPEG의 바이트는 다를 수 있다. 파일 대조는 로컬 전송 사진과 그 서버 및 앱, 운영 전송 사진과 운영 서버 및 앱 사이에서 각각 수행했다. 위 사진들과 실행 기록은 기본 기능의 검출, 등록, 조회 및 모바일 표시를 해당 실행별로 연결한 증빙이다.")
