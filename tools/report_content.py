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
    text(doc, "운영 주소는 https://daejinha.pythonanywhere.com/ 이다. 2026년 11월 9일 출입 영상 분석에서는 관측 사진 500장과 분석 실행 40개를 저장했다. 출입 인물 29명의 등록 사진과 영상별 발견 이력을 조회할 수 있다. 11월 10일에는 본인 웹캠 촬영 3건을 추가해 자동 등록과 얼굴 후보 및 운영자 확인을 검증했다.")
    text(doc, "서버와 Edge 검출기는 WSL Ubuntu에서, Android 빌드와 기기 검사는 Windows에서 수행했다. 운영 검증은 PythonAnywhere의 실제 응답과 화면을 기준으로 구분했다.")
    text(doc, "GitHub 저장소  https://github.com/haddol7/mobile_web_service_02", 9)
    section(doc, "운영 화면 접속과 확인 방법", False)
    text(doc, "운영 주소에서 로그인 없이 관측 기록, 인물 확인과 AI 질문을 이용할 수 있다. 운영자 계정은 daejinha이며 관측 등록, 인물 확인 저장과 자료 수정은 운영자 권한으로 처리한다.")
    text(doc, "로그인  https://daejinha.pythonanywhere.com/accounts/login/?next=/", 9)
    text(doc, "평가자는 별도 계정 없이 관측 사진과 인물 이력 및 질문 화면을 확인할 수 있다. 대화 기록은 방문자별 브라우저 세션 또는 로그인 계정별로 분리한다. AI 답변 생성은 서버 전체 하루 5회이며 한국 시간 자정에 한도가 갱신된다.", 9)
    text(doc, "관측 기록에서 날짜와 인물을 선택하고 사진을 열어 검출 박스를 확인한다. 인물 확인에서는 등록 얼굴과 영상 속 얼굴 및 발견 이력을 비교한다. AI 질문에서는 인물과 기간을 선택한 뒤 질문을 보내 근거 사진이 포함된 답변과 대화 기록을 확인한다.")
    text(doc, "AI 질문의 보내기는 외부 유료 API를 사용한다. 기본 API는 /api_root/에서, YOLO 검출 사진의 기본 목록은 /photos/에서 확인할 수 있다.", 9)

    from report_basic_sections import append_basic_sections
    append_basic_sections(doc, text=text, section=section, figure=figure,
                          data_table=data_table, record=record, server_tests=server_tests)

    section(doc, "B10 운영 관측 화면과 추가 기능 구성")
    text(doc, "추가 기능의 처리 위치를 Edge Client의 인물 추적 및 관측 전송과 Server의 인물 이력 및 근거 기록 질의로 나눴다. 10-1은 몸 추적, 얼굴 후보 비교와 전송을, 10-2는 저장된 인물 이력 조회, 확인 상태 관리와 RAG 답변을 평가 대상으로 제시한다.")
    text(doc, "Android에는 기본 검출 사진 조회 외에도 인물 이력과 채팅을 위한 화면 및 API 통신을 구현했다. 이 화면은 10-2의 서버 결과와 근거 사진을 확인하는 접속 경로이며, 얼굴 특징 비교나 임베딩 검색 및 답변 생성을 Android에서 별도로 수행하지 않는다. 서버의 처리 근거는 B13부터 B15, Android의 표시와 통신 구현은 B16에서 구분해 설명한다.", 9)
    pair(doc, ["evidence/private/detection-boxes/production-list.jpg", "evidence/private/cctv-walking/people/production-people.jpg"],
         ["그림 B10 1 운영 관측 기록 500장과 분석 실행 40개", "그림 B10 2 등록된 출입 인물의 얼굴과 발견 이력"], (2.1, 2.1))

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
    text(doc, "11월 9일의 색인은 분석 실행 40개의 문서다. 최초 31개 문서와 고정 질문 3개, 추가 영상 문서 4개, 재분석 문서 5개를 세 차례 배치로 구성했다. 11월 10일에는 본인 촬영 문서 3개를 추가해 43개가 됐다. 기존 벡터는 재사용하며 본인 기록의 색인 및 실제 답변은 B27과 B28에 제시했다.")
    protocol = record("docs/testing/embedding-protocol.json")
    cloud = record("evidence/history/chokepoint-people-embedding-cloud.json")
    questions = {row["id"]: row["question"] for row in protocol["queries"]}
    rows = [[questions[row["id"]], " / ".join(row["sources"][:2]), "확인"] for row in cloud["checks"]]
    data_table(doc, ["고정 질문", "반환 근거 중 대표 출처", "결과"], rows, [2.1, 3.2, .6])
    text(doc, "질문 캐시를 재사용한 운영 재검증에서 고정 예제 3개 모두 관련 출처를 반환했다. 이 결과는 고정 예제 검증이며 일반 검색 정확도 평가와 구분한다. 인물 및 날짜 조건은 의미 유사도보다 우선 적용된다.")
    data_table(doc, ["색인 배치", "신규 입력", "사용 토큰"], [["최초 색인", "문서 31개와 질문 3개", "4,814"], ["출입 영상 추가", "문서 4개", "586"], ["등록 후 재분석", "문서 5개", "1,681"]], [1.45, 3.0, 1.45])
    text(doc, "LLM은 조회한 집계와 근거 기록으로 설명을 작성한다. 통과 건수와 실제 사람 수, 분석일과 원본 촬영일을 구분한다. 원본 촬영일이 없는 자료는 날짜 미상으로 저장한다.")

    section(doc, "B15 실제 AI 답변과 대화 기록")
    text(doc, "운영 서버에서 실제 LLM이 두 영상의 근거 사진을 붙여 답변하는 것을 확인했다. 대화 기록은 계정 또는 방문자별로 저장하며 재접속 후 복원된다. 후속 질문은 앞서 선택된 근거를 이어받고 요청을 재전송해도 같은 대화가 중복 저장되지 않는다.")
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
    text(doc, "Android의 MainActivity와 ChatWorkspace는 인물 및 날짜 선택, 대화 전송과 저장된 응답 및 근거 사진 표시를 담당하고 PhotoRepository가 서버 API를 호출한다. 인물 이력의 집계, 확인 저장, 임베딩 검색과 LLM 답변은 Django에서 처리한다. 기본 Post 사진 조회는 B07과 B24 및 B25에서, 추가 이력 화면은 이 절에서 구분해 제시한다.", 9)
    text(doc, "로그인 없는 공개 조회와 AI 질문은 운영 웹 주소에서 제공한다. Android의 인물 이력과 채팅 메뉴는 운영자 로그인 후 사용하며 웹의 공개 접속 범위와 구분한다.", 9)

    section(doc, "B17 운영 사진의 검출 박스")
    text(doc, "사람 몸은 파란색과 추적 번호, 얼굴 후보는 주황색과 인물 이름 및 유사도, 확인된 얼굴은 초록색으로 표시한다. 저장된 원본 좌표를 게시 사진 크기에 맞춰 변환하며 얼굴과 이름표가 겹치는 면적이 작은 위치를 선택한다.")
    figure(doc, "evidence/private/detection-boxes/production-annotated.jpg", 6.0, "그림 B17 실제 PythonAnywhere 관측 사진의 몸과 얼굴 후보 표시")
    text(doc, "표시는 별도 이미지 응답으로 만들며 저장 원본은 유지한다. 등록 사진과 얼굴 비교용 잘라보기는 선명한 상태로 제공한다. 관측 사진과 검출 박스는 로그인 없이 열람할 수 있다.")
    text(doc, "WSL 검사에서는 사진 축소 좌표, 경계 밖 좌표, 확인 및 미확인 색상, 원본 보존과 공개 조회를 확인했다. 인물 확인 저장과 자료 변경은 운영자 인증을 적용하며 다른 방문자의 대화 기록은 열람할 수 없다.")

    section(doc, "B18 실행 환경과 검증 근거")
    data_table(doc, ["항목", "결과", "evidence 하위 기록"], [
        ["WSL 서버", f"Django {server_tests}개, HTTP 15개 통과", "content/server/verification.json"],
        ["WSL Edge", "추적과 얼굴 및 전송 30개 통과", "history/report-edge-tests.txt"],
        ["웹", "단위 검사 76개 통과", "mobile-web/unit-verification.json"],
        ["Android", "JVM 40개, Lint 오류 0개", "content/android/verification.json"],
        ["출입 영상 등록", "11월 9일 29명, 사진 500장", "history/chokepoint-people-cloud.json"],
        ["출입 영상 색인", "11월 9일 문서 40개, 예제 3개", "history/chokepoint-people-embedding-cloud.json"],
        ["운영 대화 복원", "별도 접속에서 2개 질의 복원", "ui-audit/chat-cloud.json"],
        ["공개 조회와 운영 권한", "공개 조회, 방문자 대화 분리와 하루 5회", "security/deployment.json"]], [1.05, 2.3, 2.55])
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

    section(doc, "B19 본인 웹캠의 인물 확인 결과")
    figure(doc, "evidence/screenshots/self-confirmation-20261110/user-confirmed-profile.png", 2.9,
           "그림 B19 개선 전 화면의 얼굴 대조와 확인 상태")
    text(doc, "웹캠을 연결해 YOLO로 실시간 사람 검출을 확인했다. 등록 얼굴과 새로 촬영한 얼굴을 비교한 화면이다. 후드 착용과 재진입 장면 모두 하대진 후보로 연결됐고 표시 유사도는 각각 0.87과 0.88이다.")
    text(doc, "이 화면은 운영자 확인 1개와 후보 3개를 구분한 개선 전 캡처다. 같은 인물로 확인을 저장하면 해당 추적 번호의 사진에 확인 상태가 반영된다. 상단의 공개 영상 시연 표시는 B30에서 실시간 카메라로 바로잡았으며 최신 확인 상태도 B30에 제시했다. 촬영 자료와 후보 비교 결과는 같은 실제 웹캠 기록이다.")
    text(doc, "추가 기능 10-2의 인물 확인 저장과 얼굴 대조 증빙이다.\n확인 위치  https://daejinha.pythonanywhere.com/people/self-daejinha/", 9)

    section(doc, "B20 본인 촬영별 발견 이력")
    figure(doc, "evidence/screenshots/self-confirmation-20261110/user-session-history.png", 4.6,
           "그림 B20 개선 전 화면의 세 촬영 실행과 발견 이력")
    text(doc, "2026년 11월 10일 분석일 아래에 화면 이탈과 재진입, 모자 착용, 평소 모습의 세 촬영 실행이 구분돼 있다. 각 항목에서 장면 확인을 누르면 해당 실행에 연결된 사진과 추적 기록을 조회할 수 있다.")
    data_table(doc, ["촬영 실행", "조회 사진", "화면의 상태"], [
        ["본인 웹캠 화면 이탈과 재진입 확인", "3장", "얼굴 후보"],
        ["본인 모자 착용 웹캠 인식 확인", "2장", "얼굴 후보"],
        ["본인 평소 모습 웹캠 인식 확인", "2장", "확인됨"]], [3.1, .8, 2.0])
    text(doc, "평소 모습만 먼저 확인한 시점의 화면이며 나머지 두 실행도 이후 운영자가 확인했다. 값이 없는 영상 초 항목은 B30의 최종 실시간 카메라 화면에서 숨겼다. 사진 수는 선택한 인물의 조회 기록 수이며 세 실행은 같은 사람의 별도 촬영으로 실제 방문 횟수와 구분한다.")
    text(doc, "추가 기능 10-2의 촬영별 이력 조회와 확인 상태 반영을 보여주는 보완 증빙이다. 원본 증빙은 evidence/screenshots/self-confirmation-20261110에 보관했다.", 9)
    from report_self_sections import append_self_sections
    append_self_sections(doc, section=section, text=text, figure=figure, pair=pair, data_table=data_table, server_tests=server_tests)
    from report_rag_sections import append_rag_sections
    append_rag_sections(doc, section=section, text=text, figure=figure, data_table=data_table, record=record)
    return doc
