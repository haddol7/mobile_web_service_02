"""Collect official research walking footage and decode it inside WSL."""
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import ftplib
import hashlib
import json
import os
from pathlib import Path
import re

import cv2
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence/private/cctv-walking"
PAGE="https://homepages.inf.ed.ac.uk/rbf/CAVIARDATA1/"


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=="a" and values.get("href"):self.links.append(urljoin(PAGE,values["href"]))


def collect(name,links):
    url=next(link for link in links if link.endswith('/'+name))
    target=OUT/name
    if not target.exists():
        response=requests.get(url,timeout=(10,60));response.raise_for_status()
        assert len(response.content)<40*1024**2 and len(response.content)>100000
        target.write_bytes(response.content)
    capture=cv2.VideoCapture(str(target));frames=0;fps=capture.get(cv2.CAP_PROP_FPS)
    total=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));previews=[]
    while True:
        ok,image=capture.read()
        if not ok:break
        height,width=image.shape[:2];frames+=1
    capture.release();assert frames>0
    # MPEG2 container frame counts can describe duration packets rather than decoded pictures.
    wanted={int(frames*f) for f in (.15,.5,.85)}
    capture=cv2.VideoCapture(str(target));index=0
    while True:
        ok,image=capture.read()
        if not ok:break
        if index in wanted:
            preview=OUT/(target.stem+f"-{index}.jpg");assert cv2.imwrite(str(preview),image)
            previews.append({"frame_index":index,"path":str(preview.relative_to(ROOT))})
        index+=1
    capture.release();assert len(previews)==3
    return {"id":target.stem,"dataset":"CAVIAR","url":url,"path":str(target.relative_to(ROOT)),
            "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),"bytes":target.stat().st_size,
            "decoded_frames":frames,"container_frame_count":total,"fps":fps,"size":[width,height],"previews":previews,"full_decode_pass":True,
            "view":"frontal hallway" if 'front' in name else "along corridor"}


def epfl_probe():
    try:
        response=requests.get("https://www.epfl.ch/labs/mmspg/downloads/pevid-uhd/",timeout=(8,15));response.raise_for_status()
        source=response.text
        emails=[]
        for encoded in re.findall(r'data-cfemail="([a-f0-9]+)"',source):
            raw=bytes.fromhex(encoded);emails.append(''.join(chr(value^raw[0]) for value in raw[1:]))
        section=source.split('User name:')[-1].split('Password:')[0]
        match=re.search(r'data-cfemail="([a-f0-9]+)"',section)
        if match:
            raw=bytes.fromhex(match[1]);username=''.join(chr(value^raw[0]) for value in raw[1:])
        else:
            match=re.search(r'(?:mailto:|>)([\w.+-]+@epfl\.ch)',section)
            if not match:return {"download_available":False,"reason":"official FTP username not readable"}
            username=match[1]
        match=re.search(r'Password:\s*(?:</?[^>]+>\s*)*([A-Za-z0-9]+)',source)
        if not match:return {"download_available":False,"reason":"official FTP access details not readable"}
        client=ftplib.FTP(timeout=12);client.connect("tremplin.epfl.ch",21);client.login(username,match[1]);client.cwd("PEViD/PEViD-UHD")
        files=client.nlst();client.quit()
        return {"download_available":True,"directory_items":files[:80]}
    except Exception as error:
        return {"download_available":False,"error_type":type(error).__name__}


def main():
    assert os.environ.get("WSL_DISTRO_NAME"),"Use WSL"
    OUT.mkdir(parents=True,exist_ok=True)
    response=requests.get(PAGE,timeout=(10,25));response.raise_for_status()
    page=Links();page.feed(response.text)
    names=("WalkByShop1front.mpg","WalkByShop1cor.mpg","EnterExitCrossingPaths1front.mpg")
    with ThreadPoolExecutor(max_workers=3) as pool:
        clips=list(pool.map(lambda name:collect(name,page.links),names))
    mot=json.loads((ROOT/"evidence/tracking-samples/collection.json").read_text())
    for key in ("MOT17-09-SDP","MOT17-02-SDP"):
        item=next(c for c in mot["sequences"] if c["id"]==key)
        path=ROOT/item["video"]["path"]
        capture=cv2.VideoCapture(str(path));total=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));previews=[]
        for fraction in (.15,.5,.85):
            index=int(total*fraction);capture.set(cv2.CAP_PROP_POS_FRAMES,index);ok,image=capture.read();assert ok
            preview=OUT/(key+f"-{index}.jpg");assert cv2.imwrite(str(preview),image);previews.append({"frame_index":index,"path":str(preview.relative_to(ROOT))})
        capture.release()
        clips.append({"id":key,"dataset":"MOTChallenge","url":item["video"]["url"],"path":item["video"]["path"],
                      "sha256":item["video"]["sha256"],"decoded_frames":item["decoded_frames"],"fps":item["fps"],
                      "size":item["decoded_size"],"previews":previews,"full_decode_pass":True,"reused_verified_video":True})
    record={"collected_utc":datetime.now(timezone.utc).isoformat(),"environment":"WSL Ubuntu","clips":clips,
            "sources":[{"url":PAGE,"terms":"CC BY-SA; acknowledge EC CAVIAR project IST 2001 37540"},
                       {"url":"https://motchallenge.net/data/MOT17/","terms":"MOTChallenge academic/noncommercial terms; original sequence conditions apply"}],
            "raw_videos_in_git":False,"epfl_official_ftp":epfl_probe(),"pass":True}
    (OUT/"collection.json").write_text(json.dumps(record,indent=2)+"\n")
    public={**record,"clips":[{k:v for k,v in c.items() if k!="previews"} for c in clips]}
    (ROOT/"evidence/history/cctv-walking-collection.json").write_text(json.dumps(public,indent=2)+"\n")
    print(json.dumps({"pass":True,"clips":[{k:c[k] for k in ("id","size","decoded_frames")} for c in clips],"epfl":record["epfl_official_ftp"]}),flush=True)


if __name__=="__main__":main()
