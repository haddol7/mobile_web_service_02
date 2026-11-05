"""Validate complete image content before saving it to media storage."""
from pathlib import Path
import warnings

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 16_000_000
MAX_PHOTO_DIMENSION = 8192
PHOTO_EXTENSIONS = {"JPEG": {".jpg", ".jpeg"}, "PNG": {".png"}, "WEBP": {".webp"}}


def validate_photo(upload):
    if upload.size > MAX_PHOTO_BYTES:
        raise ValidationError("사진은 5 MiB 이하여야 합니다.", code="photo_too_large")
    try:
        upload.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as image:
                width, height = image.size
                if image.format not in PHOTO_EXTENSIONS:
                    raise ValidationError("JPEG, PNG, WebP 사진만 지원합니다.", code="photo_format")
                if Path(upload.name).suffix.lower() not in PHOTO_EXTENSIONS[image.format]:
                    raise ValidationError("사진 내용과 파일 확장자가 일치해야 합니다.", code="photo_extension")
                if (
                    width < 1 or height < 1 or width > MAX_PHOTO_DIMENSION
                    or height > MAX_PHOTO_DIMENSION or width * height > MAX_PHOTO_PIXELS
                ):
                    raise ValidationError("사진은 가로·세로 8192 px 및 1600만 픽셀 이하여야 합니다.", code="photo_dimensions")
                if getattr(image, "is_animated", False):
                    raise ValidationError("움직이는 사진은 지원하지 않습니다.", code="photo_animation")
                image.verify()
            # JPEG verify() can succeed with truncated pixel data. Reopen after
            # verify() and decode fully, within the dimensions already checked.
            upload.seek(0)
            with Image.open(upload) as decoded:
                decoded.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValidationError("유효한 이미지 파일을 선택하세요.", code="photo_invalid") from error
    finally:
        upload.seek(0)

