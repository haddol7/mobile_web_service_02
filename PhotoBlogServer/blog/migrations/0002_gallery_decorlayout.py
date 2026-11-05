import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def create_existing_galleries(apps, schema_editor):
    user_app, user_model = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app, user_model)
    Post = apps.get_model("blog", "Post")
    Gallery = apps.get_model("blog", "Gallery")
    DecorLayout = apps.get_model("blog", "DecorLayout")
    alias, now = schema_editor.connection.alias, django.utils.timezone.now()
    for owner in User.objects.using(alias).all().iterator():
        count = Post.objects.using(alias).filter(author_id=owner.pk, published_date__lte=now).count()
        gallery = Gallery.objects.using(alias).create(
            owner_id=owner.pk, name=f"{owner.username}의 사진관"[:80], peak_photo_count=count,
        )
        DecorLayout.objects.using(alias).create(gallery_id=gallery.pk)


class Migration(migrations.Migration):
    dependencies = [("blog", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="Gallery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("description", models.TextField(blank=True, default="", max_length=2000)),
                ("peak_photo_count", models.PositiveIntegerField(default=0)),
                ("created_date", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="gallery", to=settings.AUTH_USER_MODEL)),
            ], options={"ordering": ("id",)},
        ),
        migrations.CreateModel(
            name="DecorLayout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revision", models.PositiveIntegerField(default=0)),
                ("items", models.JSONField(default=list)),
                ("updated_date", models.DateTimeField(auto_now=True)),
                ("gallery", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="layout", to="blog.gallery")),
            ],
        ),
        migrations.RunPython(create_existing_galleries, migrations.RunPython.noop),
    ]
