"""Consistent SQLite backup before additive migrations; no auth data is printed."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
from uuid import uuid4


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Database operations must run inside WSL.")
    server = Path(__file__).resolve().parents[1]
    database = server / "db.sqlite3"
    if not database.is_file():
        raise SystemExit("No existing development database; nothing to back up.")
    private = server.parent / "evidence" / "private" / "database-backups"
    private.mkdir(parents=True, exist_ok=True)
    destination = private / f"before-migration-{uuid4().hex}.sqlite3"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SystemExit("Backup integrity check failed; do not migrate.")
            post_count = target.execute("SELECT COUNT(*) FROM blog_post").fetchone()[0]
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "environment": "WSL " + os.environ["WSL_DISTRO_NAME"],
        "source": str(database), "backup": str(destination), "integrity_check": "ok", "post_count": post_count,
        "contains_private_auth_data": True, "git_ignored_location": True,
    }
    destination.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
