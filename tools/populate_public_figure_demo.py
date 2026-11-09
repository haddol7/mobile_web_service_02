"""Publish selected real model observations and portraits through the owner API."""
from datetime import datetime,timezone
from collections import Counter
import hashlib,json,os,sys
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
import cv2,requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-demo'

def prepare():
    data=json.loads((OUT/'inference.json').read_text());assert data['pass'];entries=[]
    for case in data['cases']:
        rows=[json.loads(line) for line in (ROOT/case['log']).read_text().splitlines()]
        def unique_expected_face(row):
            bound=Counter(f['body_track_id'] for f in row['faces'] if f['body_track_id'] is not None)
            return any(f['body_track_id'] is not None and bound[f['body_track_id']]==1 and f['candidate_profile_id']==case['expected'] for f in row['faces'])
        useful=[r for r in rows if unique_expected_face(r)
                and not any(f['candidate_profile_id'] is not None and f['candidate_profile_id']!=case['expected'] for f in r['faces'])]
        assert useful,'No verified candidate rows'
        selected={useful[round((len(useful)-1)*n/4)]['frame_index'] for n in range(5)}
        selected.add(max(useful,key=lambda r:max(f['similarity'] for f in r['faces'] if f['candidate_profile_id']==case['expected']))['frame_index'])
        session=uuid5(NAMESPACE_URL,'public-figure-demo-v1/'+case['sha256']).hex
        config={'id':session,'source_label':case['name'],'source_kind':'video','recording_started_at':None,
                'purpose':'demo','source_reference':case['source_reference'],
                'model_versions':{'yolov5':'7.0','face_model':'buffalo_l','face_policy':'candidate-2','demo_provenance':'Named public figure, genuine source video; no automatic identity confirmation'},
                'profiles':[{'id':p['id'],'name':p['name']} for p in data['profiles']]}
        capture=cv2.VideoCapture(str(ROOT/case['path']));fps=capture.get(cv2.CAP_PROP_FPS)
        for row in useful:
            if row['frame_index'] not in selected:continue
            capture.set(cv2.CAP_PROP_POS_FRAMES,round(row['video_seconds']*fps));ok,image=capture.read();assert ok
            ok,raw=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85]);assert ok
            key=hashlib.sha256(f'{session}:{row["frame_index"]}'.encode()).hexdigest();(OUT/(key+'.jpg')).write_bytes(raw.tobytes())
            frame={k:row[k] for k in ('frame_index','video_seconds','processed_at_utc','tracks','faces','crossings','image_size')};assert not frame['crossings'];frame['captured_at']=None
            entries.append({'id':key,'expected':case['expected'],'case':case['case'],'packet':{'schema_version':1,'session':config,'frame':frame,'post_id':None}})
        capture.release()
    # Serializer validation uses WSL settings, without connecting to or changing a database.
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','photoblog.settings');os.environ.setdefault('DJANGO_DEBUG','true')
    sys.path.insert(0,str(ROOT/'PhotoBlogServer'));import django;django.setup()
    from blog.history_serializers import PacketSerializer
    for entry in entries:
        form=PacketSerializer(data=entry['packet']);form.is_valid(raise_exception=True)
    (OUT/'packets.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n')
    return data,entries

def cloud(data,entries):
    sys.path.insert(0,str(ROOT/'tools/deployment'));import pythonanywhere_auth as auth
    app=json.loads(auth.private_read(Path.home()/'.config/mobile-web-service/common02/edge-auth.json'))
    client=requests.Session();client.headers['Authorization']='Token '+app['token'];origin=app['base_url']
    def call(method,path,**kwargs):
        response=client.request(method,origin+path,timeout=(5,30),allow_redirects=False,**kwargs)
        assert response.status_code in (200,201),f'{path}: HTTP {response.status_code}'
        return response.json()
    baseline=call('GET','/api_root/Post/');previous=call('GET','/api/v1/history/overview/')['facts']
    created=0
    for entry in entries:
        result=call('POST','/api/v1/history/ingest/',data={'packet':json.dumps(entry['packet'],ensure_ascii=False)},
                    files={'image':('observation.jpg',(OUT/(entry['id']+'.jpg')).read_bytes(),'image/jpeg')})
        assert result['id']==entry['id'];created+=result['created']
    people=[]
    for key in ('public-trump','public-obama'):
        profile=call('GET','/api/v1/history/people/'+key+'/')
        if not profile['reference_available']:
            call('POST','/api/v1/history/references/'+key+'/',files={'image':('portrait.jpg',(OUT/(key+'-portrait.jpg')).read_bytes(),'image/jpeg')})
        profile=call('GET','/api/v1/history/people/'+key+'/')
        assert profile['reference_available'] and profile['active'] and profile['candidate_tracks']>0
        assert profile['source_count']>=2
        assert all(f['observed_at'] is None for card in profile['timeline'] for f in card['frames'])
        question=call('POST','/api/v1/history/ask/',json={'question':'어떤 영상에서 발견됐어?','profile':key,'include_candidates':True,'date_basis':'processed'})
        assert question['facts']['source_count']==profile['source_count'] and len(question['evidence'])>=2
        people.append({k:profile[k] for k in ('key','name','source_count','session_count','sampled_frames','candidate_tracks','confirmed_tracks','reference_available','detail_url')})
    assert call('GET','/api_root/Post/')==baseline
    proof={'verified_utc':datetime.now(timezone.utc).isoformat(),'origin':origin,'production_verified':True,'pass':True,
           'real_observation_images':len(entries),'newly_created':created,'profiles':people,'previous_facts':previous,
           'current_facts':call('GET','/api/v1/history/overview/')['facts'],'existing_posts_preserved':True,
           'automatic_confirmation':False,'capture_times_not_invented':True,'record_questions_verified':True,'llm_called':False}
    (ROOT/'evidence/history/public-figure-cloud.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(proof,ensure_ascii=False),flush=True)

if __name__=='__main__':
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    data,entries=prepare();cloud(data,entries)
