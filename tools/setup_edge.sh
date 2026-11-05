#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_ENV="${YOLO_VENV:-$HOME/.venvs/mobile_web_service_02}"
if [[ ! -x "$TASK_ENV/bin/python" ]]; then
    "${PYTHON_EXECUTABLE:-python3.12}" -m venv "$TASK_ENV"
fi
"$TASK_ENV/bin/python" -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
"$TASK_ENV/bin/python" -m pip install -r "$TASK_ROOT/YOLOv5/requirements-edge.txt" -r "$TASK_ROOT/PhotoBlogServer/requirements.txt"
"$TASK_ENV/bin/python" - "$TASK_ROOT" <<'PY'
import hashlib
from pathlib import Path
import sys
from urllib.request import urlopen
target = Path(sys.argv[1]) / 'YOLOv5/yolov5s.pt'
expected = '8b3b748c1e592ddd8868022e8732fde20025197328490623cc16c6f24d0782ee'
if not target.exists():
    data = urlopen('https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5s.pt', timeout=120).read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit('Unexpected model hash; no model saved.')
    target.write_bytes(data)
if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
    raise SystemExit('Existing model hash mismatch; inspect it before replacing.')
print('Official pretrained weights verified. No training is required.')
PY
"$TASK_ENV/bin/python" -m pip check
