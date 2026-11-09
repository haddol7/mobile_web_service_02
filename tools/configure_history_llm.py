"""Import a user-approved OpenAI key into private WSL settings, never into the source tree."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import tempfile


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in the project WSL environment.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-env", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", args.model):
        raise SystemExit("Invalid model identifier.")
    try:
        raw = args.source_env.read_text(encoding="utf-8-sig")
        match = re.search(r"^\s*(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*?)\s*$", raw, re.M)
        key = match.group(1).strip().strip('"').strip("'") if match else ""
        if not re.fullmatch(r"sk-[A-Za-z0-9_-]{16,}", key):
            raise ValueError
    except (OSError, ValueError, UnicodeError):
        raise SystemExit("Cannot read an OpenAI key from the approved source file.") from None
    directory = Path.home() / ".config/mobile-web-service/common02"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    target = directory / "llm.json"
    handle, temporary = tempfile.mkstemp(prefix=".llm-", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump({"provider": "openai", "model": args.model, "api_key": key}, output)
            output.write("\n")
        os.replace(temporary, target)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
    print(json.dumps({"configured": True, "provider": "openai", "model": args.model,
                      "file_mode": oct(target.stat().st_mode & 0o777), "key_printed": False}))


if __name__ == "__main__":
    main()
