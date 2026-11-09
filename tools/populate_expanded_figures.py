"""Add the expanded, actually analyzed sources through the existing protected API."""
from datetime import datetime,timezone
import json,os,sys
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/public-figure-expanded'

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    sys.path.insert(0,str(ROOT));from tools import populate_public_figure_demo as original
    original.OUT=OUT;data,entries=original.prepare()
    for person in ('public-trump','public-obama'):
        sources=[case['source_reference'] for case in data['cases'] if case['expected']==person]
        dates=[case['capture_day_as_published'] for case in data['cases'] if case['expected']==person]
        assert len(sources)==len(set(sources))==8 and len(set(dates))==8
    sys.path.insert(0,str(ROOT/'tools/deployment'));import pythonanywhere_auth as auth
    config=json.loads(auth.private_read(Path.home()/'.config/mobile-web-service/common02/edge-auth.json'))
    client=requests.Session();client.headers['Authorization']='Token '+config['token'];origin=config['base_url']
    def call(method,path,**kwargs):
        response=client.request(method,origin+path,timeout=(5,40),allow_redirects=False,**kwargs)
        assert response.status_code in (200,201),f'{path}: HTTP {response.status_code}'
        return response.json()
    posts=call('GET','/api_root/Post/');before=call('GET','/api/v1/history/overview/')['facts']
    created=0
    def send(entry):return call('POST','/api/v1/history/ingest/',data={'packet':json.dumps(entry['packet'],ensure_ascii=False)},
            files={'image':('observation.jpg',(OUT/(entry['id']+'.jpg')).read_bytes(),'image/jpeg')})
    for entry in entries:
        result=send(entry);assert result['id']==entry['id'];created+=result['created']
    replay=send(entries[0]);assert replay['created'] is False
    people=[]
    for person in ('public-trump','public-obama'):
        profile=call('GET','/api/v1/history/people/'+person+'/')
        assert profile['source_count']>=10 and profile['reference_available']
        expected={case['source_reference'] for case in data['cases'] if case['expected']==person}
        actual={card['source_reference'] for card in profile['timeline']};assert expected<=actual
        assert all(frame['observed_at'] is None for card in profile['timeline'] for frame in card['frames'])
        question=call('POST','/api/v1/history/ask/',json={'question':'어떤 영상에서 발견됐어?','profile':person,'date_basis':'processed','include_candidates':True})
        assert question['facts']['source_count']==profile['source_count']
        assert len({frame['source_reference'] for frame in question['evidence']})>=min(10,profile['source_count'])
        people.append({key:profile[key] for key in ('key','name','source_count','session_count','sampled_frames','confirmed_tracks','candidate_tracks','reference_available','detail_url')})
    assert call('GET','/api_root/Post/')==posts
    image=call('GET','/api/v1/history/frames/',params={'session':entries[0]['packet']['session']['id']})['results'][0]['image_url']
    response=requests.get(origin+image,timeout=(5,20),allow_redirects=False);assert response.status_code in (401,403)
    after=call('GET','/api/v1/history/overview/')['facts']
    proof={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL against PythonAnywhere','origin':origin,
           'pass':True,'production_verified':True,'new_original_sources':len(data['cases']),'observation_images':len(entries),
           'newly_created':created,'profiles':people,'previous_facts':before,'current_facts':after,
           'source_diverse_question_evidence_verified':True,'existing_posts_preserved':True,'duplicate_replay_created_new_frame':False,
           'anonymous_new_image_access_denied':True,'automatic_identity_confirmation':False,'capture_times_invented':False,
           'source_files_reuploaded_as_public_posts':False,'llm_called':False}
    (ROOT/'evidence/history/public-figure-expanded-cloud.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(proof,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
