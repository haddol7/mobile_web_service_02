"""Independent WSL HTTP checks for the post created through the real web UI."""
import hashlib
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[2]
evidence = root / 'evidence/mobile-web'
base = 'http://127.0.0.1:8000'
post_id = 61
phase = sys.argv[1]
def get(path):
    with urllib.request.urlopen(base + path, timeout=20) as response:
        return response.read()
def data(path):
    return json.loads(get(path))
content = data(f'/api/v1/posts/{post_id}/content/')
post = data(f'/api_root/Post/{post_id}/')
image_url = urllib.parse.urlsplit(post['image'])
assert image_url.hostname in ('127.0.0.1', 'localhost')
image = get(image_url.path)
sha = hashlib.sha256(image).hexdigest()
assert content['image_sha256'] == sha
assert Image.open(io.BytesIO(image)).size == (1600, 1200)
assert content['theme'] == 'food' and content['theme_origin'] == 'user'
assert [t['display'] for t in content['tags']] == ['후기', '모바일검증']
assert set(content['model_versions']) == {'face', 'label', 'ocr_ko', 'ocr_latin'}
assert content['mapping_version'] == 'web_imagenet_v2'
original = root.parent / '.local/web-composite.jpg'
assert sha != hashlib.sha256(original.read_bytes()).hexdigest()
lines = [line['text'] for line in content['lines']]
assert '바다라멘 모바일교정' in lines and 'CAFE MENU' in lines
query = '/api/v1/photo-text-search/?q=' + urllib.parse.quote('SUNSET')
matches = data(query)
ids = [item['post']['id'] for item in matches['results']]
if phase == 'initial':
    assert content['revision'] == 1 and len(lines) == 3
    assert 'SUNSET 100' in lines and post_id in ids
    (evidence / 'web-uploaded-photo.jpg').write_bytes(image)
elif phase == 'excluded':
    before = json.loads((evidence / 'http-initial.json').read_text())
    assert content['revision'] == 2 and len(lines) == 2
    assert 'SUNSET 100' not in lines and post_id not in ids
    assert before['image_sha256'] == sha, 'Metadata-only edit must retain exact photo bytes'
else:
    raise ValueError(phase)
record = {'environment':'WSL Ubuntu; live Django HTTP', 'phase':phase, 'pass':True,
          'post_id':post_id,'image_bytes':len(image),'image_sha256':sha,
          'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
          'content':content,'sunset_search_post_ids':ids}
(evidence / f'http-{phase}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'phase':phase,'pass':True,'revision':content['revision'],'lines':len(lines),'bytes':len(image)}))
