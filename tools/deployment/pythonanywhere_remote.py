"""Deployment-only worker, executed in the account's PythonAnywhere Bash console.

Receives no API credentials. Immutable releases share production DB/media.
Staging never changes the existing WSGI; activation is a separate API step.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import tarfile
import time
import zipfile


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.next')
    with open(temporary, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
        json.dump(value, output, indent=2)
    temporary.replace(path)


def verify_package(package, manifest):
    if digest(package) != manifest['sha256']:
        raise ValueError('Package digest mismatch')
    expected = {'PhotoBlogServer/' + row['path']: row for row in manifest['files']}
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(expected) or set(names) != set(expected):
            raise ValueError('Package inventory mismatch')
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename:
                raise ValueError('Unsafe archive path')
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Archive symlink forbidden')
            row = expected[entry.filename]
            if entry.file_size != row['bytes'] or hashlib.sha256(archive.read(entry)).hexdigest() != row['sha256']:
                raise ValueError('Package entry digest mismatch')


def database_backup(source, target):
    with sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True) as database:
        with sqlite3.connect(target) as backup:
            database.backup(backup)
    target.chmod(0o600)


def inventory(database):
    with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as connection:
        return {'posts': list(connection.execute('SELECT id,image FROM blog_post ORDER BY id')),
                'users': connection.execute('SELECT COUNT(*) FROM auth_user').fetchone()[0]}


def stage(job):
    home = Path.home()
    if home != Path('/home/daejinha'):
        raise ValueError('Unexpected deployment account')
    base = home / 'common01-auto'
    base.mkdir(parents=True, mode=0o755, exist_ok=True)
    with (base / 'deploy.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stage_locked(job, home, base)


def stage_locked(job, home, base):
    package = home / job['package']
    manifest = json.loads((home / job['manifest']).read_text(encoding='utf-8-sig'))
    verify_package(package, manifest)
    release_id = job['release']
    if not release_id.isalnum() or len(release_id) > 48:
        raise ValueError('Invalid release identifier')
    release = base / 'releases' / release_id
    if release.exists():
        raise ValueError('Release already exists; inspect saved state')
    # Reserve room for source, venv and a consistent DB backup before making changes.
    state_path = base / 'active.json'
    previous = json.loads(state_path.read_text()) if state_path.exists() else None
    old = Path(previous['source']) if previous else home / 'mobile-web-service-project'
    required = sum(row['bytes'] for row in manifest['files']
                   if not previous or not (old / row['path']).is_file()
                   or digest(old / row['path']) != row['sha256']) + 100 * 1024**2
    if shutil.disk_usage(home).free < required:
        raise ValueError('Insufficient free disk space; existing site unchanged')
    (base / 'releases').mkdir(mode=0o755, exist_ok=True)
    release.mkdir(mode=0o755)
    private_base = home / '.local/share/common01-auto'
    private_base.mkdir(parents=True, mode=0o700, exist_ok=True)
    private_base.chmod(0o700)
    backup = private_base / release_id
    backup.mkdir(mode=0o700)
    wsgi = Path('/var/www/daejinha_pythonanywhere_com_wsgi.py')
    shutil.copy2(wsgi, backup / 'wsgi.py')
    (backup / 'wsgi.py').chmod(0o600)
    before = inventory(old / 'db.sqlite3')
    media_before = {}
    for _, name in before['posts']:
        if not name:
            continue
        photo = old / 'media' / name
        if not photo.resolve().is_relative_to((old / 'media').resolve()):
            raise ValueError('Photo path outside media root')
        media_before[name] = digest(photo)
    database_backup(old / 'db.sqlite3', backup / 'db.sqlite3')
    shared = base / 'shared'
    if not previous:
        # Full first-deployment recovery copy, including old media and source.
        with tarfile.open(backup / 'original-project.tar.gz', 'x:gz') as archive:
            archive.add(old, arcname=old.name)
        (backup / 'original-project.tar.gz').chmod(0o600)
        shared.mkdir(mode=0o755, exist_ok=False)
        shutil.copy2(backup / 'db.sqlite3', shared / 'db.sqlite3')
        shutil.copytree(old / 'media', shared / 'media')
    root = release / 'PhotoBlogServer'
    # Hardlink unchanged immutable assets across releases to fit the free quota.
    with zipfile.ZipFile(package) as archive:
        for row in manifest['files']:
            old_file, new_file = old / row['path'], root / row['path']
            new_file.parent.mkdir(parents=True, exist_ok=True)
            if previous and old_file.is_file() and digest(old_file) == row['sha256']:
                os.link(old_file, new_file)
            else:
                new_file.write_bytes(archive.read('PhotoBlogServer/' + row['path']))
    # The Bash job uses umask 077; nginx still needs ordinary public static paths.
    root.chmod(0o755)
    for path in root.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    (root / 'db.sqlite3').symlink_to(shared / 'db.sqlite3')
    (root / 'media').symlink_to(shared / 'media', target_is_directory=True)
    config = home / '.config/common01-auto/production.json'
    requirements_hash = digest(root / 'requirements.txt')[:16]
    venv = home / '.virtualenvs' / ('common01-' + requirements_hash)

    def run(name, command):
        log = backup / (name + '.log')
        with open(log, 'w', opener=lambda p, f: os.open(p, f, 0o600)) as output:
            subprocess.run(command, cwd=root, stdout=output, stderr=subprocess.STDOUT, check=True)

    if not venv.exists():
        run('venv', ['python3.13', '-m', 'venv', str(venv)])
    python = str(venv / 'bin/python')
    # A marker is written only after installation and pip check both succeed.
    installed = venv / 'common01-dependencies-ok'
    if not installed.exists():
        run('dependencies', [python, '-m', 'pip', 'install', '--no-cache-dir', '-r', str(root / 'requirements.txt')])
        run('pip-check', [python, '-m', 'pip', 'check'])
        installed.touch()
    if not config.exists():
        run('config', [python, 'deploy/create_private_config.py', '--config', str(config), '--host', job['domain']])
    manager = [python, 'deploy/manage_production.py', '--config', str(config)]
    run('check', [*manager, 'check', '--deploy'])
    run('migration-plan', [*manager, 'migrate', '--plan'])
    run('migrate', [*manager, 'migrate', '--noinput'])
    after = inventory(root / 'db.sqlite3')
    if not set(before['posts']).issubset(set(after['posts'])) or after['users'] < before['users']:
        raise ValueError('Existing data preservation check failed')
    for name, expected in media_before.items():
        if digest(root / 'media' / name) != expected:
            raise ValueError('Existing photo preservation check failed')
    run('static', [*manager, 'collectstatic', '--noinput'])
    (root / 'staticfiles').chmod(0o755)
    # Replace identical collected copies with hardlinks, preserving ordinary files for nginx.
    for path in (root / 'staticfiles').rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
        source = root / 'blog/static' / path.relative_to(root / 'staticfiles')
        if path.is_file() and source.is_file() and digest(path) == digest(source):
            path.unlink()
            os.link(source, path)
    candidate = ('from pathlib import Path\nimport sys\n'
                 f'PROJECT_ROOT = Path({str(root)!r})\nPRIVATE_CONFIG = Path({str(config)!r})\n'
                 'sys.path.insert(0, str(PROJECT_ROOT))\nfrom deploy.production import load_environment\n'
                 'load_environment(PRIVATE_CONFIG, PROJECT_ROOT)\n'
                 'from django.core.wsgi import get_wsgi_application\napplication = get_wsgi_application()\n')
    candidate_path = release / 'candidate_wsgi.py'
    candidate_path.write_text(candidate)
    candidate_path.chmod(0o600)
    run('wsgi-import', [python, '-c', f'import runpy; runpy.run_path({str(candidate_path)!r})'])
    return dict(phase='staged', source=str(root), virtualenv=str(venv), backup=str(backup),
                candidate_wsgi=str(candidate_path), previous_wsgi_sha256=digest(backup / 'wsgi.py'),
                package_sha256=manifest['sha256'], release=release_id,
                static=str(root / 'staticfiles'), media=str(shared / 'media'),
                previous=previous, staged_at=int(time.time()))


def cleanup(base=None, private_base=None):
    base = Path(base) if base else Path.home() / 'common01-auto'
    private_base = Path(private_base) if private_base else Path.home() / '.local/share/common01-auto'
    state = json.loads((base / 'active.json').read_text())
    if state.get('phase') != 'verified':
        raise ValueError('Cleanup requires a publicly verified deployment')
    keep = {state['release']}
    if state.get('previous'):
        keep.add(state['previous']['release'])
    removed = []
    for parent in (base / 'releases', private_base):
        for target in parent.iterdir():
            if not re.fullmatch(r'[0-9]{14}[0-9a-f]{6}', target.name) or target.name in keep:
                continue
            if target.is_symlink() or not target.is_dir() or not target.resolve().is_relative_to(parent.resolve()):
                raise ValueError('Unsafe cleanup target')
            # The original site's complete recovery archive is permanent.
            if (target / 'original-project.tar.gz').exists():
                continue
            shutil.rmtree(target)
            removed.append(target.name)
    return dict(phase='cleaned', removed=removed, retained=sorted(keep))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('job', nargs='?')
    parser.add_argument('--cleanup', action='store_true')
    args = parser.parse_args()
    if args.cleanup:
        print(json.dumps(cleanup()))
        return
    if not args.job:
        parser.error('job is required without --cleanup')
    job_path = Path(args.job)
    job = json.loads(job_path.read_text())
    result = job_path.with_suffix('.result.json')
    try:
        write_json(result, stage(job))
    except Exception as error:
        write_json(result, dict(phase='failed', error_type=type(error).__name__,
                                detail='Inspect private remote backup logs; no API credentials are present.'))
        raise


if __name__ == '__main__':
    main()
