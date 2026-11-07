"""Collect labelled, independent person images and a pretrained ReID model for an isolated test."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
from zipfile import ZipFile

import cv2
import numpy as np
import requests
from PIL import Image

from collect_tracking_samples import fetch, sha

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/private/identity-samples'
PUBLIC=ROOT/'evidence/identity-samples'
DATA_URL='https://1drv.ms/u/c/08410a5868373edb/EdU4rBSX7-RGsal6Gh11V98BP7pi_pusChrlBLoNJIw7eg?e=EbeSTm&download=1'
ARCHIVE_SHA='2a1f63acf116e60dee1d7cee0d91ec87268309fac0e383d0da9270e56d829727'
WEIGHT_NAME='osnet_ain_x1_0_msmt17_256x128_amsgrad_ep50_lr0.0015_coslr_b64_fb10_softmax_labsmth_flip_jitter.pth'

def get_json(url):
    response=requests.get(url,timeout=45);response.raise_for_status();return response.json()

def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run collection in the WSL project virtualenv.')
    OUT.mkdir(parents=True,exist_ok=True);PUBLIC.mkdir(parents=True,exist_ok=True)
    archive=OUT/'Celeb-reID-light.zip';download=fetch(DATA_URL,archive,150*1024**2)
    assert sha(archive)==ARCHIVE_SHA,'Dataset archive differs from the inspected official download'
    private=[];counts={};ids={};hashes={}
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        readme=bundle.read('Celeb-reID-light/readme.txt')
        (OUT/'dataset-readme.txt').write_bytes(readme)
        for split,expected in [('gallery',934),('query',887)]:
            members=sorted(name for name in bundle.namelist() if name.startswith('Celeb-reID-light/'+split+'/') and name.endswith('.jpg'))
            assert len(members)==expected
            counts[split]=len(members);ids[split]=set();hashes[split]=set()
            for member in members:
                identity=int(Path(member).name.split('_')[0]);ids[split].add(identity)
                blob=bundle.read(member);digest=hashlib.sha256(blob).hexdigest();hashes[split].add(digest)
                # Blind filenames: a model receives RGB content and opaque IDs, never the official identity in a filename.
                target=OUT/'images'/split/(digest+'.jpg');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
                with Image.open(target) as image:
                    image.verify()
                private.append({'split':split,'official_identity':identity,'source_member':member,
                                'path':str(target.relative_to(ROOT)),'sha256':digest})
        assert ids['gallery']==ids['query'] and len(ids['query'])==100
    exact_overlap=hashes['query']&hashes['gallery']
    # Keep original records for audit, but mark exact cross-split duplicate images ineligible for a matching experiment.
    for item in private:item['eligible']=not(item['split']=='query' and item['sha256'] in exact_overlap)
    (OUT/'oracle.json').write_text(json.dumps(private,indent=2)+'\n',encoding='utf-8')
    official_readme=requests.get('https://raw.githubusercontent.com/Huang-3/Celeb-reID/master/README.md',timeout=30)
    official_readme.raise_for_status();(OUT/'official-source.md').write_text(official_readme.text,encoding='utf-8')

    revision=get_json('https://api.github.com/repos/KaiyangZhou/deep-person-reid/commits/master')['sha']
    model_dir=OUT/'model-source';model_dir.mkdir(exist_ok=True)
    source_records={}
    for source,destination in [('torchreid/models/osnet_ain.py','osnet_ain.py'),('LICENSE','LICENSE')]:
        url=f'https://raw.githubusercontent.com/KaiyangZhou/deep-person-reid/{revision}/{source}'
        response=requests.get(url,timeout=30);response.raise_for_status()
        target=model_dir/destination;target.write_bytes(response.content)
        source_records[destination]={'url':url,'sha256':sha(target)}
    hub=get_json('https://huggingface.co/api/models/kaiyangzhou/osnet?blobs=true')
    weight=next(item for item in hub['siblings'] if item['rfilename']==WEIGHT_NAME)
    expected=weight['lfs']['sha256'];weight_path=model_dir/WEIGHT_NAME
    weight_url=f"https://huggingface.co/kaiyangzhou/osnet/resolve/{hub['sha']}/{WEIGHT_NAME}"
    checkpoint=fetch(weight_url,weight_path,60*1024**2)
    assert sha(weight_path)==expected,'Checkpoint differs from model-author LFS SHA256'
    model={'name':'osnet_ain_x1_0','training_dataset':'MSMT17; no project training or Celeb-reID training',
           'architecture_commit':revision,'architecture_sources':source_records,'checkpoint_revision':hub['sha'],
           'checkpoint':checkpoint,'checkpoint_path':str(weight_path.relative_to(ROOT)),
           'expected_checkpoint_sha256':expected,'preprocessing':{'height':256,'width':128,'mean':[.485,.456,.406],'std':[.229,.224,.225]}}
    (OUT/'model.json').write_text(json.dumps(model,indent=2)+'\n',encoding='utf-8')

    # Inspect a deterministic sample of author-labelled pairs without copying these restricted images into the public repo.
    rows=[]
    for identity in sorted(ids['query'])[:8]:
        examples=[next(item for item in private if item['split']==split and item['official_identity']==identity) for split in ['gallery','query']]
        cells=[]
        for item in examples:
            image=cv2.imread(str(ROOT/item['path']));image=cv2.resize(image,(128,256))
            band=np.full((28,128,3),245,np.uint8)
            cv2.putText(band,f"ID {identity} {item['split']}",(3,19),cv2.FONT_HERSHEY_SIMPLEX,.4,(20,20,20),1)
            cells.append(np.vstack([band,image]))
        rows.append(np.hstack(cells))
    preview=np.hstack([np.vstack(rows[:4]),np.vstack(rows[4:])]);cv2.imwrite(str(OUT/'labelled-pairs-review.jpg'),preview)
    summary={'collected_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu',
             'dataset':'Celeb-reID-light official query/gallery only','source':'https://github.com/Huang-3/Celeb-reID',
             'download':download,'oracle_stored_privately':True,'identities':100,'gallery_images':934,'query_images':887,
             'decoded_test_images':len(private),'exact_cross_split_duplicate_images':len(exact_overlap),
             'eligible_query_images':sum(item['split']=='query' and item['eligible'] for item in private),
             'training_images_extracted':0,'real_capture_dates_available':False,'real_visit_counts_available':False,
             'blind_model_filenames':True,'model':model,
             'license_notice':'Research only; do not distribute dataset. Raw images, labels and per-image descriptors stay local.',
             'collection_pass':True,'identity_matching_accuracy_measured':False,
             'source_sha256':{'tools/collect_identity_samples.py':sha(ROOT/'tools/collect_identity_samples.py')}}
    (PUBLIC/'collection.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in summary.items() if key not in ['model','download','source_sha256']},indent=2))

if __name__=='__main__':main()
