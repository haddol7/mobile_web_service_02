import blog.models
import blog.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name="Post",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=200)),
            ("text", models.TextField()),
            ("created_date", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ("published_date", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ("image", models.ImageField(upload_to=blog.models.photo_upload_path, validators=[blog.validators.validate_photo])),
            ("author", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photo_posts", to=settings.AUTH_USER_MODEL)),
        ],
        options={"ordering": ("-created_date", "-id")},
    )]
