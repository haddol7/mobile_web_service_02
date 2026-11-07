"""Fetch and decode official MOT footage with annotations inside the WSL environment."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
import configparser
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from urllib.parse import urljoin
from zipfile import ZipFile

import cv2
import numpy as np
import requests

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'evidence/private/tracking-samples'
PUBLIC=ROOT/'evidence/tracking-samples'
CATALOG=ROOT/'docs/testing/video-sources.json'

def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()

def fetch(url,path,limit):
    if path.is_file():
        return {'url':url,'bytes':path.stat().st_size,'sha256':sha(path),'reused':True}
    temporary=path.with_suffix(path.suffix+'.part');path.parent.mkdir(parents=True,exist_ok=True)
    size=0
    try:
        with requests.get(url,stream=True,timeout=(15,90)) as response:
            response.raise_for_status()
            expected=int(response.headers.get('Content-Length','0'))
            if expected>limit:raise ValueError('Download exceeds fixture limit')
            with temporary.open('wb') as file:
                for chunk in response.iter_content(1024*256):
                    size+=len(chunk)
                    if size>limit:raise ValueError('Download exceeds fixture limit')
                    file.write(chunk)
            if expected and expected!=size:raise ValueError('Incomplete download')
        temporary.replace(path)
    finally:
        if temporary.exists():temporary.unlink()
    print(f'Downloaded {path.name}: {size:,} bytes',flush=True)
    return {'url':url,'bytes':size,'sha256':sha(path),'reused':False}

class PageLinks(HTMLParser):
    def __init__(self,base):super().__init__();self.base=base;self.links=set()
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=='a' and values.get('href'):self.links.add(urljoin(self.base,values['href']))

def annotations(archive,sequence):
    with ZipFile(archive) as bundle:
        if bundle.testzip() is not None:raise ValueError('Annotation archive CRC failure')
        endings={name:next((item for item in bundle.namelist() if item.endswith('/'+sequence+'/'+name)),None)
                 for name in ['gt/gt.txt','seqinfo.ini']}
        if not endings['gt/gt.txt']:raise ValueError(f'Missing public ground truth for {sequence}')
        target=PRIVATE/sequence;target.mkdir(parents=True,exist_ok=True)
        for name,member in endings.items():
            if member:
                destination=target/Path(name).name
                destination.write_bytes(bundle.read(member))
        return endings

def read_gt(path,kind,total):
    kept=[];ignored=0
    with path.open(newline='') as file:
        for row in csv.reader(file):
            values=list(map(float,row));frame,identity=int(values[0]),int(values[1])
            if not 1<=frame<=total or len(values)<7 or not np.isfinite(values).all():
                raise ValueError('Invalid ground-truth coordinates/frame')
            if values[4]<=0 or values[5]<=0:raise ValueError('Nonpositive ground-truth box')
            # MOT17: mark=1 and class=1 are evaluable pedestrians. Other classes remain in raw GT.
            if values[6]<=0 or (kind=='mot17' and int(values[7])!=1):ignored+=1;continue
            kept.append((frame,identity,*values[2:6],values[8] if kind=='mot17' else None))
    return kept,ignored

def inspect(spec,asset):
    directory=PRIVATE/spec['id'];video=directory/'raw.mp4'
    capture=cv2.VideoCapture(str(video))
    if not capture.isOpened():raise ValueError('Video could not be decoded')
    declared=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));fps=capture.get(cv2.CAP_PROP_FPS)
    selected={1,max(1,spec['frames']//2),spec['frames']};frames={};count=0;dimensions=None
    while True:
        ok,frame=capture.read()
        if not ok:break
        count+=1
        shape=(frame.shape[1],frame.shape[0])
        if dimensions is None:dimensions=shape
        if dimensions!=shape:raise ValueError('Changing frame geometry')
        if count in selected:frames[count]=frame
    capture.release()
    if count!=spec['frames']:raise ValueError(f"{spec['id']}: decoded {count}, expected {spec['frames']} frames")
    if abs(fps-spec['fps'])>0.05:raise ValueError(f"{spec['id']}: FPS mismatch {fps}")
    gt,ignored=read_gt(directory/'gt.txt',asset['gt_format'],count)
    parser=configparser.ConfigParser();parser.read(directory/'seqinfo.ini')
    if parser.has_section('Sequence'):
        data=parser['Sequence']
        for key,expected in [('seqLength',count),('imWidth',spec['width']),('imHeight',spec['height']),('frameRate',spec['fps'])]:
            if int(data[key])!=expected:raise ValueError('Sequence metadata differs from catalogue')
    sx,sy=dimensions[0]/spec['width'],dimensions[1]/spec['height']
    panels=[]
    for number,frame in sorted(frames.items()):
        overlay=frame.copy()
        for entry in gt:
            fid,identity,x,y,w,h,_=entry
            if fid!=number:continue
            left,top,right,bottom=round(x*sx),round(y*sy),round((x+w)*sx),round((y+h)*sy)
            color=(40+(identity*37)%200,40+(identity*67)%200,40+(identity*97)%200)
            cv2.rectangle(overlay,(left,top),(right,bottom),color,2)
            cv2.putText(overlay,str(identity),(left,max(16,top)),cv2.FONT_HERSHEY_SIMPLEX,.5,color,1)
        width=640;height=round(frame.shape[0]*width/frame.shape[1])
        panel=np.hstack([cv2.resize(frame,(width,height)),cv2.resize(overlay,(width,height))])
        band=np.full((34,panel.shape[1],3),245,np.uint8)
        cv2.putText(band,f"{spec['id']} frame {number}: raw input (left), reference boxes (right)",(10,23),cv2.FONT_HERSHEY_SIMPLEX,.6,(20,20,20),1)
        panels.append(np.vstack([band,panel]))
    preview=directory/'alignment-review.jpg';cv2.imwrite(str(preview),np.vstack(panels))
    normalized=directory/'pedestrians.json'
    normalized.write_text(json.dumps({'source_format':asset['gt_format'],'coordinate_space':[spec['width'],spec['height']],
        'video_scale':[sx,sy],'rows':[list(item) for item in gt]},separators=(',',':')),encoding='utf-8')
    return {'id':spec['id'],'dataset':spec['dataset'],'split':spec['split'],'conditions':spec['conditions'],
            'video':dict(asset['video'],path=str(video.relative_to(ROOT))),
            'decoded_frames':count,'declared_frames':declared,'fps':fps,'duration_seconds':count/fps,
            'decoded_size':list(dimensions),'gt_coordinate_size':[spec['width'],spec['height']],
            'coordinate_scale':[sx,sy],'pedestrian_rows':len(gt),'ignored_gt_rows':ignored,
            'sequence_local_pedestrian_ids':len({row[1] for row in gt}),
            'ground_truth':{'path':str((directory/'gt.txt').relative_to(ROOT)),'sha256':sha(directory/'gt.txt')},
            'normalized_ground_truth':{'path':str(normalized.relative_to(ROOT)),'sha256':sha(normalized)},
            'alignment_preview':str(preview.relative_to(ROOT)),
            'frame_count_and_metadata_checks_pass':True,'visual_alignment_review':'pending',
            'cross_day_identity_ground_truth':False,'clothing_ground_truth':False,
            'passage_events_for_chosen_line_ground_truth':False}

def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run sample preparation with the WSL project virtualenv.')
    catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
    PRIVATE.mkdir(parents=True,exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
    dataset_assets={}
    for name,info in catalog['datasets'].items():
        response=requests.get(info['page'],timeout=30);response.raise_for_status()
        page=PRIVATE/(name+'-source.html');page.write_text(response.text,encoding='utf-8')
        parser=PageLinks(info['page']);parser.feed(response.text)
        if info['labels_url'] not in parser.links:raise ValueError('Labels URL is not linked by official source')
        dataset_assets[name]={'info':info,'links':parser.links}
    jobs=[]
    for name,asset in dataset_assets.items():
        destination=PRIVATE/(name+'Labels.zip')
        jobs.append(('labels:'+name,asset['info']['labels_url'],destination,30*1024**2))
    for spec in catalog['sequences']:
        url='https://motchallenge.net/sequenceVideos/'+spec['id']+'-raw.mp4'
        if url not in dataset_assets[spec['dataset']]['links']:raise ValueError('Raw video is not linked by official source')
        jobs.append((spec['id'],url,PRIVATE/spec['id']/'raw.mp4',200*1024**2))
    downloads={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks=[(name,pool.submit(fetch,url,path,limit)) for name,url,path,limit in jobs]
        for name,task in tasks:downloads[name]=task.result()
    sequences=[]
    for spec in catalog['sequences']:
        archive=PRIVATE/(spec['dataset']+'Labels.zip');annotations(archive,spec['id'])
        record=inspect(spec,{'gt_format':dataset_assets[spec['dataset']]['info']['gt_format'],'video':downloads[spec['id']]})
        sequences.append(record)
        print(f"Decoded {spec['id']}: {record['decoded_frames']} frames, {record['pedestrian_rows']} reference boxes",flush=True)
    result={'collected_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu',
            'catalog_sha256':sha(CATALOG),'license':catalog['license'],
            'annotation_archives':{name:downloads['labels:'+name] for name in catalog['datasets']},
            'sequences':sequences,'total_videos':len(sequences),'total_frames':sum(item['decoded_frames'] for item in sequences),
            'total_duration_seconds':sum(item['duration_seconds'] for item in sequences),
            'total_raw_video_bytes':sum(item['video']['bytes'] for item in sequences),
            'tracking_accuracy_measured':False,'reidentification_accuracy_measured':False,
            'rag_accuracy_measured':False,'webcam_tested':False,
            'collection_and_decode_pass':True,'visual_review_complete':False}
    (PUBLIC/'collection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key not in ['sequences','annotation_archives','license']},indent=2))

if __name__=='__main__':main()
