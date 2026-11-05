"""Preserve actual WSL unit-test output and the source hashes it verifies."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
if platform.system() != 'Linux' or not os.environ.get('WSL_DISTRO_NAME'):
    raise SystemExit('Run in the WSL project virtual environment.')
out = root / 'evidence/edge-tests'
out.mkdir(parents=True, exist_ok=True)
files = ['YOLOv5/changedetection.py', 'YOLOv5/detect.py', 'YOLOv5/tests/test_changedetection.py', 'tools/run_edge.py']
hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_changedetection.py', '-v']
run = subprocess.run(command, cwd=root/'YOLOv5', capture_output=True, text=True, timeout=60)
(out/'unit-tests.txt').write_text(run.stdout+run.stderr, encoding='utf-8')
stable = hashes == {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
record = {'verified_utc': datetime.now(timezone.utc).isoformat(), 'environment': 'WSL Ubuntu',
          'command': command, 'source_sha256': hashes, 'source_stable': stable,
          'tests': 8, 'exit_code': run.returncode, 'pass': stable and run.returncode == 0 and 'Ran 8 tests' in run.stderr}
(out/'verification.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({'tests':8,'pass':record['pass']}))
raise SystemExit(0 if record['pass'] else 1)
