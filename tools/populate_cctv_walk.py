"""Add selected genuine walking observations without assigning stranger identities."""
from datetime import datetime,timezone
import hashlib,json,os,sys
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
import cv2,requests

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/private/cctv-walking/chokepoint'

def main():
    assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
    info=json.loads((OUT/'inference.json').read_text());assert info['outer_archive_checksum_verified']
    rows=[json.loads(line) for line in (ROOT/info['log']).read_text().splitlines()]
    useful=[r for r in rows if any(f['body_track_id'] is not None for f in r['faces'])]
    selected={useful[round((len(useful)-1)*n/7)]['frame_index'] for n in range(8)}
    tracks={t['track_id'] for row in useful for t in row['tracks']}
    for track in tracks:
        matching=[row for row in useful if any(f['body_track_id']==track for f in row['faces'])]
        if matching:selected.add(max(matching,key=lambda row:max((f['bbox'][2]-f['bbox'][0])*(f['bbox'][3]-f['bbox'][1]) for f in row['faces'] if f['body_track_id']==track))['frame_index'])
    assert not any(f['candidate_profile_id'] for row in rows for f in row['faces'])
    session=uuid5(NAMESPACE_URL,'chokepoint-walk-v1/'+info['sha256']).hex
    references=json.loads((ROOT/'evidence/private/monitoring-showcase/v2/references.json').read_text())
    config={'id':session,'source_label':'출입 통로 / 정면 보행','source_kind':'video','recording_started_at':None,
            'model_versions':{'yolov5':'7.0','face_model':'buffalo_l','face_policy':'candidate-2','demo_provenance':'NICTA ChokePoint, Wong et al. CVPRW 2011; available-frame reconstruction'},
            'profiles':[{'id':p['id'],'name':p['name']} for p in references['profiles']],
            'purpose':'demo','source_reference':'ChokePoint/P1E_S1_C1/first1200-available-frames'}
    sys.path.insert(0,str(ROOT/'tools/deployment'));import pythonanywhere_auth as auth
    app=json.loads(auth.private_read(Path.home()/'.config/mobile-web-service/common02/edge-auth.json'))
    client=requests.Session();client.headers['Authorization']='Token '+app['token'];origin=app['base_url']
    def call(method,path,**kwargs):
        response=client.request(method,origin+path,timeout=(5,30),allow_redirects=False,**kwargs)
        assert response.status_code in (200,201),f'{path}: HTTP {response.status_code}'
        return response.json()
    baseline=call('GET','/api_root/Post/');count=0
    capture=cv2.VideoCapture(str(ROOT/info['path']))
    source_frames=sorted((OUT/'P1E_S1_C1').glob('*.jpg'));mapping=[]
    for row in useful:
        if row['frame_index'] not in selected:continue
        index=round(row['video_seconds']*30);capture.set(cv2.CAP_PROP_POS_FRAMES,index);ok,image=capture.read();assert ok
        ok,raw=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,85]);assert ok
        frame={key:row[key] for key in ('frame_index','video_seconds','processed_at_utc','tracks','faces','crossings','image_size')}
        assert not frame['crossings'];frame['captured_at']=None
        packet={'schema_version':1,'session':config,'frame':frame,'post_id':None}
        call('POST','/api/v1/history/ingest/',data={'packet':json.dumps(packet)},files={'image':('walking.jpg',raw.tobytes(),'image/jpeg')})
        mapping.append({'analyzed_frame_index':row['frame_index'],'derived_video_seconds':row['video_seconds'],'original_image':source_frames[index].name})
        count+=1
    capture.release();assert call('GET','/api_root/Post/')==baseline
    result=call('GET','/api/v1/history/sessions/',params={'date_basis':'processed','session':session})
    assert sum(row['sample_count'] for row in result['results'])==count
    assert all(f['observed_at'] is None and all(not t['confirmed'] and not t['candidate'] for t in f['tracks']) for row in result['results'] for f in row['frames'])
    proof={'verified_utc':datetime.now(timezone.utc).isoformat(),'origin':origin,'session':session,'actual_frames_added':count,
           'source':'https://arma.sourceforge.net/chokepoint/','source_camera':'P1E_S1_C1','source_credit':'NICTA; Wong, Chen, Mau, Sanderson, Lovell. CVPR Workshops 2011.',
           'derived_media_notice':'Reconstructed from the first 1200 available original images. Clip seconds are replay positions, not original capture times. JPEG compression applied.',
           'original_frame_mapping':mapping,'original_capture_date_unknown':True,'strangers_left_unassigned':True,'existing_public_posts_preserved':True,
           'dates':result['days'],'pass':True}
    (ROOT/'evidence/history/cctv-walking-cloud.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(proof,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
