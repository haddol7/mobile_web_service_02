from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .validators import validate_photo


def photo_upload_path(instance, filename):
    # User filenames never become paths. Extensions are checked against the decoded format.
    return f"images/{timezone.now():%Y/%m/%d}/{uuid4().hex}{Path(filename).suffix.lower()}"


class Post(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="photo_posts")
    title = models.CharField(max_length=200)
    text = models.TextField()
    created_date = models.DateTimeField(default=timezone.now, editable=False)
    published_date = models.DateTimeField(default=timezone.now, editable=False)
    image = models.ImageField(upload_to=photo_upload_path, validators=[validate_photo])

    class Meta:
        ordering = ("-created_date", "-id")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from .services import lock_owner, remove_uncommitted_upload

        original_image = self.image.name if self.image and self.image._committed else None
        committed = False

        def mark_committed():
            nonlocal committed
            committed = True

        try:
            with transaction.atomic():
                transaction.on_commit(mark_committed)
                lock_owner(self.author_id)
                if self.pk:
                    original = type(self).objects.filter(pk=self.pk).values("author_id", "image").first()
                    if original:
                        original_image = original["image"]
                        if original["author_id"] != self.author_id:
                            raise ValidationError({"author": "게시글 작성자는 변경할 수 없습니다."})
                self.full_clean()
                return super().save(*args, **kwargs)
        except Exception:
            if not committed:
                remove_uncommitted_upload(self, original_image)
            raise

    def delete(self, *args, **kwargs):
        from .services import lock_owner
        with transaction.atomic():
            lock_owner(self.author_id)
            return super().delete(*args, **kwargs)


class PhotoContent(models.Model):
    post = models.OneToOneField(Post, on_delete=models.CASCADE, related_name="content")
    revision = models.PositiveBigIntegerField(default=1)
    image_sha256 = models.CharField(max_length=64)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    schema_version = models.PositiveSmallIntegerField(default=1)
    model_versions = models.JSONField(default=dict)
    mapping_version = models.CharField(max_length=40, blank=True)
    theme = models.CharField(max_length=16, null=True, db_index=True)
    theme_status = models.CharField(max_length=16, default="not_analyzed")
    theme_origin = models.CharField(max_length=16, default="unclassified")
    ocr_status = models.CharField(max_length=16, default="not_analyzed")
    updated_at = models.DateTimeField(auto_now=True)


class PhotoTag(models.Model):
    content = models.ForeignKey(PhotoContent, on_delete=models.CASCADE, related_name="tags")
    display = models.CharField(max_length=30)
    normalized = models.CharField(max_length=60, db_index=True)
    origin = models.CharField(max_length=8)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("content", "normalized"), name="unique_photo_tag")]


class PhotoTextLine(models.Model):
    content = models.ForeignKey(PhotoContent, on_delete=models.CASCADE, related_name="lines")
    line_id = models.UUIDField()
    text = models.CharField(max_length=200)
    norm_text = models.TextField()
    compact_text = models.TextField()
    quad = models.JSONField()
    origin = models.CharField(max_length=8)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("content", "line_id"), name="unique_photo_text_line")]

