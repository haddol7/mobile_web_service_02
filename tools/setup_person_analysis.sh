#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${WSL_DISTRO_NAME:-}" ]]; then
    echo 'Run this setup inside WSL Ubuntu.' >&2
    exit 1
fi
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_ENV="${YOLO_VENV:-$HOME/.venvs/mobile_web_service_02}"
"$TASK_ENV/bin/python" -m pip install -r "$TASK_ROOT/YOLOv5/requirements-person.txt"
"$TASK_ENV/bin/python" -m pip check
"$TASK_ENV/bin/python" "$TASK_ROOT/tools/prepare_person_models.py"
