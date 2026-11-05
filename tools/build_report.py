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
    paragraph(appendix,'서버와 검출기는 WSL Ubuntu에서 실행하고 Android 앱은 Windows의 에뮬레이터에서 확인했다. 웹캠은 연결 후 검증할 예정이며, 아래 검출 결과는 공식 샘플 정지 사진으로 확인한 내용이다.')
    paragraph(appendix,'GitHub 저장소  https://github.com/haddol7/mobile_web_service_02',9)
    heading(appendix,'B03 원본 검출기 실행 결과')
    paragraph(appendix,'Ultralytics v7.0 원본 detect.py의 SHA256을 대조한 뒤 CPU로 실행했다. bus.jpg에서 사람 4명과 버스 1대를 검출했다.',9.5)
    picture(appendix,ROOT/'evidence/yolo-pipeline/original-image/bus.jpg',2.7)

    new_page(appendix,'B02 검출기 코드 수정')
    paragraph(appendix,'ChangeDetection은 프레임마다 객체 종류별 존재 여부를 비교한다. 0에서 1로 바뀐 종류가 있으면 검출 상자를 표시한 사진을 320 x 240 JPEG로 저장하고 게시글을 등록한다. 인증은 서버의 DRF Token 방식에 맞췄다.')
    picture(appendix,ROOT/'evidence/screenshots/changedetection-vscode.png',6.25)
    paragraph(appendix,'추가 소스  YOLOv5/changedetection.py  |  연결 위치  YOLOv5/detect.py',9)
    paragraph(appendix,'첫 검출, 같은 장면, 빈 화면, 재등장 순서로 실제 추론을 실행했다. 게시글은 첫 검출과 재등장에서 1개씩, 총 2개가 등록됐다. 같은 장면과 빈 화면은 전송하지 않았다.')

    new_page(appendix,'B04 로컬 서버 API 확인')
    paragraph(appendix,'http://127.0.0.1:8020/api_root/ 에서 API 루트의 HTTP 200 응답을 확인했다.',9.5)
    picture(appendix,ROOT/'evidence/screenshots/local-api-root.jpg',6.25)
    paragraph(appendix,'검출 사진은 /api_root/Post/ 에서 목록으로 조회된다. id, author, title, text, created_date, published_date, image의 7개 필드가 유지된다.',9.5)
    picture(appendix,ROOT/'evidence/screenshots/local-api-posts.jpg',6.25)

    new_page(appendix,'B05 로컬 블로그 등록 결과')
    paragraph(appendix,'http://127.0.0.1:8020/ 에서 실제 검출 사진 2개와 제목을 확인했다. 전송한 JPEG와 서버가 저장한 JPEG, HTTP로 다시 조회한 JPEG의 SHA256이 일치했다.')
    picture(appendix,ROOT/'evidence/screenshots/local-list.jpg',6.25)
    paragraph(appendix,'이미지 SHA256  8008025bfc271eeb39dd8b00e8f64bdf5f2e74df8e665df41871f22d3c878cfe',8)
    heading(appendix,'B07 자동 검증 결과')
    for text in ['WSL Django 검사와 마이그레이션 일관성 검사 통과',
                 'Django 테스트 148개 통과', '실제 HTTP API 테스트 15개 통과',
                 '객체 출현과 전송 로직 단위 테스트 8개 통과',
                 'Windows Android 단위 테스트 38개 및 Lint 통과',
                 'Android 에뮬레이터의 YOLO 게시글 목록과 상세 화면 검증 1개 통과']:
        paragraph(appendix,text,10)
    paragraph(appendix,'원본 결과 기록은 evidence/content/server, evidence/edge-tests, evidence/content/android, evidence/yolo-pipeline에 보관했다.',9)

    new_page(appendix,'B06 Android 모바일 화면 확인')
    paragraph(appendix,'별도로 설치한 사진 블로그 02 앱에서 WSL 서버에 등록된 검출 사진을 조회했다. 이미지 바이트의 SHA256을 확인하고 실제 목록과 상세 화면을 캡처했다.')
    pair=appendix.add_table(rows=1,cols=2)
    for cell,name in zip(pair.rows[0].cells,['yolo-native-list.png','yolo-native-detail.png']):
        p=cell.paragraphs[0];p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(ROOT/'evidence/screenshots'/name),width=Inches(2.75))
    paragraph(appendix,'왼쪽은 목록 화면, 오른쪽은 상세 화면이다. 접속 주소는 http://10.0.2.2:8020/ 이다.',9)

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
