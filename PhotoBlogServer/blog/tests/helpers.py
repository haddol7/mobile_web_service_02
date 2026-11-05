from io import BytesIO
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image


def photo_bytes(size=(48, 32), image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", size, color=(127, 173, 120)).save(buffer, format=image_format)
    return buffer.getvalue()


def uploaded_photo(name="photo.png", size=(48, 32), image_format="PNG"):
    return SimpleUploadedFile(name, photo_bytes(size, image_format), content_type=f"image/{image_format.lower()}")


class TemporaryMediaMixin:
    def setUp(self):
        super().setUp()
        media_root = tempfile.mkdtemp(prefix="photoblog-test-media-")
        self.media_root = media_root
        media_override = override_settings(MEDIA_ROOT=media_root)
        media_override.enable()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        self.addCleanup(media_override.disable)
