"""Evidence-backed report prose and embedded figures for Common Assessment 02."""
import json
import re
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
FIGURES = []


def record(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def text(doc, value, size=10.5, bold=False):
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_after = Pt(5)
    paragraph.paragraph_format.line_spacing = 1.05
    run = paragraph.add_run(value)
    run.font.name = "바탕"
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "바탕")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    return paragraph


def section(doc, title, new_page=True):
    if new_page:
        doc.add_page_break()
    paragraph = text(doc, title, 13, True)
    paragraph.paragraph_format.keep_with_next = True


def figure(doc, path, width, caption=None, crop_bottom=0):
    full = ROOT / path
    assert full.is_file(), path
    FIGURES.append(path)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(4)
    picture = paragraph.add_run().add_picture(str(full), width=Inches(width))
    if crop_bottom:
        # Crop only the blank lower viewport in Word; preserve the original screenshot bytes.
        assert 0 < crop_bottom < 1
        crop = OxmlElement("a:srcRect")
        crop.set("b", str(round(crop_bottom * 100000)))
        fill = picture._inline.graphic.graphicData.pic.blipFill
        fill.insert(1, crop)
        picture.height = round(picture.height * (1 - crop_bottom))
    if caption:
        paragraph.paragraph_format.keep_with_next = True
        text(doc, caption, 9)


def pair(doc, paths, captions, widths=(2.6, 2.6)):
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    for cell, path, caption, width in zip(table.rows[0].cells, paths, captions, widths):
        cell.width = Inches(3.0)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        FIGURES.append(path)
        cell.paragraphs[0].add_run().add_picture(str(ROOT / path), width=Inches(width))
        paragraph = cell.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(3)
        run = paragraph.add_run(caption)
        run.font.name = "바탕"
        run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "바탕")
        run.font.size = Pt(9)
    for row in table.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def data_table(doc, headers, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    table.style = "Table Grid"
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement("w:" + edge)
        for key, value in (("val", "single"), ("sz", "4"), ("color", "999999")):
            border.set(qn("w:" + key), value)
        borders.append(border)
    table._tbl.tblPr.append(borders)
    for row_values in [headers, *rows]:
        cells = table.rows[0].cells if row_values is headers else table.add_row().cells
        for i, (cell, value) in enumerate(zip(cells, row_values)):
            if widths:
                cell.width = Inches(widths[i])
            cell.text = str(value)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(4)
                paragraph.paragraph_format.space_before = Pt(3)
                for run in paragraph.runs:
                    run.font.name = "바탕"
                    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "바탕")
                    run.font.size = Pt(9)
                    run.font.color.rgb = RGBColor(0, 0, 0)
                    run.bold = row_values is headers
            if row_values is headers:
                shade = OxmlElement("w:shd")
                shade.set(qn("w:fill"), "D9D9D9")
                cell._tc.get_or_add_tcPr().append(shade)
    for row in table.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))


def build_appendix():
    FIGURES.clear()
    test_log = (ROOT / "evidence/content/server/tests-coverage.txt").read_text(encoding="utf-8")
    server_tests = int(re.search(r"Ran (\d+) tests", test_log).group(1))
    doc = Document()
    section(doc, "구현 및 검증 결과", False)
    text(doc, "YOLOv5가 객체 출현을 감지하면 Django 서버에 사진을 등록하고 Android와 웹에서 확인하는 감시 시스템을 구현했다. 기존 객체 출현 비교와 Post API를 유지하고 사람 추적 및 얼굴 후보 비교, 인물별 이력과 근거 기록 질문을 추가했다.")
    text(doc, "운영 주소는 https://daejinha.pythonanywhere.com/ 이다. 2026년 11월 9일 기준으로 관측 사진 500장과 분석 실행 40개를 저장했다. 출입 인물 29명의 등록 사진과 영상별 발견 이력을 조회할 수 있다.")
    text(doc, "서버와 Edge 검출기는 WSL Ubuntu에서, Android 빌드와 기기 검사는 Windows에서 수행했다. 운영 검증은 PythonAnywhere의 실제 응답과 화면을 기준으로 구분했다.")
    text(doc, "GitHub 저장소  https://github.com/haddol7/mobile_web_service_02", 9)
    section(doc, "운영 화면 접속과 확인 방법", False)
    text(doc, "운영자 계정은 daejinha다. 아래 로그인 주소에서 사용자 이름과 계정 비밀번호를 입력하면 관측 기록으로 이동한다. 관측 사진과 인물 이력은 운영자 로그인 후 확인한다.")
    text(doc, "로그인  https://daejinha.pythonanywhere.com/accounts/login/?next=/", 9)
    text(doc, "운영 화면을 직접 확인하려면 평가자에게 계정 비밀번호를 비공개로 전달한다. 공개 저장소에는 비밀번호와 API 키를 포함하지 않는다.", 9)
    text(doc, "관측 기록에서 날짜와 인물을 선택하고 사진을 열어 검출 박스를 확인한다. 인물 확인에서는 등록 얼굴과 영상 속 얼굴 및 발견 이력을 비교한다. AI 질문에서는 인물과 기간을 선택한 뒤 질문을 보내 근거 사진이 포함된 답변과 대화 기록을 확인한다.")
    text(doc, "AI 질문의 보내기는 외부 유료 API를 사용한다. 기본 API는 /api_root/에서, YOLO 검출 사진의 기본 목록은 /photos/에서 확인할 수 있다.", 9)

    section(doc, "B01 제출 폴더 구조와 별도 저장소")
    text(doc, "공통평가 01과 분리된 저장소에 PhotoBlogServer, PhotoViewer, YOLOv5 폴더를 구성했다. PhotoBlogServer는 Django 서버, PhotoViewer는 Android 앱, YOLOv5는 Edge 검출기다. 수행 결과 보고서는 저장소 루트에 둔다.")
    figure(doc, "evidence/screenshots/github-folder-structure.jpg", 6.1, "그림 B01 공통평가 02 별도 저장소의 폴더 구성")
    text(doc, "PhotoBlogServer의 모델 및 API와 PhotoViewer의 동기화 기능은 공통평가의 기본 연동 구조를 사용한다. 관측 기록과 등록 얼굴은 운영자 인증 후 조회하며, 소스와 모델 실행 환경을 분리했다.")

    section(doc, "B02 원본 YOLOv5 실행 결과")
    text(doc, "Ultralytics YOLOv5 v7.0의 원본 detect.py를 별도 baseline 폴더에 보관하고 공식 파일의 SHA256을 대조했다. CPU로 bus.jpg를 실행한 결과 사람 4명과 버스 1대를 검출했다. 아래는 원본 검출기의 실제 결과 이미지다.")
    figure(doc, "evidence/yolo-pipeline/original-image/bus.jpg", 3.9, "그림 B02 원본 검출기로 처리한 공식 bus.jpg")
    text(doc, "가중치는 공식 사전 학습 모델을 사용한다. 원본 출처와 파일 해시는 docs/upstream/provenance.json, 실행 결과는 evidence/yolo-pipeline/verification.json에 기록했다.", 9)

    section(doc, "B03 객체 출현 비교 코드")
    text(doc, "ChangeDetection은 프레임별 객체 종류의 존재 여부를 비교한다. 이전에 없던 종류가 나타나면 전송 대상으로 판단하고 같은 장면이 이어지는 동안에는 추가 전송을 억제한다.")
    figure(doc, "evidence/screenshots/changedetection-vscode.png", 6.1, "그림 B03 1 객체 출현 비교를 구현한 changedetection.py")
    text(doc, "첫 검출, 같은 장면, 빈 화면, 재등장 순서의 실제 추론에서 첫 검출과 재등장에 각각 게시글 1개가 등록됐다.")

    section(doc, "B03 검출 사진 저장과 HTTP 등록")
    text(doc, "검출 상자를 표시한 사진을 320 x 240 JPEG로 저장하고 제목과 검출 내용을 multipart 요청으로 전송한다. 서버의 DRF Token 인증을 사용하며 전송에 실패한 사진은 로컬에 보관한다.")
    figure(doc, "evidence/screenshots/changedetection-upload-vscode.png", 6.1, "그림 B03 2 검출 사진 저장과 Post API 등록 코드")

    section(doc, "B03 추론 루프와 전송 연결")
    text(doc, "YOLOv5 detect.py의 추론 루프에서 검출 결과를 ChangeDetection에 전달한다. 객체 종류의 출현 변화가 있는 프레임만 서버 전송으로 연결했다.")
    figure(doc, "evidence/screenshots/detect-hook-vscode.png", 6.1, "그림 B03 3 YOLOv5 추론 루프의 연결 위치")

    section(doc, "B04 로컬 서버 API 확인")
    text(doc, "WSL 서버의 http://127.0.0.1:8020/api_root/ 에서 HTTP 200 응답을 확인했다. Post API는 id, author, title, text, created_date, published_date, image의 기본 7개 필드를 유지한다.")
    figure(doc, "evidence/screenshots/local-api-root.jpg", 6.0, "그림 B04 1 로컬 API 루트의 브라우저 응답")
    figure(doc, "evidence/screenshots/local-api-posts.jpg", 6.0, "그림 B04 2 검출 게시글의 JSON 응답")

    section(doc, "B05 로컬 검출 사진 등록 결과")
    text(doc, "로컬 서버에서 첫 출현과 재등장으로 등록된 검출 사진 2개를 조회했다. 전송 JPEG, 서버에 저장된 JPEG와 HTTP로 조회한 JPEG의 SHA256이 일치했다.")
    figure(doc, "evidence/screenshots/local-list.jpg", 6.1, "그림 B05 로컬 기본 사진 목록에서 검출 결과 확인")
    section(doc, "B06 자동 검증 결과", False)
    data_table(doc, ["구분", "검증 결과", "환경"], [
        ["Django 전체", f"{server_tests}개 통과", "WSL Ubuntu"], ["실제 HTTP 엔진", "전체 중 15개 별도 재실행 통과", "WSL Ubuntu"],
        ["Edge 단위", "30개 통과", "WSL Ubuntu"], ["웹 단위", "76개 통과", "Windows Node"],
        ["Android JVM", "40개 통과", "Windows"], ["Android Lint", "오류 0개, 경고 9개", "Windows"]], [1.3, 3.15, 1.45])

    section(doc, "B07 Android 기본 사진 동기화")
    text(doc, "Android 02 앱에서 WSL 서버에 등록된 검출 사진을 조회했다. 같은 검출 사진의 SHA256을 대조하고 목록과 상세 화면을 캡처했다. 접속 주소는 http://10.0.2.2:8020/ 이다.")
    pair(doc, ["evidence/screenshots/yolo-native-list.png", "evidence/screenshots/yolo-native-detail.png"],
         ["그림 B07 1 기본 사진 목록", "그림 B07 2 검출 사진 상세"], (2.6, 2.6))
    text(doc, "이 화면은 강의 기본 Post API 연동의 검증 화면이며 최신 감시 메뉴 화면은 B16에 정리했다.", 9)

    section(doc, "B07 Android 모바일 웹 확인")
    text(doc, "Android Chrome에서도 같은 검출 게시글의 목록과 상세를 확인했다. 실제 WSL 서버의 이미지 응답과 앱의 이미지 해시 검사 결과를 함께 보관했다.")
    pair(doc, ["evidence/mobile-flow/yolo-mobile-web-list.png", "evidence/mobile-flow/yolo-mobile-web-detail.png"],
         ["그림 B07 3 로컬 모바일 웹 목록", "그림 B07 4 로컬 모바일 웹 상세"], (2.6, 2.6))

    section(doc, "B08 영상 입력과 전송 실패 처리")
    text(doc, "공식 bus.jpg와 빈 프레임을 조합한 30프레임 영상을 초당 5프레임으로 실제 YOLOv5에 입력했다. 전송 대상은 기존 데이터와 분리한 WSL 검증 서버다.")
    data_table(doc, ["입력 순서", "내용", "새 게시글"], [
        ["처음 6프레임", "빈 화면", "0개"], ["다음 12프레임", "사람과 버스가 연속 등장", "첫 프레임의 1개"],
        ["다음 6프레임", "빈 화면", "0개"], ["마지막 6프레임", "사람과 버스가 재등장", "1개"]], [1.35, 3.1, 1.45])
    text(doc, "등록 사진은 총 2개이며 모두 320 x 240 JPEG였다. 잘못된 인증값을 사용한 요청은 거부됐고 기존 게시글 수가 유지됐다. 실패한 전송의 사진은 로컬에 보관돼 재시도할 수 있다.")
    text(doc, "관측 이력 전송에서는 동일 패킷 재전송과 서버 저장 후 응답 유실을 재현했다. 재전송 시 같은 기록이 두 번 생성되지 않았으며 저장 대기 패킷은 전송 완료 후 비워졌다.")
    text(doc, "전용 Python 가상환경에서 pip check, OpenCV 로딩과 PyTorch CPU 연산을 확인했다. WSL 소스와 Windows Android 프로젝트는 같은 작업 폴더를 사용한다.")
    text(doc, "근거 기록  evidence/video-flow/verification.json, evidence/history/verification.json, evidence/environment/wsl-runtime.json", 9)

    section(doc, "B08 원본 검출기의 실시간 웹캠 실행")
    text(doc, "2026년 11월 10일 노트북의 Acer HD User Facing 웹캠을 USB/IP로 WSL2 Ubuntu에 연결했다. /dev/video0에서 실제 프레임이 읽히는 것을 확인한 뒤 수정하지 않은 YOLOv5 v7.0의 detect.py를 카메라 인덱스 0으로 실행했다. 원본 파일과 공식 가중치의 SHA256이 기록된 값과 일치했다.")
    text(doc, "카메라 입력 형식을 MJPEG로 지정해 기본 YUYV 형식의 녹색 깨짐을 해결했다. 보조 스크립트는 입력 형식을 설정하고 원본 검출기가 화면에 표시한 프레임을 저장한다. 640 x 480 실시간 화면에서 사람 검출 상자와 person 0.71 라벨을 확인했다.")
    figure(doc, "evidence/notebook-20261110/02_웹캠_증빙/웹캠_실시간_검출.png", 4.0, "그림 B08 1 실제 노트북 웹캠을 입력으로 실행한 원본 YOLOv5 사람 검출 화면")
    text(doc, "WSL Ubuntu 24.04.2 LTS, Python 3.12.3과 PyTorch 2.6.0 CPU에서 실행했다. 선택한 추론 프레임은 101번이며 사람 점수는 0.708044다. 검출값 파일 124개를 저장하고 정상 종료했다. 녹화 영상의 분석 결과와 구분한 실제 카메라 실행이다.")
    text(doc, "실제 실행 명령은 다음과 같다. 보조 스크립트 보관본은 evidence/notebook-20261110/02_웹캠_증빙/webcam_mjpeg_capture.py다.", 9)
    text(doc, record("evidence/notebook-20261110/02_웹캠_증빙/웹캠_검증.json")["actual_helper_command"], 9)
    text(doc, "보조 스크립트가 호출한 원본 실행기  tools/run_edge.py --baseline --source 0 --device cpu --view-img --nosave --save-txt --save-conf", 9)
    text(doc, "근거 기록  evidence/notebook-20261110/02_웹캠_증빙의 웹캠_검증.json, 선택_프레임_검출값.txt, webcam-retake.log", 9)

    section(doc, "B09 PythonAnywhere API 응답")
    text(doc, "https://daejinha.pythonanywhere.com/api_root/ 에서 기본 API의 HTTP 200을 확인했다. 실제 YOLO 클라이언트가 운영 서버에 등록한 게시글과 사진을 Android 앱에서 다시 조회했다.")
    figure(doc, "evidence/ui-audit/cloud/api-root-browser.png", 6.0,
           "그림 B09 1 운영 API 응답 확대 화면 하단의 빈 영역만 생략", crop_bottom=.69)
    text(doc, "GET /api_root/의 HTTP 200 OK와 JSON의 Post 링크에 전체 운영 도메인이 표시된다. 그림은 11월 8일 운영 검증 때 저장한 원본 캡처의 응답 부분을 확대해 배치했다.", 9)

    section(doc, "B09 PythonAnywhere Android 동기화")
    figure(doc, "evidence/ui-audit/cloud/yolo-native-detail.png", 2.5,
           "그림 B09 2 운영 검출 사진의 Android 상세")
    text(doc, "운영 등록 과정에서 기존 게시글 3개와 사진 바이트를 보존했다. 새 YOLO 검출 게시글 id 8의 사진 해시를 운영 API와 Android에서 대조했다. 기본 연동 증빙은 11월 8일의 실제 운영 검사다.", 9)

    section(doc, "B09 PythonAnywhere 브라우저 목록과 검출 사진")
    text(doc, "11월 9일 운영 서버의 기본 사진 보관함과 검출 게시글을 브라우저에서 다시 열었다. YOLO가 등록한 person, bus 게시글 id 8이 목록에 표시되며 상세 화면에서 검출 박스가 그려진 사진과 검출 내용을 확인할 수 있다.")
    figure(doc, "evidence/private/report-fixes-20261109/production-post-list.jpg", 5.65, "그림 B09 3 운영 서버 /photos/의 기본 사진 목록")
    figure(doc, "evidence/private/report-fixes-20261109/production-post-detail.jpg", 5.65, "그림 B09 4 운영 서버 /post/8/의 YOLO 검출 사진 상세")

    section(doc, "B10 운영 관측 화면과 추가 기능 구성")
    text(doc, "추가 기능은 두 항목으로 구성했다. Edge Client는 인물 추적과 관측 기록을 전송하고, Server는 인물 이력을 관리하고 근거 기록 질문에 답한다. Android와 웹은 같은 서버 API로 이 결과를 조회한다.")
    pair(doc, ["evidence/private/detection-boxes/production-list.jpg", "evidence/private/cctv-walking/people/production-people.jpg"],
         ["그림 B10 1 운영 관측 기록 500장과 분석 실행 40개", "그림 B10 2 등록된 출입 인물의 얼굴과 발견 이력"], (2.35, 2.35))

    section(doc, "B11 인물 등록과 영상별 발견 이력")
    text(doc, "ChokePoint 공식 등록 사진 58장으로 29명을 등록했다. 인물마다 중립 표정과 미소 사진 두 장을 사용하고 실제 이름 대신 데이터셋 ID에 맞춘 별칭을 부여했다. 기존 등록 인물을 포함한 비교 갤러리는 34명이다.")
    pair(doc, ["evidence/private/cctv-walking/people/production-person.jpg", "evidence/private/cctv-walking/people/production-comparison.jpg"],
         ["그림 B11 1 출입 인물 05의 원본 영상 5개 이력", "그림 B11 2 등록 얼굴과 혼잡 영상의 후보 얼굴 비교"], (2.3, 2.3))
    text(doc, "등록 사진과 조회 영상은 분리했다. 후보와 확인 상태를 구분하며 혼잡 영상의 후보는 운영자가 사진을 대조해 확인한다.", 9)

    section(doc, "B12 출입 영상 재분석과 정답 대조")
    text(doc, "기존 출입 영상 다섯 개를 재분석해 총 4,343프레임을 처리했다. 몸 추적은 재생 영상 기준 약 15fps, 얼굴 비교는 약 3fps다. 등록 얼굴과 실제 검출 얼굴을 대조한 뒤 일반 구간의 공식 눈 좌표로 정답을 대응시켰다.")
    rows = []
    for case in record("evidence/history/chokepoint-people-summary.json")["model_evaluation"]:
        rows.append([case["camera"], case["frames_analyzed"], case["scored_face_matches"] if case["groundtruth_available"] else "정답 없음",
                     case["correct_candidates"] if case["groundtruth_available"] else "-",
                     case["unresolved_labeled_faces"] if case["groundtruth_available"] else "-",
                     case["wrong_candidates"] if case["groundtruth_available"] else "-"])
    data_table(doc, ["원본 구간", "처리 프레임", "정답 대응", "일치", "보류", "오연결"], rows, [1.55, .9, 1.1, .75, .75, .75])
    text(doc, "일반 구간의 정답 대응 359건 중 후보 일치 358건, 보류 1건, 오연결 0건이었다. 검출된 얼굴 중 양쪽 눈 좌표를 유일하게 대응시킨 표본의 결과이며 전체 얼굴 검출률과 구분한다. 일반 입장 및 퇴장 영상에서는 각각 25명의 동일 인물 연결을 확인했다.")
    text(doc, "같은 몸 추적에 반복 정답과 모델 후보가 일치한 61개를 시연 정답 확인으로 저장했다. 혼잡 S5 구간은 공식 정답이 없어 후보 상태로 표시한다. 29명 중 28명은 후보를 포함해 두 개 이상의 원본 영상에 연결됐다.")
    section(doc, "B12 공식 등록 사진 검토")
    text(doc, "공식 Still.tar.xz의 Neutral과 Smile 사진 58장 모두 등록 가능한 얼굴이 검출됐다. ID별 두 사진을 나란히 대조해 얼굴 자르기와 번호를 확인했다. 공식 ID 0008은 없어 0001부터 0030 사이의 29개 번호를 그대로 사용했다.")
    figure(doc, "evidence/private/cctv-walking/people/enrollment-review.jpg", 5.6, "그림 B12 공식 ID별 등록 사진 29쌍 검토")
    text(doc, "원본 등록 사진 묶음의 MD5는 2efcd4010d19e811cce144a614ea82a2이며 공식 배포값과 일치했다. 등록 사진과 조회 영상은 다른 자료로 구성했다. 원본 출처와 이용 조건은 파생 사진과 함께 보관한다.", 9)

    section(doc, "B13 얼굴 특징 추출과 후보 결정 방법")
    text(doc, "InsightFace Buffalo L의 사전 학습 모델을 사용한다. 등록 사진에서 짧은 변이 20픽셀 이상인 얼굴을 고르고, 여러 얼굴이 있으면 지정 영역을 사용한다. 영역 지정이 없을 때는 가장 큰 얼굴의 면적이 두 번째 얼굴의 4배 이상인 경우에만 자동으로 선택한다.")
    text(doc, "눈과 코 등 다섯 기준점으로 얼굴을 112 x 112 크기에 정렬한다. 원본 얼굴과 좌우를 뒤집은 얼굴의 특징 벡터를 더한 뒤 길이를 1로 정규화한다. 한 인물의 여러 등록 사진 중 코사인 유사도가 가장 큰 값을 그 인물의 점수로 사용한다.")
    data_table(doc, ["비교 설정", "기존", "개선 후"], [
        ["특징 추출", "원본 한 번", "원본과 좌우 반전 결합"],
        ["최고 유사도 기준", "0.55 이상", "0.29 이상"],
        ["다른 인물 2위와의 점수 차이", "0.08 이상", "0.10 이상"]], [2.6, 1.65, 1.65])
    text(doc, "최고 점수와 다른 인물 2위와의 점수 차이가 두 기준을 모두 만족해야 후보를 연결한다. 기준에 못 미치면 미확인으로 남기며 자동 확정은 하지 않는다. 몸 추적 번호와 얼굴 후보는 구분해 저장한다.")
    text(doc, "앞의 ChokePoint 출입 시연과 별개로 VoxCeleb2 공개 미러에서 얼굴 비교용 자료를 구성했다. 설정은 개발 인물 18명으로 정한 뒤 고정하고, 이들과 겹치지 않는 인물 24명으로 최종 비교했다. 등록과 질의는 원본 영상 ID 단위로 분리했다. 다음 결과는 등록 얼굴 선택, 특징 결합과 임계값을 함께 바꾼 실험이며 개별 변경의 기여도를 분리한 결과는 아니다.")
    text(doc, "구현 근거  YOLOv5/face_features.py, YOLOv5/person_tracking.py, YOLOv5/face_policy.json", 9)

    section(doc, "B13 얼굴 후보 비교 개선 검증")
    text(doc, "VoxCeleb2의 별도 평가 인물 24명 중 등록 인물 12명과 미등록 인물 12명을 비교했다. 질의 영상 48개에서 원본 576프레임을 추출했다. 등록 사진은 등록 인물별 첫 원본 영상에서 선택하고 질의는 다른 원본 영상 두 개씩을 사용했다. 원본, 밝기 35%와 64픽셀 저해상도 조건은 같은 프레임에서 파생한 조건이다.")
    text(doc, "자료 출처와 구성  docs/testing/face-video-sources.md, docs/testing/person-libraries.md\n평가 결과  evidence/person-libraries/face-improvement-evaluation.json", 9)
    face = record("evidence/person-libraries/face-improvement-evaluation.json")
    rows = []
    for key, label in [("original", "원본"), ("low_light_35_percent", "밝기 35%"), ("low_resolution_64px", "64픽셀")]:
        case = face["comparisons"][key]["improved"]
        rows.append([label, f'{case["correct_candidates"]}/288', f'{case["known_recall"]*100:.1f}%', case["known_unresolved"], f'{case["unknown_false_candidates"]}/288'])
    data_table(doc, ["조건", "올바른 연결", "연결률", "등록 인물 보류", "미등록 오연결"], rows, [1.05, 1.2, .9, 1.4, 1.35])
    text(doc, "원본 조건의 올바른 연결은 기존 104/288에서 개선 후 272/288로 증가했다. 낮은 점수 또는 후보 간 차이가 작은 얼굴은 미확인으로 남긴다. 이 표본에서 미등록 오연결은 0건이며 모든 환경의 오류율을 보장하는 값은 아니다.")
    figure(doc, "evidence/person-libraries/face-improvement-results.png", 6.0, "그림 B13 고정된 비교 조건의 얼굴 후보 성능 결과")

    section(doc, "B14 근거 기록 검색과 임베딩")
    text(doc, "인물과 날짜 조건으로 DB 기록을 먼저 제한한 뒤 영상 설명과 인물 및 날짜 메타데이터를 임베딩으로 비교한다. text-embedding-3-small의 512차원 벡터와 제목 일치를 함께 사용해 관련 영상 최대 5개를 선택한다. 검색된 기록의 집계와 근거 사진을 답변에 연결한다.")
    text(doc, "현재 색인은 분석 실행 40개의 문서다. 최초 31개 문서와 고정 질문 3개, 추가 영상 문서 4개, 재분석 문서 5개를 세 차례 배치로 구성했다. 기존 벡터는 재사용하며 사진과 얼굴 특징은 텍스트 임베딩 입력과 구분해 보관한다.")
    protocol = record("docs/testing/embedding-protocol.json")
    cloud = record("evidence/history/chokepoint-people-embedding-cloud.json")
    questions = {row["id"]: row["question"] for row in protocol["queries"]}
    rows = [[questions[row["id"]], " / ".join(row["sources"][:2]), "확인"] for row in cloud["checks"]]
    data_table(doc, ["고정 질문", "반환 근거 중 대표 출처", "결과"], rows, [2.1, 3.2, .6])
    text(doc, "질문 캐시를 재사용한 운영 재검증에서 고정 예제 3개 모두 관련 출처를 반환했다. 이 결과는 고정 예제 검증이며 일반 검색 정확도 평가와 구분한다. 인물 및 날짜 조건은 의미 유사도보다 우선 적용된다.")
    data_table(doc, ["색인 배치", "신규 입력", "사용 토큰"], [["최초 색인", "문서 31개와 질문 3개", "4,814"], ["출입 영상 추가", "문서 4개", "586"], ["등록 후 재분석", "문서 5개", "1,681"]], [1.45, 3.0, 1.45])
    text(doc, "LLM은 조회한 집계와 근거 기록으로 설명을 작성한다. 통과 건수와 실제 사람 수, 분석일과 원본 촬영일을 구분한다. 원본 촬영일이 없는 자료는 날짜 미상으로 저장한다.")

    section(doc, "B15 실제 AI 답변과 대화 기록")
    text(doc, "운영 서버에서 실제 LLM이 두 영상의 근거 사진을 붙여 답변하는 것을 확인했다. 대화 기록은 운영자별로 저장하며 재접속 후 복원된다. 후속 질문은 앞서 선택된 근거를 이어받고 요청을 재전송해도 같은 대화가 중복 저장되지 않는다.")
    pair(doc, ["evidence/private/ui-audit/person-answer-production.png", "evidence/private/ui-audit/chat-production.png"],
         ["그림 B15 1 실제 운영 LLM 답변 검증 화면", "그림 B15 2 운영 대화 저장과 후속 질문 화면"], (2.3, 2.3))
    text(doc, "왼쪽은 실제 생성 검증 시점의 화면이며 오른쪽은 개편된 채팅 화면이다. 대화 저장 검증에는 캐시와 DB 조회를 사용했다. 실제 생성과 대화 복원 검증은 각각의 실행 기록으로 구분했다.", 9)
    text(doc, "공개 인물 영상은 DVIDS와 HDTF 자료를 사용했다. 영상별 원본 URL과 확인된 날짜는 docs/testing/PUBLIC_FIGURE_EXPANSION.md와 docs/testing/face-video-sources.md에 정리했다. 이 자료는 촬영 영상의 동일인 후보 비교용이며 실제 방문 기록을 뜻하지 않는다.", 9)

    section(doc, "B16 Android와 모바일 웹의 감시 메뉴")
    text(doc, "주 메뉴는 관측 기록, 인물 확인, AI 질문이다. 관측 기록에서 전체 집계와 날짜별 사진을 함께 보고 인물 화면에서 등록 얼굴 및 발견 장면을 비교한다. 작은 화면에서도 사진 목록을 두 열로 배치하고 상세 창의 확인 버튼이 보이도록 구성했다.")
    pair(doc, ["evidence/private/ui-audit/20261108T214736631868/captures/ui-audit/native-primary-records.png",
               "evidence/private/ui-audit/20261108T221731926915/captures/ui-audit/web-history-detail.png"],
         ["그림 B16 1 검증 서버의 Android 네이티브 관측 목록", "그림 B16 2 작은 Android WebView의 검출 박스 상세"], (2.5, 2.3))
    text(doc, "네이티브 및 WebView는 같은 Django API를 사용한다. 두 화면 크기의 메뉴와 얼굴 확인 흐름을 검사했고 박스 표시 추가 후 작은 화면의 WebView 흐름을 다시 확인했다.", 9)

    section(doc, "B17 운영 사진의 검출 박스")
    text(doc, "사람 몸은 파란색과 추적 번호, 얼굴 후보는 주황색과 인물 이름 및 유사도, 확인된 얼굴은 초록색으로 표시한다. 저장된 원본 좌표를 게시 사진 크기에 맞춰 변환하며 얼굴과 이름표가 겹치는 면적이 작은 위치를 선택한다.")
    figure(doc, "evidence/private/detection-boxes/production-annotated.jpg", 6.0, "그림 B17 실제 PythonAnywhere 비공개 관측 사진의 몸과 얼굴 후보 표시")
    text(doc, "표시는 별도 이미지 응답으로 만들며 저장 원본은 유지한다. 등록 사진과 얼굴 비교용 잘라보기는 선명한 상태로 제공한다. 박스가 포함된 사진도 운영자 인증 후 열람한다.")
    text(doc, "WSL 검사에서는 사진 축소 좌표, 경계 밖 좌표, 확인 및 미확인 색상, 원본 보존과 접근 권한을 확인했다. 운영 응답에서도 박스 이미지와 원본의 해시가 다르고 비인증 요청이 차단되는 것을 확인했다.")

    section(doc, "B18 실행 환경과 검증 근거")
    data_table(doc, ["항목", "결과", "evidence 하위 기록"], [
        ["WSL 서버", f"Django {server_tests}개, HTTP 15개 통과", "content/server/verification.json"],
        ["WSL Edge", "추적과 얼굴 및 전송 30개 통과", "history/report-edge-tests.txt"],
        ["웹", "단위 검사 76개 통과", "mobile-web/unit-verification.json"],
        ["Android", "JVM 40개, Lint 오류 0개", "content/android/verification.json"],
        ["운영 인물 등록", "29명 등록, 관측 사진 500장", "history/chokepoint-people-cloud.json"],
        ["운영 검색 색인", "문서 40개, 고정 예제 3개 확인", "history/chokepoint-people-embedding-cloud.json"],
        ["운영 대화 복원", "별도 접속에서 2개 질의 복원", "ui-audit/chat-cloud.json"],
        ["운영 박스 표시", "원본 보존과 비인증 접근 차단", "ui-audit/detection-boxes-deployment.json"]], [1.05, 2.3, 2.55])
    text(doc, f"HTTP 엔진의 15개 사례는 Django 전체 {server_tests}개에 포함된 사례를 별도 HTTP 엔진으로 재실행한 결과다. 테스트 수를 합산해 전체 사례 수로 계산하지 않는다.")
    text(doc, "노트북 WSL에서도 환경 파일 615개와 등록 사진 34명 73장을 검사했다. 동봉 영상 240프레임, Django 250개 및 이전 도구 단위 테스트 9개를 확인했고 로컬 API와 사진 목록은 HTTP 200을 반환했다.", 9)
    text(doc, "검사 명령  서버 python PhotoBlogServer/tools/verify_security.py\nEdge는 YOLOv5에서 python -m unittest discover -s tests -v\n웹 node tools/verify-mobile-web.mjs, Android PhotoViewer/tools/verify-android.ps1", 9)
    text(doc, "운영 보호의 로컬 검증과 적용 상태는 docs/security-controls.md, evidence/security/deployment.json에 정리했다.", 9)
    text(doc, "무료 PythonAnywhere는 Django API와 DB, 관측 이력 및 텍스트 검색을 제공한다. YOLOv5와 얼굴 비교는 Edge CPU에서 실행하고 사진 및 메타데이터를 서버로 전송한다. LLM 설명 생성은 별도 외부 API를 사용한다.")
    text(doc, "주요 출처", 11, True)
    for line in ["YOLOv5  https://github.com/ultralytics/yolov5/tree/v7.0",
                 "InsightFace  https://github.com/deepinsight/insightface",
                 "ChokePoint  https://zenodo.org/records/815657",
                 "VoxCeleb2 공개 미러  https://huggingface.co/datasets/mortal9826/VoxCeleb2-test-data",
                 "HDTF 원출처와 원본 영상 목록  https://github.com/MRzzm/HDTF",
                 "DVIDS 영상별 원본 URL  docs/testing/PUBLIC_FIGURE_EXPANSION.md",
                 "모델과 자료의 이용 조건  docs/testing/licenses 및 docs/upstream"]:
        paragraph = text(doc, line, 9)
        paragraph.paragraph_format.space_after = Pt(2)
    return doc
