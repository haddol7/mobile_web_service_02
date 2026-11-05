"""Fill the supplied assessment template and embed only actual, verified evidence."""
from copy import deepcopy
from io import BytesIO
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT/'docs/reference/모바일웹서비스 프로젝트_공통평가 02_수행 결과 보고서.docx'
OUT = ROOT/'모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
NS={'w':W,'r':R}
q=lambda name:'{'+W+'}'+name

def set_text(element,value):
    old=element.find('w:r',NS)
    props=deepcopy(old.find('w:rPr',NS)) if old is not None and old.find('w:rPr',NS) is not None else None
    for child in list(element):
        if child.tag!=q('pPr'):element.remove(child)
    run=etree.SubElement(element,q('r'))
    if props is not None:run.append(props)
    for index,line in enumerate(value.split('\n')):
        if index:etree.SubElement(run,q('br'))
        text=etree.SubElement(run,q('t'));text.text=line
        text.set('{http://www.w3.org/XML/1998/namespace}space','preserve')

def cell_text(cell,value,center=False):
    paragraphs=cell.findall('w:p',NS)
    first=paragraphs[0]
    for p in paragraphs[1:]:cell.remove(p)
    set_text(first,value)
    props=first.find('w:pPr',NS)
    if props is None:
        props=etree.Element(q('pPr'));first.insert(0,props)
    for node in props.findall('w:jc',NS):props.remove(node)
    etree.SubElement(props,q('jc')).set(q('val'),'center' if center else 'left')
    for run in first.findall('w:r',NS):
        fmt=run.find('w:rPr',NS)
        if fmt is None:
            fmt=etree.Element(q('rPr'));run.insert(0,fmt)
        for name in ('sz','szCs'):
            node=fmt.find('w:'+name,NS)
            if node is None:node=etree.SubElement(fmt,q(name))
            node.set(q('val'),'15')

def paragraph(doc,text='',size=10.5,bold=False):
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.LEFT;p.paragraph_format.space_after=Pt(4);p.paragraph_format.line_spacing=1.05
    run=p.add_run(text);run.font.name='바탕';run.font.size=Pt(size);run.font.bold=bold;run.font.color.rgb=RGBColor(0,0,0)
    fonts=run._element.get_or_add_rPr().get_or_add_rFonts();fonts.set(q('eastAsia'),'바탕')
    return p

def heading(doc,text):
    p=paragraph(doc,text,13,True);p.paragraph_format.keep_with_next=True
    return p

def picture(doc,path,width):
    if doc.paragraphs:doc.paragraphs[-1].paragraph_format.keep_with_next=True
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after=Pt(5);p.add_run().add_picture(str(path),width=Inches(width));return p

def new_page(doc,title):
    doc.add_page_break();heading(doc,title)

def main():
    reference_hash=hashlib.sha256(REF.read_bytes()).hexdigest()
    with ZipFile(REF) as archive:parts={name:archive.read(name) for name in archive.namelist()}
    before=dict(parts)
    xml=etree.fromstring(parts['word/document.xml']);body=xml.find('w:body',NS)
    original_section=etree.tostring(body.find('w:sectPr',NS))
    paragraphs=body.findall('w:p',NS)
    set_text(paragraphs[2],'학번 : 2020105671');set_text(paragraphs[3],'이름 : 하대진')
    department=deepcopy(paragraphs[3]);set_text(department,'학과 : 컴퓨터공학과')
    body.replace(paragraphs[4],department)
    set_text(paragraphs[5],'진행본  웹캠 실측과 클라우드 검증 후 최종 확정')
    draft_run=paragraphs[5].find('w:r',NS)
    draft_props=draft_run.find('w:rPr',NS)
    if draft_props is None:
        draft_props=etree.Element(q('rPr'));draft_run.insert(0,draft_props)
    for tag in ('sz','szCs'):
        node=draft_props.find('w:'+tag,NS)
        if node is None:node=etree.SubElement(draft_props,q(tag))
        node.set(q('val'),'18')
    table=body.find('w:tbl',NS);rows=table.findall('w:tr',NS)
    requirements=json.loads((ROOT/'docs/assessment-requirements.json').read_text(encoding='utf-8'))
    labels={'complete':'완료','partial':'부분','pending':'대기','deferred':'미정'}
    for i,item in enumerate(requirements['requirements'],start=2):
        cells=rows[i].findall('w:tc',NS)
        cell_text(cells[4],labels[item['status']],center=True)
        cell_text(cells[6],item.get('report_evidence',''))
    # Keep the supplied header/footer, correcting only the stale course metadata.
    header=etree.fromstring(parts['word/header1.xml'])
    for p in header.findall('.//w:p',NS):
        texts=p.findall('.//w:t',NS);value=''.join(text.text or '' for text in texts)
        if '공통평가' in value:
            texts[0].text=value.replace('2024','2026').replace('공통평가 01','공통평가 02')
            for text in texts[1:]:text.text=''
    parts['word/header1.xml']=etree.tostring(header,xml_declaration=True,encoding='UTF-8',standalone=True)
    settings=etree.fromstring(parts['word/settings.xml'])
    update=settings.find('w:updateFields',NS)
    if update is None:update=etree.SubElement(settings,q('updateFields'))
    update.set(q('val'),'true')
    parts['word/settings.xml']=etree.tostring(settings,xml_declaration=True,encoding='UTF-8',standalone=True)

    appendix=Document();heading(appendix,'구현 및 검증 결과')
    paragraph(appendix,'YOLOv5가 객체를 검출한 사진을 Django REST API로 등록하고 Android 앱에서 확인했다. 이전 프레임에 없던 객체 종류가 나타날 때 등록하며, 같은 장면이 이어지는 동안에는 중복 전송하지 않는다.')
    paragraph(appendix,'서버와 검출기는 WSL Ubuntu에서 실행하고 Android 앱과 모바일 웹은 Windows의 Android 에뮬레이터에서 확인했다. 공식 샘플 사진과 이 사진으로 만든 영상으로 검증했으며, 웹캠은 연결 후 별도로 확인한다.')
    paragraph(appendix,'GitHub 저장소  https://github.com/haddol7/mobile_web_service_02',9)
    heading(appendix,'B01 제출 폴더 구조와 GitHub 업로드')
    paragraph(appendix,'공통평가 01과 별도인 저장소에서 PhotoBlogServer, PhotoViewer, YOLOv5 폴더와 보고서 파일을 확인했다.',9.5)
    picture(appendix,ROOT/'evidence/screenshots/github-folder-structure.jpg',5.3)
    heading(appendix,'B02 원본 검출기 실행 결과')
    paragraph(appendix,'Ultralytics v7.0 원본 detect.py의 SHA256을 대조한 뒤 CPU로 실행했다. bus.jpg에서 사람 4명과 버스 1대를 검출했다.',9.5)
    picture(appendix,ROOT/'evidence/yolo-pipeline/original-image/bus.jpg',2.7)

    new_page(appendix,'B03 검출기 코드 수정')
    paragraph(appendix,'ChangeDetection은 프레임마다 객체 종류별 존재 여부를 비교한다. 0에서 1로 바뀐 종류가 있으면 검출 상자를 표시한 사진을 320 x 240 JPEG로 저장하고 게시글을 등록한다. 인증은 서버의 DRF Token 방식에 맞췄다.')
    picture(appendix,ROOT/'evidence/screenshots/changedetection-vscode.png',6.25)
    paragraph(appendix,'추가 소스는 YOLOv5/changedetection.py이고 추론 루프의 연결 위치는 YOLOv5/detect.py다.',9)
    paragraph(appendix,'첫 검출, 같은 장면, 빈 화면, 재등장 순서로 실제 추론을 실행했다. 게시글은 첫 검출과 재등장에서 1개씩, 총 2개가 등록됐다. 같은 장면과 빈 화면은 전송하지 않았다.')

    new_page(appendix,'B03 사진 저장과 HTTP 등록')
    paragraph(appendix,'검출 상자가 표시된 프레임을 JPEG로 저장한 뒤 제목과 본문, 이미지 파일을 multipart 요청으로 전송한다. 서버의 HTTP 201 응답과 게시글 ID를 확인한 경우에만 등록 성공으로 처리한다.')
    picture(appendix,ROOT/'evidence/screenshots/changedetection-upload-vscode.png',6.25)
    paragraph(appendix,'YOLOv5/changedetection.py의 send 함수다. 인증값은 비공개 환경변수로 전달하며 이 캡처에는 실제 인증값이 없다.',9)

    new_page(appendix,'B03 추론 루프 연결')
    paragraph(appendix,'검출한 객체 종류의 존재 여부를 detected_current에 기록한다. 검출 상자를 그린 프레임을 changes.add에 전달하고, 등록이 완료되면 게시글 ID를 출력한다.')
    picture(appendix,ROOT/'evidence/screenshots/detect-hook-vscode.png',6.25)
    paragraph(appendix,'YOLOv5/detect.py의 프레임별 검출 결과 처리 부분이다. 실제 실행 기록은 evidence/yolo-pipeline/server-registration.txt에 있다.',9)

    new_page(appendix,'B04 로컬 서버 API 확인')
    paragraph(appendix,'http://127.0.0.1:8020/api_root/ 에서 API 루트의 HTTP 200 응답을 확인했다.',9.5)
    picture(appendix,ROOT/'evidence/screenshots/local-api-root.jpg',6.25)
    paragraph(appendix,'검출 사진은 /api_root/Post/ 에서 목록으로 조회된다. id, author, title, text, created_date, published_date, image의 7개 필드가 유지된다.',9.5)
    picture(appendix,ROOT/'evidence/screenshots/local-api-posts.jpg',6.25)

    new_page(appendix,'B05 로컬 블로그 등록 결과')
    paragraph(appendix,'http://127.0.0.1:8020/ 에서 실제 검출 사진 2개와 제목을 확인했다. 전송한 JPEG와 서버가 저장한 JPEG, HTTP로 다시 조회한 JPEG의 SHA256이 일치했다.')
    picture(appendix,ROOT/'evidence/screenshots/local-list.jpg',6.25)
    paragraph(appendix,'이미지 SHA256  8008025bfc271eeb39dd8b00e8f64bdf5f2e74df8e665df41871f22d3c878cfe',8)
    heading(appendix,'B06 자동 검증 결과')
    for text in ['WSL Django 검사와 마이그레이션 일관성 검사 통과',
                 'Django 전체 테스트 148개 통과', '전체 148개 중 HTTP 사례 15개를 별도 엔진으로 재실행해 통과',
                 '객체 출현과 전송 로직 단위 테스트 8개 통과',
                 'Windows Android 단위 테스트 38개 통과',
                 'Android Lint 오류 0개와 경고 7개를 확인했고 빌드 검사 통과',
                 'Android 에뮬레이터의 YOLO 게시글 목록과 상세 화면 검증 1개 통과']:
        paragraph(appendix,text,10)
    paragraph(appendix,'원본 결과 기록은 evidence/content/server, evidence/edge-tests, evidence/content/android, evidence/yolo-pipeline에 보관했다.',9)

    new_page(appendix,'B07 Android 모바일 화면 확인')
    paragraph(appendix,'별도로 설치한 사진 블로그 02 앱에서 WSL 서버에 등록된 검출 사진을 조회했다. 이미지 바이트의 SHA256을 확인하고 실제 목록과 상세 화면을 캡처했다.')
    pair=appendix.add_table(rows=1,cols=2)
    for cell,name in zip(pair.rows[0].cells,['yolo-native-list.png','yolo-native-detail.png']):
        p=cell.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(ROOT/'evidence/screenshots'/name),width=Inches(2.75))
    paragraph(appendix,'왼쪽은 목록 화면, 오른쪽은 상세 화면이다. 접속 주소는 http://10.0.2.2:8020/ 이다.',9)

    new_page(appendix,'B07 Android 모바일 웹 화면 확인')
    paragraph(appendix,'Android Chrome에서 같은 검출 게시글의 목록과 상세 화면을 확인했다. 목록에는 검출 사진 2개가 함께 보이며 상세 화면에는 제목, 사진과 검출 내용이 표시된다.')
    pair=appendix.add_table(rows=1,cols=2)
    for cell,name in zip(pair.rows[0].cells,['yolo-mobile-web-list.png','yolo-mobile-web-detail.png']):
        p=cell.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(ROOT/'evidence/mobile-flow'/name),width=Inches(2.75))
    paragraph(appendix,'왼쪽은 목록 화면, 오른쪽은 상세 화면이다. 주소창의 10.0.2.2는 에뮬레이터에서 WSL 검증 서버에 접속하는 주소다. 이 검증은 로컬 서버를 대상으로 했다.',9)
    paragraph(appendix,'앱의 이미지 해시 검사와 화면 확인 1개도 다시 통과했다. 실행 기록과 HTTP 응답은 evidence/mobile-flow에 보관했다.',9)

    new_page(appendix,'B08 영상 입력과 오류 처리 검증')
    paragraph(appendix,'공식 bus.jpg와 빈 프레임을 조합한 30프레임 영상을 실제 YOLOv5에 입력했다. 초당 5프레임이며, 검출된 사진은 별도 검증 DB의 Django 서버로 전송했다.')
    for text in ['첫 6프레임은 빈 화면으로 게시글이 등록되지 않았다.',
                 '다음 12프레임에는 사람과 버스가 계속 나타났고 첫 검출에서만 게시글 1개가 등록됐다.',
                 '다음 6프레임은 빈 화면으로 게시글이 추가되지 않았다.',
                 '마지막 6프레임에 사람과 버스가 다시 나타나 게시글 1개가 추가됐다.']:
        paragraph(appendix,text)
    paragraph(appendix,'영상 실행으로 등록된 사진은 총 2개이며 모두 320 x 240 JPEG였다. 잘못된 검증용 인증값으로 보낸 요청은 서버가 거부했고 게시글 목록은 유지됐다. 전송에 실패한 사진은 로컬에 남아 있는 것을 확인했다.')
    paragraph(appendix,'클라우드 검사 도구도 이 격리 서버에서 실행해 기존 게시글과 사진의 보존, 신규 등록과 조회를 확인했다. 이는 검사 도구의 로컬 검증이며 PythonAnywhere 운영 검증은 별도 항목으로 남겨 두었다.')
    paragraph(appendix,'실행 기록  evidence/video-flow/verification.json 및 detector-output.txt',9)
    heading(appendix,'WSL 실행 환경 확인')
    paragraph(appendix,'전용 가상환경의 Python 3.12.15에서 OpenCV 로딩과 PyTorch CPU 연산을 확인했다. pip check에서 패키지 의존성 충돌이 없었고 공식 사전 학습 가중치의 SHA256도 일치했다.')
    paragraph(appendix,'환경 기록  evidence/environment/wsl-runtime.json 및 wsl-installed.txt',9)
    paragraph(appendix,'실물 웹캠은 연결되지 않아 영상 입력 검증으로 웹캠 항목을 완료 처리하지 않았다. PythonAnywhere의 02 전환과 운영 캡처, 기본 기능 후 선정할 추가 편의 기능도 완료 항목에 포함하지 않았다.')

    memory=BytesIO();appendix.save(memory)
    with ZipFile(memory) as archive:added={name:archive.read(name) for name in archive.namelist()}
    added_xml=etree.fromstring(added['word/document.xml'])
    rels=etree.fromstring(parts['word/_rels/document.xml.rels'])
    imported_rels=etree.fromstring(added['word/_rels/document.xml.rels'])
    old_ids={node.get('Id') for node in rels}
    remap={};next_id=1
    for relation in imported_rels:
        if not relation.get('Type','').endswith('/image'):continue
        while 'rId'+str(next_id) in old_ids:next_id+=1
        new_id='rId'+str(next_id);old_ids.add(new_id)
        target='media/assessment02-'+Path(relation.get('Target')).name
        parts['word/'+target]=added['word/'+relation.get('Target')]
        copy=deepcopy(relation);copy.set('Id',new_id);copy.set('Target',target);rels.append(copy)
        remap[relation.get('Id')]=new_id
    max_doc_id=max([int(node.get('id','0')) for node in xml.iter() if etree.QName(node).localname=='docPr']+[0])
    for element in added_xml.find('w:body',NS):
        if element.tag==q('sectPr'):continue
        copy=deepcopy(element)
        for node in copy.iter():
            for key,value in list(node.attrib.items()):
                if key in ('{'+R+'}embed','{'+R+'}id') and value in remap:node.set(key,remap[value])
            if etree.QName(node).localname=='docPr':max_doc_id+=1;node.set('id',str(max_doc_id))
        body.insert(len(body)-1,copy)
    parts['word/document.xml']=etree.tostring(xml,xml_declaration=True,encoding='UTF-8',standalone=True)
    parts['word/_rels/document.xml.rels']=etree.tostring(rels,xml_declaration=True,encoding='UTF-8',standalone=True)
    types=etree.fromstring(parts['[Content_Types].xml'])
    extensions={node.get('Extension') for node in types}
    for extension,kind in [('jpg','image/jpeg'),('jpeg','image/jpeg'),('png','image/png')]:
        if extension not in extensions:etree.SubElement(types,'{'+CT+'}Default',Extension=extension,ContentType=kind)
    parts['[Content_Types].xml']=etree.tostring(types,xml_declaration=True,encoding='UTF-8',standalone=True)
    allowed={'word/document.xml','word/header1.xml','word/settings.xml','word/_rels/document.xml.rels','[Content_Types].xml'}
    assert all(parts[name]==value for name,value in before.items() if name not in allowed)
    assert etree.tostring(body.find('w:sectPr',NS))==original_section
    assert hashlib.sha256(REF.read_bytes()).hexdigest()==reference_hash
    with ZipFile(OUT,'w',ZIP_DEFLATED) as archive:
        for name,value in parts.items():archive.writestr(name,value)
    print(json.dumps({'output':str(OUT),'source_template_preserved':True,'opaque_parts_preserved':True,'section_geometry_preserved':True},ensure_ascii=False))

if __name__=='__main__':main()
