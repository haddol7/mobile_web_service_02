"""WSL-only verified deployment through the official PythonAnywhere API.

No browser cookies, passwords or manual uploads. Authentication is provisioned
separately using pythonanywhere_auth.py connect in a user-controlled terminal.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pythonanywhere_auth as auth

WORKSPACE = Path(__file__).resolve().parents[2]
SERVER = WORKSPACE / 'PhotoBlogServer'
DOMAIN = 'daejinha.pythonanywhere.com'
HOME = '/home/daejinha'
WSGI = '/var/www/daejinha_pythonanywhere_com_wsgi.py'
# Keep the existing shared production database/media and recovery history.
# Assessment 02 source is packaged from this repository into a new immutable release.
# The user explicitly approved this transition on 2026-11-05 after reviewing preflight.py.
BASE = HOME + '/common01-auto'
NODE = '/mnt/c/Users/1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'


class DeploymentError(Exception):
    pass


_next_request_at = 0.0


def wait_request_slot():
    """Space API and website verification requests to avoid bursts from this PC."""
    global _next_request_at
    time.sleep(max(0, _next_request_at - time.monotonic()))
    _next_request_at = time.monotonic() + 5


class API:
    def __init__(self, credentials):
        if credentials['host'] not in auth.HOSTS or not re.fullmatch(r'[A-Za-z0-9_]{1,30}', credentials['username']):
            raise DeploymentError('Invalid API account')
        if credentials['username'] != 'daejinha':
            raise DeploymentError('This pipeline is configured for daejinha only')
        self.credentials = credentials
        self.prefix = 'https://' + credentials['host'] + '/api/v0/user/' + credentials['username']
        self.opener = urllib.request.build_opener(auth.NoRedirect())

    def request(self, method, endpoint, data=None, content_type=None, raw=False, missing_ok=False):
        if not endpoint.startswith('/') or endpoint.startswith('//') or '\\' in endpoint or '#' in endpoint:
            raise DeploymentError('Invalid API endpoint')
        headers = {'Authorization': 'Token ' + self.credentials['token']}
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
            content_type = 'application/x-www-form-urlencoded'
        if content_type:
            headers['Content-Type'] = content_type
        request = urllib.request.Request(self.prefix + endpoint, data=data, headers=headers, method=method)
        try:
            wait_request_slot()
            with self.opener.open(request, timeout=90) as response:
                value = response.read(100 * 1024**2 + 1)
            if len(value) > 100 * 1024**2:
                raise DeploymentError('API response too large')
            return value if raw else (json.loads(value) if value else None)
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            raise DeploymentError(f'API {method} failed: HTTP {error.code}. Response body withheld.') from None
        except (urllib.error.URLError, ValueError, OSError):
            raise DeploymentError(f'API {method} failed; credentials and response body withheld.') from None

    def file(self, path, content=None, missing_ok=False):
        if not path.startswith((HOME + '/', '/var/www/daejinha_pythonanywhere_com_wsgi.py')) or '..' in path.split('/'):
            raise DeploymentError('File path outside deployment scope')
        endpoint = '/files/path' + urllib.parse.quote(path, safe='/')
        if content is None:
            return self.request('GET', endpoint, raw=True, missing_ok=missing_ok)
        boundary = 'common01' + secrets.token_hex(20)
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="content"; filename="upload"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        return self.request('POST', endpoint, body, 'multipart/form-data; boundary=' + boundary)


def build_package():
    rows = []
    paths = [SERVER / name for name in ('manage.py', 'api_test_engine.py', 'requirements.txt', '.coveragerc')]
    for directory in ('blog', 'photoblog', 'deploy', 'tools'):
        paths.extend(path for path in (SERVER / directory).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc', '.pyo'})
    output = WORKSPACE / 'dist'
    output.mkdir(exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S') + secrets.token_hex(3)
    package = output / ('pythonanywhere-auto-' + stamp + '.zip')
    with zipfile.ZipFile(package, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            relative = path.relative_to(SERVER).as_posix()
            if path.is_symlink() or set(Path(relative).parts) & {'media', 'private', 'node_modules', 'htmlcov', 'db.sqlite3'}:
                raise DeploymentError('Private or runtime file in package')
            value = path.read_bytes()
            archive.writestr('PhotoBlogServer/' + relative, value)
            rows.append(dict(path=relative, bytes=len(value), sha256=hashlib.sha256(value).hexdigest()))
    manifest = dict(sha256=hashlib.sha256(package.read_bytes()).hexdigest(), files=rows)
    manifest_path = package.with_suffix('.json')
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return stamp, package, manifest_path, manifest


def assert_source_unchanged(manifest):
    for row in manifest['files']:
        if hashlib.sha256((SERVER / row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise DeploymentError('Source changed during verification; rebuild required')


def verify():
    verify_frontend()
    subprocess.run([sys.executable, 'tools/verify_content.py'], cwd=SERVER, check=True)


def verify_frontend():
    record = json.loads((WORKSPACE / 'evidence/mobile-web/unit-verification.json').read_text())
    finished = dt.datetime.fromisoformat(record['finished_utc'].replace('Z', '+00:00'))
    age = (dt.datetime.now(dt.timezone.utc) - finished).total_seconds()
    if not record.get('pass') or not record.get('source_stable') or record.get('exit_code') != 0 or not -30 <= age <= 900:
        raise DeploymentError('Run tools/verify-mobile-web.mjs to refresh Windows web verification')
    actual = {}
    common = WORKSPACE
    for directory in ('web-tests', 'PhotoBlogServer/blog/static/blog', 'PhotoBlogServer/blog/templates'):
        for path in (common / directory).rglob('*'):
            if path.is_file():
                actual[path.relative_to(common).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != record['source_sha256']:
        raise DeploymentError('Browser source differs from the verified Windows test run')


def wait_ready(api, console):
    marker = 'COMMON01READY' + secrets.token_hex(12)
    api.request('POST', f'/consoles/{console}/send_input/', {'input': "printf '\\n%s\\n' " + shlex.quote(marker) + '\n'})
    for _ in range(12):
        time.sleep(3)
        result = api.request('GET', f'/consoles/{console}/get_latest_output/')
        if marker in str(result.get('output', '')).replace('\r', '').splitlines():
            return
    raise DeploymentError('Bash console is not ready. Open the existing deployment Bash console once; no upload is needed.')


def wait_stage(api, result_path):
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        time.sleep(5)
        raw = api.file(result_path, missing_ok=True)
        if raw:
            result = json.loads(raw)
            if result.get('phase') != 'staged':
                raise DeploymentError('Remote staging failed. Existing WSGI was not switched; inspect private job logs.')
            return result
    raise DeploymentError('Staging timeout. Inspect remote job before retrying; activation was not performed.')


def smoke(state, manifest):
    opener = urllib.request.build_opener(auth.NoRedirect())
    asset = next(row for row in manifest['files'] if row['path'].endswith('/content/composer.mjs'))
    probes = [('/', None), ('/accounts/login/', None), ('/api_root/Post/', None),
              ('/static/' + asset['path'].split('/static/', 1)[1], asset['sha256'])]
    results = []
    for path, expected in probes:
        with opener.open('https://' + DOMAIN + path, timeout=40) as response:
            value = response.read(10 * 1024**2)
            if response.status != 200:
                raise DeploymentError('Public URL verification failed')
        if expected and hashlib.sha256(value).hexdigest() != expected:
            raise DeploymentError('Deployed asset does not match release')
        results.append(dict(path=path, status=200, sha256=hashlib.sha256(value).hexdigest()))
    return results


def set_mappings(api, desired):
    endpoint = f'/webapps/{DOMAIN}/static_files/'
    current = api.request('GET', endpoint)
    for url, path in desired.items():
        matching = [row for row in current if row['url'] == url]
        if len(matching) > 1:
            raise DeploymentError('Duplicate static mapping; inspect before activation')
        if matching:
            api.request('PATCH', endpoint + str(matching[0]['id']) + '/', {'path': path})
        else:
            api.request('POST', endpoint, {'url': url, 'path': path})


def activate(api, state, manifest, snapshot_dir):
    endpoint = f'/webapps/{DOMAIN}/'
    previous = api.request('GET', endpoint)
    mappings = api.request('GET', endpoint + 'static_files/')
    old_wsgi = api.file(WSGI)
    if hashlib.sha256(old_wsgi).hexdigest() != state['previous_wsgi_sha256']:
        raise DeploymentError('Live WSGI changed after backup; activation stopped')
    auth.private_write(snapshot_dir / 'previous-webapp.json', json.dumps(previous).encode())
    auth.private_write(snapshot_dir / 'previous-mappings.json', json.dumps(mappings).encode())
    auth.private_write(snapshot_dir / 'previous-wsgi.py', old_wsgi)
    try:
        candidate = api.file(state['candidate_wsgi'])
        api.file(WSGI, candidate)
        api.request('PATCH', endpoint, {'source_directory': state['source'], 'virtualenv_path': state['virtualenv'], 'force_https': 'true'})
        set_mappings(api, {'/static/': state['static'], '/media/': state['media']})
        api.request('POST', endpoint + 'reload/', {})
        last = None
        for attempt in range(6):
            time.sleep(5)
            try:
                probes = smoke(state, manifest)
                break
            except (OSError, DeploymentError) as error:
                last = error
        else:
            raise DeploymentError('Public URL verification failed after reload') from last
    except Exception as activation_error:
        failure = dict(error_type=type(activation_error).__name__)
        if isinstance(activation_error, DeploymentError):
            failure['reason'] = str(activation_error)
        if isinstance(activation_error, urllib.error.HTTPError):
            failure['http_status'] = activation_error.code
        auth.private_write(snapshot_dir / 'activation-failure.json', json.dumps(failure).encode())
        # Restore routing/code only. Never revert the shared DB and lose new posts.
        try:
            api.file(WSGI, old_wsgi)
            fields = {key: previous[key] for key in ('source_directory', 'virtualenv_path', 'force_https') if key in previous}
            api.request('PATCH', endpoint, fields)
            mapping_endpoint = endpoint + 'static_files/'
            old_urls = {row['url'] for row in mappings}
            for row in api.request('GET', mapping_endpoint):
                if row['url'] in {'/static/', '/media/'} and row['url'] not in old_urls:
                    api.request('DELETE', mapping_endpoint + str(row['id']) + '/')
            set_mappings(api, {row['url']: row['path'] for row in mappings if row['url'] in {'/static/', '/media/'}})
            api.request('POST', endpoint + 'reload/', {})
        except Exception:
            raise DeploymentError('Activation failed and routing recovery failed. Private snapshots are available; agent intervention required.') from None
        raise DeploymentError('Activation failed (' + json.dumps(failure) + '); previous routing/WSGI restored. Database backup retained; schema compatibility needs inspection.') from None
    committed = dict(state, phase='verified', public_probes=probes)
    # Keep one previous release pointer without recursively growing state files.
    if committed.get('previous'):
        committed['previous'] = {key: committed['previous'][key] for key in
                                 ('source', 'release', 'virtualenv', 'backup')}
    api.file(BASE + '/active.json', json.dumps(committed).encode())
    auth.private_write(snapshot_dir / 'result.json', json.dumps(committed, indent=2).encode())
    return dict(phase='verified', url='https://' + DOMAIN, release=state['release'], probes=probes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--console', type=int, default=48736170)
    parser.add_argument('--check-auth', action='store_true')
    parser.add_argument('--prepare-only', action='store_true', help='Run local verification and package without any API action')
    parser.add_argument('--resume', help='Activate an already staged, source-matching release after inspecting a failure')
    args = parser.parse_args()
    if not sys.platform.startswith('linux') or not os.environ.get('WSL_DISTRO_NAME'):
        raise DeploymentError('Run in the WSL Ubuntu project virtualenv')
    if args.prepare_only:
        release_id, package, manifest_path, manifest = build_package()
        verify()
        assert_source_unchanged(manifest)
        print(json.dumps(dict(phase='locally_verified', package=package.name, files=len(manifest['files']), cloud_deployed=False)))
        return
    credentials = auth.load_credentials()
    api = API(credentials)
    api.request('GET', '/cpu/')
    if args.check_auth:
        print(json.dumps(dict(authenticated=True, username=credentials['username'])))
        return
    lock = (auth.DEFAULT_DIR / 'deployment.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise DeploymentError('A deployment is already running; no second job was started') from None
    wait_ready(api, args.console)
    if args.resume:
        if not re.fullmatch(r'[0-9]{14}[0-9a-f]{6}', args.resume):
            raise DeploymentError('Invalid staged release identifier')
        manifest_path = WORKSPACE / 'dist' / ('pythonanywhere-auto-' + args.resume + '.json')
        manifest = json.loads(manifest_path.read_text())
        assert_source_unchanged(manifest)
        verify_frontend()
        state = wait_stage(api, HOME + '/common01-job-' + args.resume + '.result.json')
        if state['package_sha256'] != manifest['sha256']:
            raise DeploymentError('Staged release does not match local verified package')
        snapshot_dir = auth.secure_directory(auth.DEFAULT_DIR / 'deployments' / (args.resume + '-resume-' + secrets.token_hex(4)))
        print(json.dumps(activate(api, state, manifest, snapshot_dir), indent=2))
        return
    # Capture source before tests, then ensure exactly those files are packaged.
    release_id, package, manifest_path, manifest = build_package()
    verify()
    assert_source_unchanged(manifest)
    snapshot_dir = auth.secure_directory(auth.DEFAULT_DIR / 'deployments' / release_id)
    worker = Path(__file__).with_name('pythonanywhere_remote.py')
    remote_worker = HOME + '/common01-auto-worker-' + release_id + '.py'
    job_path = HOME + '/common01-job-' + release_id + '.json'
    result_path = job_path[:-5] + '.result.json'
    for path in (package, manifest_path):
        api.file(HOME + '/' + path.name, path.read_bytes())
    api.file(remote_worker, worker.read_bytes())
    job = dict(release=release_id, package=package.name, manifest=manifest_path.name, domain=DOMAIN)
    api.file(job_path, json.dumps(job).encode())
    command = 'umask 077; python3.13 ' + shlex.quote(remote_worker) + ' ' + shlex.quote(job_path)
    command += ' > ' + shlex.quote(HOME + '/common01-job-' + release_id + '.log') + ' 2>&1\n'
    api.request('POST', f'/consoles/{args.console}/send_input/', {'input': command})
    state = wait_stage(api, result_path)
    assert_source_unchanged(manifest)
    result = activate(api, state, manifest, snapshot_dir)
    # Uploaded source ZIPs are transient; verified local packages remain available.
    try:
        for path in (package, manifest_path):
            api.request('DELETE', '/files/path' + urllib.parse.quote(HOME + '/' + path.name, safe='/'))
        cleanup_command = 'umask 077; python3.13 ' + shlex.quote(remote_worker) + ' --cleanup\n'
        api.request('POST', f'/consoles/{args.console}/send_input/', {'input': cleanup_command})
    except DeploymentError:
        result['cleanup_pending'] = True
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (DeploymentError, auth.AuthError, OSError, subprocess.CalledProcessError) as error:
        print(str(error) if isinstance(error, (DeploymentError, auth.AuthError)) else
              'Deployment stopped. Authentication, local verification or a required file needs attention.', file=sys.stderr)
        sys.exit(1)
