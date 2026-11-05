from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SingleOwnerMigrationTests(TransactionTestCase):
    def test_studio_removal_keeps_users_posts_content_and_photo_paths(self):
        old=[('blog','0003_photocontent_phototag_phototextline')]
        executor=MigrationExecutor(connection)
        latest=executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(old)
            apps=executor.loader.project_state(old).apps
            user=apps.get_model('auth','User').objects.create(username='existing-publisher',password='!')
            post=apps.get_model('blog','Post').objects.create(author_id=user.pk,title='기존 사진',text='유지',image='images/preserved.png')
            gallery=apps.get_model('blog','Gallery').objects.create(owner_id=user.pk,name='폐기된 사진관')
            apps.get_model('blog','DecorLayout').objects.create(gallery=gallery)
            content=apps.get_model('blog','PhotoContent').objects.create(post_id=post.pk,image_sha256='a'*64,width=10,height=20)
            snapshots={name:list(apps.get_model(app,name).objects.values()) for app,name in [('auth','User'),('blog','Post'),('blog','PhotoContent')]}
            executor=MigrationExecutor(connection)
            executor.migrate(latest)
            apps=executor.loader.project_state(latest).apps
            for app,name in [('auth','User'),('blog','Post'),('blog','PhotoContent')]:
                self.assertEqual(list(apps.get_model(app,name).objects.values()),snapshots[name])
            tables=connection.introspection.table_names()
            self.assertNotIn('blog_gallery',tables)
            self.assertNotIn('blog_decorlayout',tables)
        finally:
            MigrationExecutor(connection).migrate(latest)
