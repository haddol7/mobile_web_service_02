"""Load an explicit, private production configuration without new dependencies."""
import json
import os
from pathlib import Path
import re
import stat
import sys


CONFIG_KEYS = {"DJANGO_DEBUG", "DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS"}
HOST_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]*\.pythonanywhere\.com\Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key.")
        result[key] = value
    return result


def validate_values(values):
    """Validate everything before touching the process environment; never echo values."""
    if not isinstance(values, dict) or set(values) != CONFIG_KEYS:
        raise ValueError("Production configuration must contain exactly the documented keys.")
    if values["DJANGO_DEBUG"] != "false":
        raise ValueError("Production DJANGO_DEBUG must be the string false.")
    secret = values["DJANGO_SECRET_KEY"]
    if (
        not isinstance(secret, str) or len(secret) < 50 or len(set(secret)) < 5
        or secret.startswith("django-insecure-")
        or any(marker in secret.upper() for marker in ("REPLACE", "CHANGE_ME", "EXAMPLE"))
    ):
        raise ValueError("Use a private, randomly generated production secret key.")
    host = values["DJANGO_ALLOWED_HOSTS"]
    if not isinstance(host, str) or not HOST_PATTERN.fullmatch(host):
        raise ValueError("Use exactly the approved account's PythonAnywhere hostname.")
    return dict(values)


def validate_config_location(config_path, project_root):
    """Keep private configuration outside the submitted Common Assessment source."""
    candidate = Path(config_path).expanduser()
    if not candidate.is_absolute() or candidate.is_symlink():
        raise ValueError("Use an absolute, non-symlink private configuration path.")
    resolved = candidate.resolve()
    assessment_root = Path(project_root).resolve().parent
    if resolved.is_relative_to(assessment_root):
        raise ValueError("Private configuration must be outside the assessment source tree.")
    return resolved


def load_environment(config_path, project_root):
    """Load before importing Django settings in both WSGI and management commands."""
    if os.name != "posix" or sys.version_info < (3, 12):
        raise RuntimeError("Production requires Linux and Python 3.12 or newer.")
    project_root = Path(project_root).resolve()
    if not (project_root / "manage.py").is_file() or not (project_root / "photoblog/settings.py").is_file():
        raise ValueError("Select the approved Common Assessment PhotoBlogServer directory.")
    path = validate_config_location(config_path, project_root)
    try:
        metadata = path.stat()
        parent = path.parent.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_mode & 0o077
            or parent.st_uid != os.geteuid()
            or parent.st_mode & 0o077
            or metadata.st_size > 16 * 1024
        ):
            raise ValueError("Private configuration requires an owner-only directory and file.")
        values = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        values = validate_values(values)
    except (OSError, ValueError, UnicodeError):
        # Do not attach parser errors, which can contain confidential input values.
        raise ValueError("Cannot load valid private production configuration.") from None
    os.environ.update(values)
    os.environ["DJANGO_SETTINGS_MODULE"] = "photoblog.settings"
    return project_root
