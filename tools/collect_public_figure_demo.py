"""Locate and pin named public-figure clips for an explicit demonstration gallery."""
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/private/public-figure-demo'

def metadata(repo):
    response=requests.get('https://huggingface.co/api/datasets/'+repo,timeout=(10,30));response.raise_for_status()
    data=response.json();matches=[f['rfilename'] for f in data.get('siblings',[]) if any(n in f['rfilename'].lower() for n in ('trump','obama'))]
    return {'repo':repo,'revision':data['sha'],'matches':matches,'file_count':len(data.get('siblings',[])),'license':data.get('cardData',{}).get('license')}

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    OUT.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(metadata,['saeed-5959/hdtf','global-optima-research/HDTF']))
    record={'checked_utc':datetime.now(timezone.utc).isoformat(),'repositories':results}
    (OUT/'source-discovery.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)

if __name__=='__main__':main()
