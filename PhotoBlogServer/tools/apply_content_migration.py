"""Back up the local SQLite database before applying additive content migrations."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photoblog.settings")


if __name__ == "__main__":
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in WSL Ubuntu.")
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from blog.models import Post
    root = Path(__file__).resolve().parents[2]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = root / "evidence/private/database-backups" / f"before-content-{stamp}.sqlite3"
    backup.parent.mkdir(parents=True, exist_ok=True)
    def snapshot():
        result = []
        for post in Post.objects.order_by("pk"):
            with post.image.open("rb") as image:
                digest = hashlib.file_digest(image, "sha256").hexdigest()
            result.append({"id":post.pk,"author_id":post.author_id,"image":post.image.name,"sha256":digest})
        return result
    before = snapshot()
    with sqlite3.connect(settings.DATABASES["default"]["NAME"]) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    call_command("migrate", interactive=False)
    after = snapshot()
    record = {"environment":"WSL Ubuntu", "backup":str(backup.relative_to(root)),
              "existing_posts":len(before),"existing_post_images_unchanged":before==after}
    destination=root/"evidence/content/server/migration.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(record,ensure_ascii=False))
    if before != after:
        raise SystemExit("Existing images changed; inspect backup before proceeding.")
