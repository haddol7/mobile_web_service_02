"""Load optional server-only credentials from the user's private configuration."""
import json
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


def load_llm_config(environ=None, home=None):
    environ = os.environ if environ is None else environ
    default = (Path.home() if home is None else Path(home)) / ".config/mobile-web-service/common02/llm.json"
    location = environ.get("HISTORY_LLM_CONFIG", str(default))
    private = {}
    if location:
        try:
            with Path(location).open(encoding="utf-8") as source:
                raw = source.read(65537)
            if len(raw) > 65536:
                raise ValueError
            private = json.loads(raw)
            if not isinstance(private, dict) or any(
                not isinstance(private.get(key, ""), str) for key in ("provider", "model", "api_key")
            ):
                raise ValueError
        except FileNotFoundError:
            pass
        except (OSError, ValueError, UnicodeError):
            raise ImproperlyConfigured("Cannot load the private history LLM configuration.") from None
    return {
        "provider": environ.get("HISTORY_LLM_PROVIDER", private.get("provider", "gemini")),
        "api_key": environ.get("HISTORY_LLM_API_KEY", private.get("api_key", "")),
        "model": environ.get("HISTORY_LLM_MODEL", private.get("model", "")),
    }
