from pathlib import PurePosixPath
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from blog.models import photo_upload_path
from blog.validators import MAX_PHOTO_BYTES, validate_photo
from .helpers import photo_bytes, uploaded_photo


class PhotoValidationUnitTests(SimpleTestCase):
    def test_png_jpeg_webp_supported(self):
        for name, format_name in (("photo.png", "PNG"), ("photo.jpg", "JPEG"), ("photo.webp", "WEBP")):
            with self.subTest(format_name=format_name):
                upload = uploaded_photo(name, image_format=format_name)
                validate_photo(upload)
                self.assertEqual(upload.tell(), 0)

    def test_extension_content_mismatch_rejected(self):
        with self.assertRaisesMessage(ValidationError, "파일 확장자"):
            validate_photo(uploaded_photo("not-jpeg.jpg"))

    def test_corrupted_file_rejected_and_cursor_reset(self):
        upload = SimpleUploadedFile("broken.png", b"broken PNG data")
        with self.assertRaises(ValidationError):
            validate_photo(upload)
        self.assertEqual(upload.tell(), 0)

    def test_truncated_jpeg_is_rejected_and_cursor_reset(self):
        original = photo_bytes(image_format="JPEG")
        self.assertTrue(original.startswith(b"\xff\xd8"))
        self.assertTrue(original.endswith(b"\xff\xd9"))
        for removed_bytes in (2, 10, 25, 50):
            with self.subTest(removed_bytes=removed_bytes):
                upload = SimpleUploadedFile(
                    "truncated.jpg", original[:-removed_bytes], content_type="image/jpeg"
                )
                upload.seek(7)
                with self.assertRaises(ValidationError):
                    validate_photo(upload)
                self.assertEqual(upload.tell(), 0)

    def test_size_limit_is_enforced_before_decode(self):
        upload = uploaded_photo()
        upload.size = MAX_PHOTO_BYTES + 1
        with self.assertRaisesMessage(ValidationError, "5 MiB"):
            validate_photo(upload)

    def test_overwide_image_rejected(self):
        with self.assertRaisesMessage(ValidationError, "8192"):
            validate_photo(uploaded_photo(size=(8193, 1)))

    def test_over_pixel_budget_rejected(self):
        with self.assertRaisesMessage(ValidationError, "1600만"):
            validate_photo(uploaded_photo(size=(4001, 4000)))

    def test_gif_format_not_supported_even_when_valid_image(self):
        with self.assertRaisesMessage(ValidationError, "JPEG, PNG, WebP"):
            validate_photo(uploaded_photo("photo.gif", image_format="GIF"))

    def test_user_filename_does_not_become_upload_path(self):
        first = photo_upload_path(None, "../../a/photo.PNG")
        second = photo_upload_path(None, "../../a/photo.PNG")
        self.assertNotEqual(first, second)
        self.assertNotIn("..", PurePosixPath(first).parts)
        self.assertRegex(first, r"^images/\d{4}/\d{2}/\d{2}/[a-f0-9]{32}\.png$")

