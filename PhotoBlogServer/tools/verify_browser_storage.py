"""Read-only proof that the browser's local DB rows reference real fixture bytes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
FIXTURE = PROJECT_ROOT / "evidence" / "test-runs" / "baseline-photo.png"
OUTPUT = PROJECT_ROOT / "evidence" / "baseline" / "browser-storage.json"


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Browser storage verification must run inside WSL.")
    sys.path.insert(0, str(SERVER_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photoblog.settings")
    import django
    django.setup()
    from django.conf import settings
    from PIL import Image
    from blog.models import Post

    fixture_sha = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    rows = []
    for pk in (1, 2):
        post = Post.objects.filter(pk=pk).first()
        row = {"id": pk, "row_exists": post is not None}
        if post:
            path = Path(post.image.path)
            row.update({
                "author_id": post.author_id,
                "expected_author_id": 1,
                "author_matches": post.author_id == 1,
                "image_name": post.image.name,
                "image_file_exists": path.is_file(),
            })
            if path.is_file():
                row["stored_bytes"] = path.stat().st_size
                row["stored_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                row["matches_browser_upload_fixture"] = row["stored_sha256"] == fixture_sha
                try:
                    with Image.open(path) as image:
                        row["image_format"] = image.format
                        row["image_dimensions"] = list(image.size)
                        image.verify()
                    row["pillow_verify_pass"] = True
                except Exception as error:
                    row["pillow_verify_pass"] = False
                    row["pillow_error_type"] = type(error).__name__
        row["pass"] = all(row.get(key, False) for key in (
            "row_exists", "author_matches", "image_file_exists", "matches_browser_upload_fixture", "pillow_verify_pass",
        ))
        rows.append(row)
    result = {
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "environment": "WSL " + os.environ["WSL_DISTRO_NAME"],
        "python": sys.executable,
        "database_path": str(settings.DATABASES["default"]["NAME"]),
        "scope": "Local browser-upload Post IDs 1 and 2, not Django's isolated test database.",
        "read_only": True,
        "post_count_in_local_database": Post.objects.count(),
        "fixture_path": str(FIXTURE.relative_to(PROJECT_ROOT)),
        "fixture_sha256": fixture_sha,
        "rows": rows,
        "pass": all(row["pass"] for row in rows),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Read-only browser storage evidence: {OUTPUT}")
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
