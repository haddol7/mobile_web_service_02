"""One-use encrypted credential handoff; run only from the WSL project venv.

PythonAnywhere's existing API_TOKEN is encrypted by OpenSSL RSA-OAEP SHA256
inside its Bash console. Only ciphertext is returned through the conversation.
Private keys and accepted tokens stay in a mode-0700 WSL home directory.
This authenticates the API; it does not transfer a browser session or deploy.
"""
import argparse
import base64
import datetime as dt
import json
import getpass
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOSTS = {'www.pythonanywhere.com', 'eu.pythonanywhere.com'}
PREFIX = 'PA-AUTH1:'
TTL = 1800
DEFAULT_DIR = Path.home() / '.config/mobile-web-service/pythonanywhere'


class AuthError(Exception):
    pass


def secure_directory(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise AuthError('인증 디렉터리의 심볼릭 링크는 허용하지 않습니다.')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise AuthError('인증 디렉터리는 본인 소유의 0700 권한이어야 합니다.')
    return directory


def private_write(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)


def private_read(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise AuthError('비공개 인증 파일을 읽을 수 없습니다.') from None
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise AuthError('인증 파일은 본인 소유의 0600 권한이어야 합니다.')
        raw = stream.read(8193)
    if len(raw) > 8192:
        raise AuthError('인증 파일의 크기가 올바르지 않습니다.')
    return raw


def openssl(arguments, data=None):
    result = subprocess.run(['openssl', *arguments], input=data, capture_output=True, check=False)
    if result.returncode:
        # Do not echo process stderr or payloads into transcript/logs.
        raise AuthError('암호화 인증 처리를 완료하지 못했습니다.')
    return result.stdout


def phone_command(public_key, nonce, host):
    encoded = base64.b64encode(public_key).decode('ascii')
    # The key and nonce are public. API_TOKEN is read only inside PA's console,
    # never placed in command history, command-line arguments or printed text.
    code = ';'.join([
        'import os,json,time,base64,tempfile,pathlib,subprocess,sys,getpass',
        'k=os.environ.get("API_TOKEN","")',
        '(k and len(k)<=128) or sys.exit("Create an API token, then start a NEW Bash console.")',
        f'p=json.dumps(dict(v=1,u=getpass.getuser(),h={host!r},t=int(time.time()),n={nonce!r},k=k),separators=(",",":")).encode()',
        'len(p)<=446 or sys.exit("Authentication payload is too large.")',
        'd=tempfile.TemporaryDirectory()',
        'f=pathlib.Path(d.name)/"public.pem"',
        f'f.write_bytes(base64.b64decode({encoded!r}))',
        'r=subprocess.run(["openssl","pkeyutl","-encrypt","-pubin","-inkey",str(f),"-pkeyopt","rsa_padding_mode:oaep","-pkeyopt","rsa_oaep_md:sha256"],input=p,capture_output=True)',
        'd.cleanup()',
        'r.returncode==0 or sys.exit("Encryption failed; no credential was printed.")',
        f'print({PREFIX!r}+base64.b64encode(r.stdout).decode())',
    ])
    return 'python3 -c ' + shlex.quote(code)


def initialize(directory=DEFAULT_DIR, host='www.pythonanywhere.com'):
    if host not in HOSTS:
        raise AuthError('공식 PythonAnywhere 호스트만 허용합니다.')
    directory = secure_directory(directory)
    if any((directory / name).exists() for name in ('pending.json', 'pairing-private.pem', 'auth.json')):
        raise AuthError('기존 인증·연결 요청이 있습니다. 덮어쓰지 않았습니다.')
    private_key = openssl(['genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:4096'])
    private_write(directory / 'pairing-private.pem', private_key)
    public_key = openssl(['pkey', '-pubout', '-in', str(directory / 'pairing-private.pem')])
    now = int(time.time())
    pending = {'version': 1, 'nonce': secrets.token_hex(16), 'host': host, 'created': now, 'expires': now + TTL}
    private_write(directory / 'pending.json', json.dumps(pending).encode())
    return {'expires_utc': dt.datetime.fromtimestamp(now + TTL, dt.timezone.utc).isoformat(),
            'command': phone_command(public_key, pending['nonce'], host)}


def decrypt_handoff(text, directory=DEFAULT_DIR, now=None):
    directory = secure_directory(directory)
    pending = json.loads(private_read(directory / 'pending.json'))
    private_read(directory / 'pairing-private.pem')
    now = int(time.time()) if now is None else now
    if now > pending['expires']:
        raise AuthError('연결 요청이 만료됐습니다. 새 요청이 필요합니다.')
    text = text.strip()
    if not text.startswith(PREFIX) or len(text) > 1024:
        raise AuthError('PA-AUTH1:으로 시작하는 암호화된 인증 문자열만 받습니다.')
    try:
        cipher = base64.b64decode(text[len(PREFIX):], validate=True)
        if len(cipher) != 512:
            raise ValueError()
        raw = openssl(['pkeyutl', '-decrypt', '-inkey', str(directory / 'pairing-private.pem'),
                       '-pkeyopt', 'rsa_padding_mode:oaep', '-pkeyopt', 'rsa_oaep_md:sha256'], cipher)
        packet = json.loads(raw)
    except (ValueError, UnicodeError, AuthError):
        raise AuthError('인증 문자열의 복호화·형식을 확인하지 못했습니다.') from None
    if not isinstance(packet, dict) or set(packet) != {'v', 'u', 'h', 't', 'n', 'k'}:
        raise AuthError('인증 정보 형식이 올바르지 않습니다.')
    if packet['v'] != 1 or packet['h'] != pending['host'] or packet['h'] not in HOSTS or packet['n'] != pending['nonce']:
        raise AuthError('이 작업의 연결 요청과 일치하지 않습니다.')
    if type(packet['t']) is not int or not pending['created'] - 120 <= packet['t'] <= now + 120:
        raise AuthError('인증 정보 생성 시각이 올바르지 않습니다.')
    if not isinstance(packet['u'], str) or not re.fullmatch(r'[A-Za-z0-9_]{1,30}', packet['u']):
        raise AuthError('계정 이름 형식이 올바르지 않습니다.')
    if not isinstance(packet['k'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}', packet['k']):
        raise AuthError('인증 토큰 형식이 올바르지 않습니다.')
    return {'username': packet['u'], 'host': packet['h'], 'token': packet['k']}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def metadata(credentials, resource):
    if resource not in {'cpu', 'webapps', 'system_image'} or credentials['host'] not in HOSTS:
        raise AuthError('허용하지 않은 API 요청입니다.')
    username = credentials['username']
    if not re.fullmatch(r'[A-Za-z0-9_]{1,30}', username):
        raise AuthError('계정 이름 형식이 올바르지 않습니다.')
    request = urllib.request.Request(
        f"https://{credentials['host']}/api/v0/user/{username}/{resource}/",
        headers={'Authorization': 'Token ' + credentials['token'], 'Accept': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as response:
            raw = response.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise ValueError()
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise AuthError(f'공식 API 인증 확인 실패: HTTP {error.code}. 토큰과 응답 본문은 출력하지 않았습니다.') from None
    except (urllib.error.URLError, ValueError, OSError):
        raise AuthError('공식 API 인증 확인에 실패했습니다. 응답 본문과 토큰은 출력하지 않았습니다.') from None


def accept(text, directory=DEFAULT_DIR):
    credentials = decrypt_handoff(text, directory)
    metadata(credentials, 'cpu')  # Confirm credentials before storing them.
    directory = secure_directory(directory)
    private_write(directory / 'auth.json', json.dumps(credentials).encode())
    (directory / 'pending.json').unlink()
    (directory / 'pairing-private.pem').unlink()
    return {'authenticated': True, 'username': credentials['username'], 'host': credentials['host'],
            'browser_session_created': False, 'deployment_changed': False}


def load_credentials(directory=DEFAULT_DIR):
    directory = secure_directory(directory)
    return json.loads(private_read(directory / 'auth.json'))


def connect(username, host, directory=DEFAULT_DIR, local_pipe=False):
    directory = secure_directory(directory)
    if (directory / 'auth.json').exists():
        raise AuthError('이미 연결되어 있습니다. 기존 인증은 변경하지 않았습니다.')
    if host not in HOSTS or not re.fullmatch(r'[A-Za-z0-9_]{1,30}', username):
        raise AuthError('계정 또는 API 호스트가 올바르지 않습니다.')
    if not local_pipe and not sys.stdin.isatty():
        raise AuthError('토큰은 로컬 대화형 터미널에서만 입력할 수 있습니다.')
    raw_token = sys.stdin.read(4098) if local_pipe else getpass.getpass('PythonAnywhere API token (hidden): ')
    # Windows PowerShell 5/.NET StreamWriter emits a UTF-8 preamble on stdin.
    token = raw_token.removeprefix('\ufeff').strip()
    if token.startswith('Token '):
        token = token[6:].strip()
    # Treat the service credential as opaque. Its validity belongs to the API,
    # not an assumed token alphabet/length from an older service version.
    if not token:
        raise AuthError('입력창에서 빈 값이 전달됐습니다. 붙여넣은 후 Connect를 눌러주세요.')
    if len(token) > 4096:
        raise AuthError('토큰 값 대신 너무 긴 내용이 입력됐습니다.')
    if any(ord(char) < 33 or ord(char) > 126 for char in token):
        raise AuthError('입력값에 공백 또는 제어문자가 있습니다. API 토큰 값만 복사해주세요.')
    credentials = dict(username=username, host=host, token=token)
    metadata(credentials, 'cpu')
    private_write(directory / 'auth.json', json.dumps(credentials).encode())
    status_path = directory / 'last-connection.json'
    if status_path.exists():
        private_read(status_path)
        status_path.unlink()
    private_write(status_path, json.dumps({'connected': True, 'time': time.time()}).encode())
    return {'authenticated': True, 'username': username, 'host': host,
            'deployment_changed': False}


def renew(directory=DEFAULT_DIR):
    directory = secure_directory(directory)
    if (directory / 'auth.json').exists():
        raise AuthError('이미 연결된 계정 인증은 변경하지 않았습니다.')
    pending = json.loads(private_read(directory / 'pending.json'))
    if time.time() <= pending['expires']:
        raise AuthError('현재 연결 요청이 유효합니다. 기존 명령을 사용해주세요.')
    private_read(directory / 'pairing-private.pem')
    (directory / 'pending.json').unlink()
    (directory / 'pairing-private.pem').unlink()
    return initialize(directory, pending['host'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'renew', 'accept', 'status', 'check', 'connect'])
    parser.add_argument('--username', default='daejinha')
    parser.add_argument('--local-ui-pipe', action='store_true', help='Private stdin from the local masked credential dialog')
    parser.add_argument('--host', choices=sorted(HOSTS), default='www.pythonanywhere.com')
    args = parser.parse_args()
    if not sys.platform.startswith('linux') or not os.environ.get('WSL_DISTRO_NAME'):
        raise AuthError('Windows 소스를 WSL Ubuntu의 프로젝트 가상환경에서 실행해주세요.')
    if args.action == 'connect':
        result = connect(args.username, args.host, local_pipe=args.local_ui_pipe)
    elif args.action == 'init':
        result = initialize(host=args.host)
    elif args.action == 'renew':
        result = renew()
    elif args.action == 'accept':
        result = accept(sys.stdin.read(1025))
    elif args.action == 'status':
        result = {'authenticated': (DEFAULT_DIR / 'auth.json').is_file(),
                  'pending': (DEFAULT_DIR / 'pending.json').is_file()}
    else:
        credentials = load_credentials()
        apps = metadata(credentials, 'webapps')
        result = {'authenticated': True, 'username': credentials['username'], 'host': credentials['host'],
                  'webapps': [{'domain_name': app.get('domain_name'), 'python_version': app.get('python_version')}
                              for app in apps], 'deployment_changed': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (AuthError, FileExistsError) as error:
        if '--local-ui-pipe' in sys.argv:
            directory = secure_directory(DEFAULT_DIR)
            status_path = directory / 'last-connection.json'
            if status_path.exists():
                private_read(status_path)
                status_path.unlink()
            private_write(status_path, json.dumps({'connected': False, 'time': time.time(), 'error': str(error)
                if isinstance(error, AuthError) else 'Existing credentials were not overwritten.'}, ensure_ascii=False).encode())
        print(str(error) if isinstance(error, AuthError) else '기존 인증 파일을 덮어쓰지 않았습니다.', file=sys.stderr)
        sys.exit(1)
