"""Measure a pretrained identity matcher against withheld labels and replay decisions in a private DB.

This is an isolated experiment, not the production Django person registry or an actual visit-count test.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sqlite3
import time

import numpy as np
from PIL import Image
import torch
from torchvision import transforms

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'evidence/private/identity-samples'
PUBLIC=ROOT/'evidence/identity-samples'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def features(paths,model_info):
    """Only opaque image paths and model configuration enter inference. No oracle labels."""
    architecture=PRIVATE/'model-source/osnet_ain.py'
    assert sha(architecture)==model_info['architecture_sources']['osnet_ain.py']['sha256']
    checkpoint=ROOT/model_info['checkpoint_path']
    assert sha(checkpoint)==model_info['expected_checkpoint_sha256']
    spec=importlib.util.spec_from_file_location('official_osnet_ain',architecture)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    model=module.osnet_ain_x1_0(num_classes=1,pretrained=False)
    saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
    weights=saved.get('state_dict',saved)
    weights={key.removeprefix('module.'):value for key,value in weights.items()}
    expected=model.state_dict()
    usable={key:value for key,value in weights.items() if key in expected and expected[key].shape==value.shape}
    missing=[key for key in expected if key not in usable and not key.startswith('classifier.')]
    assert not missing,f'Feature layers not loaded: {missing}'
    model.load_state_dict(usable,strict=False);model.eval();torch.set_num_threads(4)
    transform=transforms.Compose([transforms.Resize((256,128)),transforms.ToTensor(),
        transforms.Normalize(model_info['preprocessing']['mean'],model_info['preprocessing']['std'])])
    result=[];started=time.perf_counter()
    with torch.inference_mode():
        for offset in range(0,len(paths),32):
            batch=[]
            for path in paths[offset:offset+32]:
                with Image.open(path) as image:batch.append(transform(image.convert('RGB')))
            vectors=model(torch.stack(batch))
            result.append(torch.nn.functional.normalize(vectors,dim=1).cpu().numpy())
            if offset%320==0:print(f'Encoded {min(offset+32,len(paths))}/{len(paths)} images',flush=True)
    values=np.concatenate(result)
    assert values.shape==(len(paths),512) and np.isfinite(values).all()
    return values,{'images':len(paths),'dimension':512,'seconds':time.perf_counter()-started,
                   'feature_weight_keys_loaded':len(usable),'unloaded_non_classifier_keys':missing}

def rank_profiles(query_vectors,gallery_vectors,profile_ids):
    """Match RGB-derived vectors to registered gallery profiles without access to query labels."""
    unique=sorted(set(profile_ids));similarities=query_vectors@gallery_vectors.T
    scores=np.stack([similarities[:,np.array(profile_ids)==identity].max(axis=1) for identity in unique],axis=1)
    order=np.argsort(-scores,axis=1,kind='stable')
    top=scores[np.arange(len(scores)),order[:,0]]
    margin=top-scores[np.arange(len(scores)),order[:,1]]
    return {'predicted':np.array(unique)[order[:,0]],'top':top,'margin':margin}

def measure(ranked,truth,registered,threshold,margin):
    accepted=(ranked['top']>=threshold)&(ranked['margin']>=margin)
    known=np.isin(truth,list(registered));correct=accepted&known&(ranked['predicted']==truth)
    wrong=accepted&~correct
    unknown=~known
    number=int(accepted.sum());unknown_n=int(unknown.sum());known_n=int(known.sum())
    return {'queries':len(truth),'known_queries':known_n,'unknown_queries':unknown_n,
            'accepted':number,'correct_links':int(correct.sum()),'wrong_links':int(wrong.sum()),
            'rejected_or_unresolved':int((~accepted).sum()),'unknown_false_links':int((accepted&unknown).sum()),
            'link_precision':float(correct.sum()/number) if number else None,
            'known_correct_link_coverage':float(correct.sum()/known_n) if known_n else None,
            'unknown_false_accept_rate':float((accepted&unknown).sum()/unknown_n) if unknown_n else None}

def main():
    if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run identity evaluation inside the WSL project virtualenv.')
    collection=json.loads((PUBLIC/'collection.json').read_text())
    oracle=json.loads((PRIVATE/'oracle.json').read_text())
    items=[item for item in oracle if item['eligible']]
    for item in items:assert sha(ROOT/item['path'])==item['sha256']
    model_info=collection['model']
    blind_paths=[ROOT/item['path'] for item in items]
    vectors,timing=features(blind_paths,model_info)
    np.save(PRIVATE/'descriptors.npy',vectors) # Descriptors and per-image data remain outside Git.
    gallery_mask=np.array([item['split']=='gallery' for item in items]);query_mask=~gallery_mask
    gv,qv=vectors[gallery_mask],vectors[query_mask]
    # Labels are read here, after inference, for registration grouping and independent scoring.
    gl=np.array([item['official_identity'] for item in items if item['split']=='gallery'])
    ql=np.array([item['official_identity'] for item in items if item['split']=='query'])
    closed=rank_profiles(qv,gv,gl)
    all_scores=qv@gv.T;order=np.argsort(-all_scores,axis=1,kind='stable')
    ranked_labels=gl[order]
    matches=ranked_labels==ql[:,None]
    precision=matches.cumsum(axis=1)/np.arange(1,len(gl)+1)
    average_precision=(precision*matches).sum(axis=1)/matches.sum(axis=1)
    unique_ids=sorted(set(gl),key=lambda value:hashlib.sha256(f'assessment02-identity-split-v1:{value}'.encode()).hexdigest())
    calibration_ids=unique_ids[:40];holdout_ids=unique_ids[40:]
    cal_registered=set(calibration_ids[:30]);test_registered=set(holdout_ids[:45])
    def subset(all_ids,registered):
        qm=np.isin(ql,all_ids);gm=np.isin(gl,list(registered))
        return rank_profiles(qv[qm],gv[gm],gl[gm]),ql[qm],qm
    cal,cal_truth,_=subset(calibration_ids,cal_registered)
    holdout,test_truth,test_mask=subset(holdout_ids,test_registered)
    best=None
    # Predeclared calibration goals; this is threshold calibration, not model training.
    for threshold in np.arange(.35,1.001,.005):
        for gap in np.arange(0,.201,.005):
            score=measure(cal,cal_truth,cal_registered,float(threshold),float(gap))
            if score['accepted'] and score['link_precision']>=.99 and score['unknown_false_accept_rate']<=.01:
                priority=(score['correct_links'],-score['wrong_links'],-float(threshold),-float(gap))
                if best is None or priority>best[0]:best=(priority,float(threshold),float(gap),score)
    if best is None:
        threshold,gap=1.001,1.001;cal_result=measure(cal,cal_truth,cal_registered,threshold,gap)
    else:_,threshold,gap,cal_result=best
    test_result=measure(holdout,test_truth,test_registered,threshold,gap)

    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    db_path=PRIVATE/('identity-replay-'+stamp+'.sqlite3')
    registered_map={identity:'profile-'+hashlib.sha256(f'gallery:{identity}'.encode()).hexdigest()[:16] for identity in test_registered}
    query_items=[item for item in items if item['split']=='query'];query_items=[item for item,yes in zip(query_items,test_mask) if yes]
    accepted=(holdout['top']>=threshold)&(holdout['margin']>=gap)
    with sqlite3.connect(db_path) as database:
        database.execute('PRAGMA foreign_keys=ON')
        database.executescript('CREATE TABLE profiles(id TEXT PRIMARY KEY); CREATE TABLE observations(id TEXT PRIMARY KEY, image_sha256 TEXT NOT NULL, fixture_time TEXT NOT NULL, time_source TEXT NOT NULL, profile_id TEXT REFERENCES profiles(id), status TEXT NOT NULL, similarity REAL NOT NULL);')
        database.executemany('INSERT INTO profiles VALUES(?)',[(value,) for value in registered_map.values()])
        records=[]
        for i,item in enumerate(query_items):
            selected=registered_map[int(holdout['predicted'][i])] if accepted[i] else None
            # Synthetic dates exercise storage only. They are never represented as real capture dates or visits.
            fixture_time=(datetime(2026,11,1,tzinfo=timezone.utc)+timedelta(hours=i)).isoformat()
            records.append(('observation-'+item['sha256'][:24],item['sha256'],fixture_time,
                'synthetic_fixture_not_real_capture_date',selected,'auto_candidate' if selected else 'unresolved',float(holdout['top'][i])))
        sql='INSERT INTO observations VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING'
        database.executemany(sql,records);first=database.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        database.executemany(sql,records);second=database.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        assert first==second==len(records)
        links=database.execute('SELECT COUNT(*) FROM observations WHERE profile_id IS NOT NULL').fetchone()[0]
        assert links==test_result['accepted'] and database.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert database.execute('SELECT COUNT(*) FROM observations WHERE status="confirmed"').fetchone()[0]==0
    # Detailed predictions/labels are local research data and are not published.
    (PRIVATE/'evaluation-oracle.json').write_text(json.dumps({'calibration_ids':list(map(int,calibration_ids)),
        'holdout_ids':list(map(int,holdout_ids)),'private_database':str(db_path),'threshold':threshold,'margin':gap},indent=2)+'\n')
    suitable=bool(test_result['link_precision'] is not None and test_result['link_precision']>=.99
                  and test_result['known_correct_link_coverage']>=.5 and test_result['unknown_false_accept_rate']<=.01)
    result={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL Ubuntu CPU',
        'dataset':'Celeb-reID-light official test query/gallery','identities':100,'query_images':len(ql),'gallery_images':len(gl),
        'no_model_training_performed':True,'inference_receives_ground_truth_identity':False,
        'pretrained_model':model_info['name'],'checkpoint_sha256':model_info['expected_checkpoint_sha256'],
        'encoding':timing,'closed_set':{'identity_top1_accuracy':float((closed['predicted']==ql).mean()),
        'image_top5_hit_rate':float(matches[:,:5].any(axis=1).mean()),'image_mean_average_precision':float(average_precision.mean())},
        'protocol':{'seed':'assessment02-identity-split-v1','calibration_identities':40,'holdout_identities':60,
                    'calibration_registered':30,'calibration_unknown':10,'holdout_registered':45,'holdout_unknown':15,
                    'calibration_target_link_precision':.99,'calibration_target_unknown_false_accept_rate':.01,
                    'minimum_holdout_correct_link_coverage_for_experimental_gate':.5,
                    'threshold_selected_without_holdout_labels':True,'similarity_threshold':threshold,'margin_threshold':gap},
        'calibration':cal_result,'holdout':test_result,
        'isolated_database':{'rows_after_first_import':first,'rows_after_duplicate_replay':second,
                    'foreign_keys_valid':True,'automatic_matches_stored_as_candidates':True,
                    'contains_real_capture_dates':False,'counting_unit':'independent query photos, not real visits',
                    'production_django_integration_tested':False},
        'pipeline_executed':True,'experimental_auto_link_gate_pass':suitable,
        'real_cross_day_visit_accuracy_measured':False,'rag_tested':False,'production_deployed':False,
        'source_sha256':{'tools/evaluate_identity_samples.py':sha(ROOT/'tools/evaluate_identity_samples.py')}}
    (PUBLIC/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
