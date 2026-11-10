"""Fill the supplied assessment template and embed only actual, verified evidence."""
from copy import deepcopy
from datetime import date
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
    requirements=json.loads((ROOT/'docs/assessment-requirements.json').read_text(encoding='utf-8'))
    reference_hash=hashlib.sha256(REF.read_bytes()).hexdigest()
    with ZipFile(REF) as archive:parts={name:archive.read(name) for name in archive.namelist()}
    before=dict(parts)
    xml=etree.fromstring(parts['word/document.xml']);body=xml.find('w:body',NS)
    original_section=etree.tostring(body.find('w:sectPr',NS))
    paragraphs=body.findall('w:p',NS)
    set_text(paragraphs[2],'학번 : 2020105671');set_text(paragraphs[3],'이름 : 하대진')
    department=deepcopy(paragraphs[3]);set_text(department,'학과 : 컴퓨터공학과')
    body.replace(paragraphs[4],department)
    checked=date.fromisoformat(requirements['report_state']['updated_date'])
    set_text(paragraphs[5],f'검증 기준일  {checked.year}년 {checked.month}월 {checked.day}일')
    draft_run=paragraphs[5].find('w:r',NS)
    draft_props=draft_run.find('w:rPr',NS)
    if draft_props is None:
        draft_props=etree.Element(q('rPr'));draft_run.insert(0,draft_props)
    for tag in ('sz','szCs'):
        node=draft_props.find('w:'+tag,NS)
        if node is None:node=etree.SubElement(draft_props,q(tag))
        node.set(q('val'),'18')
    table=body.find('w:tbl',NS);rows=table.findall('w:tr',NS)
    labels={'complete':'완료','partial':'부분','pending':'대기','deferred':'미정'}
    for i,item in enumerate(requirements['requirements'],start=2):
        cells=rows[i].findall('w:tc',NS)
        cell_text(cells[4],labels[item['status']],center=True)
        cell_text(cells[6],item.get('report_evidence',''))
    for offset,item in enumerate(requirements.get('extra_requirements',[]),start=12):
        cells=rows[offset].findall('w:tc',NS)
        for column,value in enumerate([item['id'],item['role'],item['name'],item['description'],labels[item['status']],'',item['report_evidence']]):
            cell_text(cells[column],value,center=column in (0,1,4))
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

    from report_content import FIGURES, build_appendix
    appendix=build_appendix()
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
    inventory=[{'path':name,'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest()} for name in FIGURES]
    (ROOT/'docs/report-figures.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    from report_basic_sections import BASIC_EVIDENCE
    (ROOT/'docs/basic-evidence-guide.json').write_text(json.dumps({
        'scope':'Common Assessment 02 original items 1 through 9',
        'figures':BASIC_EVIDENCE,
        'requirement_ids':sorted({item for figure in BASIC_EVIDENCE for item in figure['assessment_ids']},key=int),
        'all_figures_have_individual_explanations':all(len(figure['explanation'])>=2 for figure in BASIC_EVIDENCE)
    },ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(OUT),'source_template_preserved':True,'opaque_parts_preserved':True,'section_geometry_preserved':True},ensure_ascii=False))

if __name__=='__main__':main()
