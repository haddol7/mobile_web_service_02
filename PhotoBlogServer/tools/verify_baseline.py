"""Reproduce WSL backend checks and preserve actual subprocess output as evidence."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


SERVER_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = SERVER_ROOT.parent / "evidence" / "baseline"


def source_hashes():
    files = [SERVER_ROOT / "requirements.txt", SERVER_ROOT / ".coveragerc"]
    files.extend(SERVER_ROOT.glob("*.py"))
    for package in ("blog", "photoblog", "tools"):
        files.extend(path for path in (SERVER_ROOT / package).rglob("*") if path.is_file() and path.suffix in (".py", ".html", ".mjs", ".css", ".js", ".json", ".wasm", ".tflite", ".gz", ".txt"))
    return {
        str(path.relative_to(SERVER_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(set(files))
    }


def redact_secrets(text):
    # Failed assertions may include a temporary 40-hex DRF token. Never persist it.
    text = re.sub(r"\b[a-fA-F0-9]{40}\b", "[REDACTED_TOKEN]", text)
    return re.sub(r'(?i)([\"\']?(?:password|token)[\"\']?\s*[:=]\s*)[\"\'][^\"\']*[\"\']', r'\1"[REDACTED]"', text)


def main():
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Backend validation must run inside WSL, not Windows Python.")
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    hashes_before = source_hashes()
    python = sys.executable
    steps = [
        ("django-check", [python, "manage.py", "check"]),
        ("migration-consistency", [python, "manage.py", "makemigrations", "--check", "--dry-run"]),
        ("tests-coverage", [python, "-m", "coverage", "run", "manage.py", "test", "--verbosity", "2"]),
        ("coverage-report", [python, "-m", "coverage", "report"]),
        ("coverage-html", [python, "-m", "coverage", "html"]),
        ("coverage-json", [python, "-m", "coverage", "json", "-o", "htmlcov/coverage.json"]),
        ("http-api-engine", [python, "api_test_engine.py"]),
    ]
    results = []
    for name, command in steps:
        print(f"Running: {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=SERVER_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        output = redact_secrets(result.stdout + result.stderr)
        log = (
            f"ACTUAL WSL SUBPROCESS OUTPUT: {name}\n"
            f"Run started UTC: {started}\nWSL: {os.environ['WSL_DISTRO_NAME']}\n"
            f"Working directory: {SERVER_ROOT}\nCommand: {' '.join(command)}\n"
            "Credential-like values are redacted if present; no terminal screenshot is fabricated.\n\n"
            + output + f"\nExit code: {result.returncode}\n"
        )
        path = EVIDENCE_ROOT / f"{name}.txt"
        path.write_text(log, encoding="utf-8")
        print(output, flush=True)
        results.append({"name": name, "command": command, "exit_code": result.returncode, "log": str(path.relative_to(SERVER_ROOT.parent))})
        if result.returncode:
            break
    hashes_after = source_hashes()
    metadata = {
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "environment": "WSL " + os.environ["WSL_DISTRO_NAME"],
        "python": python,
        "results": results,
        "source_sha256": hashes_before,
        "source_changed_during_validation": hashes_before != hashes_after,
        "pass": len(results) == len(steps) and all(item["exit_code"] == 0 for item in results) and hashes_before == hashes_after,
    }
    coverage_path = SERVER_ROOT / "htmlcov" / "coverage.json"
    if coverage_path.exists():
        metadata["coverage_totals"] = json.loads(coverage_path.read_text(encoding="utf-8"))["totals"]
    destination = EVIDENCE_ROOT / "verification.json"
    destination.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Actual verification manifest: {destination}", flush=True)
    raise SystemExit(0 if metadata["pass"] else 1)


if __name__ == "__main__":
    main()
