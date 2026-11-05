"""Read-only assessment 02 compatibility review. Does not stage or activate a release."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pythonanywhere_auth as auth
from pythonanywhere_deploy import API, BASE, DOMAIN, SERVER, WORKSPACE

credentials = auth.load_credentials()
api = API(credentials)
state = json.loads(api.file(BASE + '/active.json'))
source = state['source']
paths = ['blog/models.py', 'blog/services.py', 'blog/serializers.py', 'blog/permissions.py',
         'blog/ownership.py', 'blog/views.py', 'blog/api_v1.py', 'blog/api_v1_urls.py', 'blog/urls.py',
         'photoblog/urls.py', 'requirements.txt']
paths += [path.relative_to(SERVER).as_posix() for path in sorted((SERVER / 'blog/migrations').glob('*.py'))]

def compare(relative):
    remote = API(credentials).file(source + '/' + relative, missing_ok=True)
    local = (SERVER / relative).read_bytes()
    return {'path': relative, 'identical': remote == local, 'local_sha256': hashlib.sha256(local).hexdigest(),
            'remote_sha256': hashlib.sha256(remote).hexdigest() if remote is not None else None}

with ThreadPoolExecutor(max_workers=4) as pool:
    rows = list(pool.map(compare, paths))
result = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True, 'domain': DOMAIN,
          'current_source': source, 'candidate_source': str(SERVER), 'comparisons': rows,
          'migrations_identical': all(row['identical'] for row in rows if '/migrations/' in row['path']),
          'requirements_identical': next(row['identical'] for row in rows if row['path'] == 'requirements.txt'),
          'proposed_storage': {'database': BASE + '/shared/db.sqlite3', 'media': state['media'], 'preserve': True},
          'proposed_activation': 'Use an immutable release of assessment 02 source in the existing webapp after approval. Keep existing shared DB and media. Back up DB and WSGI, verify migrations and original image hashes, then switch source and reload. Restore routing if public verification fails.',
          'production_changed': False, 'approval_required': True}
destination = WORKSPACE / 'docs/deployment-preflight.json'
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'read_only': True, 'compared': len(rows), 'differences': [row['path'] for row in rows if not row['identical']],
                  'migrations_identical': result['migrations_identical'], 'requirements_identical': result['requirements_identical'],
                  'production_changed': False}, indent=2))
