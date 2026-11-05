"""Print only non-secret deployment state using the existing official API credential."""
import json
import pythonanywhere_auth as auth
from pythonanywhere_deploy import API, BASE, DOMAIN

api = API(auth.load_credentials())
webapp = api.request('GET', f'/webapps/{DOMAIN}/')
consoles = api.request('GET', '/consoles/')
state = json.loads(api.file(BASE + '/active.json'))
print(json.dumps({'domain': DOMAIN, 'source_directory': webapp.get('source_directory'),
                  'virtualenv_path': webapp.get('virtualenv_path'),
                  'consoles': [{'id': row['id'], 'executable': row.get('executable')} for row in consoles],
                  'active': {key: state.get(key) for key in ('phase', 'source', 'virtualenv', 'media', 'release')}}, indent=2))
