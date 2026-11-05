"""Two actual processes exercise revision control in an isolated file SQLite DB."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

from django.test import SimpleTestCase


class ContentFileConcurrencyTests(SimpleTestCase):
    def test_simultaneous_owner_corrections_have_one_winner(self):
        setup = textwrap.dedent("""
            import json, sys
            from pathlib import Path
            from django.conf import settings
            settings.DATABASES['default']['NAME'] = sys.argv[1]
            settings.MEDIA_ROOT = Path(sys.argv[2])
            settings.BLOG_OWNER_USERNAME = 'content-concurrency'
            import django
            django.setup()
        """)
        bootstrap = setup + textwrap.dedent("""
            from django.core.management import call_command
            from django.contrib.auth import get_user_model
            from blog.services import create_post
            from blog.tests.helpers import uploaded_photo
            from blog.tests.test_photo_content import packet
            call_command('migrate', verbosity=0, interactive=False)
            owner = get_user_model().objects.create_user('content-concurrency')
            post = create_post(actor=owner, values={'title':'fixture','text':'body', 'image':uploaded_photo(), 'photo_content':packet()})
            print(json.dumps({'owner':owner.pk,'post':post.pk}))
        """)
        worker = setup + textwrap.dedent("""
            import time
            from django.contrib.auth import get_user_model
            from blog import services
            from blog.content_services import update_content
            from blog.content_rules import ContentError
            from blog.tests.test_photo_content import packet
            owner=get_user_model().objects.get(pk=int(sys.argv[3]))
            original=services.lock_owner
            def hold(pk):
                result=original(pk)
                time.sleep(0.25)
                return result
            services.lock_owner=hold
            print('READY',flush=True)
            if sys.stdin.readline().strip() != 'GO': raise RuntimeError('Missing gate')
            started=time.monotonic()
            try:
                row=update_content(actor=owner,post_id=int(sys.argv[4]),packet=packet(revision=1))
                outcome={'status':200,'revision':row.revision}
            except ContentError as error:
                outcome={'status':error.status,'revision':error.revision}
            outcome.update(started=started,finished=time.monotonic())
            print(json.dumps(outcome),flush=True)
        """)
        project=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="content-file-cas-") as temp:
            args=[str(Path(temp)/"isolated.sqlite3"),str(Path(temp)/"media")]
            result=subprocess.run([sys.executable,"-c",bootstrap,*args],cwd=project,capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stderr)
            ids=json.loads(result.stdout)
            processes=[]
            try:
                for _ in range(2):
                    processes.append(subprocess.Popen([sys.executable,"-c",worker,*args,str(ids["owner"]),str(ids["post"])],
                        cwd=project,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
                for process in processes: self.assertEqual(process.stdout.readline().strip(),"READY")
                for process in processes: process.stdin.write("GO\n"); process.stdin.flush()
                results=[]
                for process in processes:
                    stdout,stderr=process.communicate(timeout=30)
                    self.assertEqual(process.returncode,0,stderr)
                    results.append(json.loads(stdout))
                self.assertEqual(sorted(r["status"] for r in results),[200,409])
                self.assertTrue(all(r["revision"]==2 for r in results))
                self.assertLess(max(r["started"] for r in results),min(r["finished"] for r in results))
            finally:
                for process in processes:
                    if process.poll() is None: process.kill(); process.communicate()
