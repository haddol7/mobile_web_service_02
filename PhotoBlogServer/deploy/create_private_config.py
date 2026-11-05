"""Explicit preparation command: create a fresh private key without printing it."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from deploy.production import load_environment, validate_config_location, validate_values


def create_config(config_path, host):
    if os.name != "posix" or sys.version_info < (3, 12):
        raise RuntimeError("Run inside PythonAnywhere Bash or WSL Python 3.12+.")
    values = validate_values({
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_ALLOWED_HOSTS": host,
    })
    path = validate_config_location(config_path, PROJECT_ROOT)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise ValueError("Select an owner-only private directory (mode 0700).")
    # Exclusive creation: never rotate an existing key or overwrite a previous config.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(values, output, indent=2)
        output.write("\n")
    load_environment(path, PROJECT_ROOT)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Absolute private JSON path outside source")
    parser.add_argument("--host", required=True, help="Approved username.pythonanywhere.com hostname")
    arguments = parser.parse_args()
    path = create_config(arguments.config, arguments.host)
    print(f"Created private configuration: {path}; secret not displayed.")


if __name__ == "__main__":
    main()
