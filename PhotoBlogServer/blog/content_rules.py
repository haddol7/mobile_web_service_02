"""Photo-content validation and literal search normalization, without ORM or HTTP."""
import json
import math
import re
import unicodedata
from uuid import UUID

THEMES = {"food": "음식", "animal": "동물", "nature": "자연·풍경", "people": "인물",
          "space": "건축·공간", "object": "사물", "other": "기타"}
OCR_STATUSES = {"ready", "no_text", "skipped", "failed", "not_analyzed"}
MAX_CONTENT_BYTES = 64 * 1024


class ContentError(ValueError):
    def __init__(self, detail, *, field="photo_content", code="invalid_content", status=400, revision=None):
        self.detail, self.field, self.code, self.status, self.revision = detail, field, code, status, revision
        super().__init__(detail)


def fail(detail, field="photo_content"):
    raise ContentError(detail, field=field)


def text_value(value, maximum, field, *, allow_empty=False):
    if not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value):
        fail("제어문자 없는 문자열을 입력하세요.", field)
    value = " ".join(value.split())
    if len(value) > maximum or (not value and not allow_empty):
        fail(f"1–{maximum}문자로 입력하세요.", field)
    return value


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def query_terms(value):
    value = normalize(text_value(value, 160, "q"))
    if not 2 <= len(value) <= 80 or len(value.split()) > 5:
        fail("검색어는 2–80문자, 최대 5개 단어로 입력하세요.", "q")
    return list(dict.fromkeys(value.split()))


def integer(value, low, high, field):
    if type(value) is not int or not low <= value <= high:
        fail(f"{low}–{high} 범위의 정수를 입력하세요.", field)
    return value


def exact_fields(value, required, field, optional=()):
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - set(optional):
        fail("필드 구성을 확인하세요.", field)


def validate_quad(value, field):
    if not isinstance(value, list) or len(value) != 4:
        fail("네 점의 사각형이 필요합니다.", field)
    points = []
    for point in value:
        if not isinstance(point, list) or len(point) != 2 or any(
            type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1 for n in point
        ):
            fail("좌표는 0–1 사이의 유한한 숫자여야 합니다.", field)
        points.append([float(n) for n in point])
    for i in range(4):
        a, b, c = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
        cross = (b[0]-a[0])*(c[1]-b[1]) - (b[1]-a[1])*(c[0]-b[0])
        if cross <= 1e-12:
            fail("이미지 기준 시계 방향의 볼록한 사각형이어야 합니다.", field)
    return points


def validate_packet(value):
    required = {"schema_version", "image_sha256", "width", "height", "model_versions", "mapping_version",
                "theme_status", "theme", "theme_origin", "tags", "ocr_status", "lines"}
    exact_fields(value, required, "photo_content", {"expected_revision"})
    try:
        size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (ValueError, TypeError, UnicodeError):
        fail("JSON에 올바르지 않은 값이 있습니다.")
    if size > MAX_CONTENT_BYTES:
        raise ContentError("분석 결과는 64KiB 이하여야 합니다.", status=413)
    integer(value["schema_version"], 1, 1, "schema_version")
    digest = value["image_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        fail("이미지 SHA-256을 확인하세요.", "image_sha256")
    width = integer(value["width"], 1, 8192, "width")
    height = integer(value["height"], 1, 8192, "height")
    if width * height > 16_000_000:
        fail("사진은 16MP 이하여야 합니다.", "width")
    versions = value["model_versions"]
    if not isinstance(versions, dict) or len(versions) > 4 or set(versions) - {"label", "ocr_ko", "ocr_latin", "face"}:
        fail("모델 버전 구성을 확인하세요.", "model_versions")
    clean_versions = {k: text_value(v, 32, "model_versions") for k, v in versions.items()}
    mapping = text_value(value["mapping_version"], 40, "mapping_version", allow_empty=True)
    theme, theme_status, origin = value["theme"], value["theme_status"], value["theme_origin"]
    if not isinstance(theme_status, str) or theme_status not in {"classified", "unclassified", "not_analyzed"}:
        fail("분류 상태를 확인하세요.", "theme_status")
    if theme_status == "classified":
        if not isinstance(theme, str) or theme not in THEMES or origin not in ("auto", "user"):
            fail("확정 테마와 출처를 확인하세요.", "theme")
    elif theme is not None or origin != "unclassified":
        fail("미분류·미분석 테마는 null이어야 합니다.", "theme")
    if not isinstance(value["tags"], list) or len(value["tags"]) > 10:
        fail("태그는 최대 10개입니다.", "tags")
    tags, seen = [], set()
    for tag in value["tags"]:
        exact_fields(tag, {"display", "origin"}, "tags")
        display = text_value(tag["display"], 30, "tags")
        normalized = normalize(display)
        if len(normalized) > 60 or tag["origin"] not in ("auto", "user"):
            fail("태그 길이와 출처를 확인하세요.", "tags")
        if normalized not in seen:
            seen.add(normalized)
            tags.append({"display": display, "normalized": normalized, "origin": tag["origin"]})
    if not isinstance(value["ocr_status"], str) or value["ocr_status"] not in OCR_STATUSES:
        fail("글자 인식 상태를 확인하세요.", "ocr_status")
    if not isinstance(value["lines"], list) or len(value["lines"]) > 100:
        fail("검색 문구는 최대 100줄입니다.", "lines")
    if value["ocr_status"] != "ready" and value["lines"]:
        fail("인식 완료 상태에서만 검색 문구를 보낼 수 있습니다.", "lines")
    lines, ids, total = [], set(), 0
    for line in value["lines"]:
        exact_fields(line, {"line_id", "text", "quad", "origin"}, "lines")
        try:
            line_id = str(UUID(line["line_id"]))
        except (ValueError, TypeError, AttributeError):
            fail("글자 영역 ID가 올바르지 않습니다.", "lines")
        if line_id in ids or line["origin"] not in ("auto", "user"):
            fail("중복 영역 ID 또는 올바르지 않은 출처입니다.", "lines")
        ids.add(line_id)
        text = text_value(line["text"], 200, "lines")
        total += len(text)
        normalized = normalize(text)
        lines.append({"line_id": line_id, "text": text, "norm_text": normalized,
                      "compact_text": normalized.replace(" ", ""),
                      "quad": validate_quad(line["quad"], "lines"), "origin": line["origin"]})
    if total > 8192:
        fail("검색 문구 전체는 8192문자 이하여야 합니다.", "lines")
    result = {k: value[k] for k in required}
    result.update(model_versions=clean_versions, mapping_version=mapping, tags=tags, lines=lines)
    if "expected_revision" in value:
        result["expected_revision"] = integer(value["expected_revision"], 0, 2**63-1, "expected_revision")
    return result
