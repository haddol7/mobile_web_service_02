import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import urllib.error
import zipfile

import pythonanywhere_auth as auth
import pythonanywhere_deploy as deploy
import pythonanywhere_remote as remote


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credentials = dict(username='daejinha', host='www.pythonanywhere.com', token='fake_' + 'x' * 40)

    def package(self, name='PhotoBlogServer/manage.py', data=b'example', expected=None):
        package = self.root / 'test.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr(name, data)
        row = dict(path=name.removeprefix('PhotoBlogServer/'), bytes=len(data),
                   sha256=expected or hashlib.sha256(data).hexdigest())
        return package, dict(sha256=remote.digest(package), files=[row])

    def test_verified_package(self):
        package, manifest = self.package()
        remote.verify_package(package, manifest)

    def test_tampered_entry(self):
        package, manifest = self.package(expected='0' * 64)
        with self.assertRaises(ValueError):
            remote.verify_package(package, manifest)

    def test_zip_slip(self):
        package, manifest = self.package('PhotoBlogServer/../../secret')
        with self.assertRaises(ValueError):
            remote.verify_package(package, manifest)

    def test_zip_duplicate_inventory(self):
        package, manifest = self.package()
        manifest['files'] = []
        with self.assertRaises(ValueError):
            remote.verify_package(package, manifest)

    def test_wrong_package_hash(self):
        package, manifest = self.package()
        manifest['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            remote.verify_package(package, manifest)

    def test_api_rejects_different_account_and_host(self):
        for override in [dict(username='someone'), dict(host='attacker.example')]:
            with self.assertRaises(deploy.DeploymentError):
                deploy.API(dict(self.credentials, **override))

    def test_api_token_header_and_multipart_contract(self):
        api = deploy.API(self.credentials)
        response = Mock()
        response.read.return_value = b'{"ok":true}'
        api.opener = Mock()
        api.opener.open.return_value.__enter__ = Mock(return_value=response)
        api.opener.open.return_value.__exit__ = Mock(return_value=False)
        api.file('/home/daejinha/example.zip', b'package')
        request = api.opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Token ' + self.credentials['token'])
        self.assertIn(b'name="content"', request.data)
        self.assertIn(b'package', request.data)
        self.assertNotIn(self.credentials['token'].encode(), request.data)

    def test_api_failure_does_not_echo_server_body_or_token(self):
        api = deploy.API(self.credentials)
        api.opener = Mock()
        api.opener.open.side_effect = urllib.error.HTTPError('url', 401, 'Unauthorized', {}, io.BytesIO(self.credentials['token'].encode()))
        with self.assertRaises(deploy.DeploymentError) as caught:
            api.request('GET', '/cpu/')
        self.assertIn('401', str(caught.exception))
        self.assertNotIn(self.credentials['token'], str(caught.exception))

    def test_file_scope(self):
        api = deploy.API(self.credentials)
        for path in ['/etc/passwd', '/home/daejinha/../../secret']:
            with self.assertRaises(deploy.DeploymentError):
                api.file(path)

    def test_duplicate_static_mapping_stops(self):
        api = Mock()
        api.request.return_value = [dict(url='/static/', id=1), dict(url='/static/', id=2)]
        with self.assertRaises(deploy.DeploymentError):
            deploy.set_mappings(api, {'/static/': 'new'})
        self.assertEqual(api.request.call_count, 1)

    def test_console_echo_is_not_ready_marker(self):
        api = Mock()
        api.request.return_value = dict(output="printf '\\n%s\\n' COMMON01READY" + 'a' * 24)
        with patch.object(deploy.secrets, 'token_hex', return_value='a' * 24), patch.object(deploy.time, 'sleep'):
            with self.assertRaises(deploy.DeploymentError):
                deploy.wait_ready(api, 123)

    def test_remote_failure_never_activates(self):
        api = Mock()
        api.file.return_value = b'{"phase":"failed"}'
        with patch.object(deploy.time, 'sleep'):
            with self.assertRaises(deploy.DeploymentError):
                deploy.wait_stage(api, '/result')
        api.request.assert_not_called()

    def test_connect_pipe_saves_private_file_after_verification(self):
        with patch.object(auth.sys, 'stdin', io.StringIO(self.credentials['token'])), patch.object(auth, 'metadata') as check:
            result = auth.connect('daejinha', 'www.pythonanywhere.com', self.root, local_pipe=True)
        self.assertTrue(result['authenticated'])
        check.assert_called_once()
        self.assertEqual((self.root / 'auth.json').stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.credentials['token'], json.dumps(result))

    def test_failed_connect_does_not_store_token(self):
        with patch.object(auth.sys, 'stdin', io.StringIO(self.credentials['token'])), patch.object(auth, 'metadata', side_effect=auth.AuthError('Rejected')):
            with self.assertRaises(auth.AuthError):
                auth.connect('daejinha', 'www.pythonanywhere.com', self.root, local_pipe=True)
        self.assertFalse((self.root / 'auth.json').exists())

    def test_noninteractive_getpass_is_rejected(self):
        with patch.object(auth.sys, 'stdin', io.StringIO('')):
            with self.assertRaises(auth.AuthError):
                auth.connect('daejinha', 'www.pythonanywhere.com', self.root)

    def test_private_remote_status(self):
        result = self.root / 'result.json'
        remote.write_json(result, dict(phase='staged'))
        self.assertEqual(result.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(result.read_text())['phase'], 'staged')

    def activation_api(self):
        api = Mock()
        previous = dict(source_directory='/old', virtualenv_path='/old-venv', force_https=False)
        mappings = [dict(id=1, url='/static/', path='/old-static'), dict(id=2, url='/media/', path='/old-media')]
        endpoint = '/webapps/' + deploy.DOMAIN + '/'
        api.request.side_effect = lambda method, path, *args: (previous if path == endpoint else mappings) if method == 'GET' else None
        api.file.side_effect = lambda path, *args: b'old_wsgi' if path == deploy.WSGI and not args else b'candidate'
        state = dict(previous_wsgi_sha256=hashlib.sha256(b'old_wsgi').hexdigest(), candidate_wsgi='/candidate',
                     source='/new', virtualenv='/new-venv', static='/new-static', media='/media', release='test', previous=None)
        return api, state

    def test_activation_success_requires_public_smoke_before_commit(self):
        api, state = self.activation_api()
        with patch.object(deploy, 'smoke', return_value=[dict(status=200)]), patch.object(deploy.time, 'sleep'):
            result = deploy.activate(api, state, {}, self.root)
        self.assertEqual(result['phase'], 'verified')
        self.assertTrue((self.root / 'result.json').exists())
        self.assertTrue(any(call.args[0] == deploy.BASE + '/active.json' for call in api.file.call_args_list))

    def test_activation_failure_restores_wsgi_and_routing_without_db_restore(self):
        api, state = self.activation_api()
        with patch.object(deploy, 'smoke', side_effect=deploy.DeploymentError('Unavailable')), patch.object(deploy.time, 'sleep'):
            with self.assertRaisesRegex(deploy.DeploymentError, 'restored'):
                deploy.activate(api, state, {}, self.root)
        writes = [call.args for call in api.file.call_args_list if len(call.args) > 1]
        self.assertIn((deploy.WSGI, b'old_wsgi'), writes)
        self.assertFalse(any('active.json' in call[0] for call in writes))
        self.assertFalse(any('db.sqlite3' in call[0] for call in writes))

    def test_long_opaque_token_is_validated_by_api_not_local_assumptions(self):
        value = 'opaque.' + 'a' * 200
        with patch.object(auth.sys, 'stdin', io.StringIO(value)), patch.object(auth, 'metadata') as check:
            auth.connect('daejinha', 'www.pythonanywhere.com', self.root, local_pipe=True)
        self.assertEqual(check.call_args.args[0]['token'], value)

    def test_cleanup_keeps_two_releases_and_original_backup(self):
        base, private = self.root / 'public', self.root / 'private'
        releases = base / 'releases'
        releases.mkdir(parents=True)
        private.mkdir()
        ids = ['20261020000000' + char * 6 for char in 'abcd']
        for release in ids:
            (releases / release).mkdir()
            (private / release).mkdir()
        (private / ids[0] / 'original-project.tar.gz').write_bytes(b'original')
        (releases / 'unrelated-user-directory').mkdir()
        (base / 'active.json').write_text(json.dumps(dict(phase='verified', release=ids[3], previous=dict(release=ids[2]))))
        remote.cleanup(base, private)
        self.assertFalse((releases / ids[0]).exists())
        self.assertTrue((private / ids[0] / 'original-project.tar.gz').exists())
        self.assertFalse((private / ids[1]).exists())
        self.assertTrue((releases / ids[2]).exists())
        self.assertTrue((releases / 'unrelated-user-directory').exists())

    def test_cleanup_requires_verified_deployment(self):
        (self.root / 'active.json').write_text('{"phase":"staged"}')
        with self.assertRaises(ValueError):
            remote.cleanup(self.root, self.root)

    def test_cleanup_refuses_symlink_target(self):
        (self.root / 'releases').mkdir()
        (self.root / 'outside').mkdir()
        (self.root / 'releases/20261020000000aaaaaa').symlink_to(self.root / 'outside')
        (self.root / 'active.json').write_text('{"phase":"verified","release":"other"}')
        with self.assertRaises(ValueError):
            remote.cleanup(self.root, self.root)

    def test_whitespace_input_is_rejected_without_api_request(self):
        with patch.object(auth.sys, 'stdin', io.StringIO('not a token')), patch.object(auth, 'metadata') as check:
            with self.assertRaises(auth.AuthError):
                auth.connect('daejinha', 'www.pythonanywhere.com', self.root, local_pipe=True)
        check.assert_not_called()

    def test_windows_framework_stdin_bom_is_removed(self):
        with patch.object(auth.sys, 'stdin', io.StringIO('\ufeff' + self.credentials['token'])), patch.object(auth, 'metadata') as check:
            auth.connect('daejinha', 'www.pythonanywhere.com', self.root, local_pipe=True)
        self.assertEqual(check.call_args.args[0]['token'], self.credentials['token'])

    def test_public_smoke_uses_real_module_filename_and_checks_digest(self):
        path = deploy.SERVER / 'blog/static/blog/content/composer.mjs'
        content = path.read_bytes()
        manifest = dict(files=[dict(path=path.relative_to(deploy.SERVER).as_posix(), sha256=hashlib.sha256(content).hexdigest())])
        opener = Mock()
        def response(url, **kwargs):
            result = Mock()
            result.status = 200
            result.read.return_value = content if url.endswith('/composer.mjs') else b'page'
            context = Mock()
            context.__enter__ = Mock(return_value=result)
            context.__exit__ = Mock(return_value=False)
            return context
        opener.open.side_effect = response
        with patch.object(deploy.urllib.request, 'build_opener', return_value=opener):
            result = deploy.smoke({}, manifest)
        self.assertEqual(len(result), 4)
        self.assertTrue(result[-1]['path'].endswith('/composer.mjs'))
        self.assertEqual(result[-1]['sha256'], manifest['files'][0]['sha256'])

    def test_public_smoke_rejects_stale_module_bytes(self):
        manifest = dict(files=[dict(path='blog/static/blog/content/composer.mjs', sha256='0' * 64)])
        response = Mock(status=200)
        response.read.return_value = b'stale module'
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(deploy.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(deploy.DeploymentError):
                deploy.smoke({}, manifest)


if __name__ == '__main__':
    unittest.main()
