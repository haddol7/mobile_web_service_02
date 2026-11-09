#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_ENV="${YOLO_VENV:-$HOME/.venvs/mobile_web_service_02}"
if [[ -z "${WSL_DISTRO_NAME:-}" || "$TASK_ROOT" != /mnt/* ]]; then
    echo 'Use WSL2 Ubuntu with the source on the Windows drive.' >&2; exit 1
fi
task_kernel="$(uname -r)"
if [[ "${task_kernel,,}" != *wsl2* || "$(uname -m)" != x86_64 ]]; then
    echo 'This package requires x64 WSL2. Check wsl --list --verbose; do not use WSL1 or Windows Python.' >&2; exit 1
fi
action="${1:-Verify}"
if [[ "$action" == Setup ]]; then
    python3 -c 'import sys; assert sys.version_info >= (3,12), "Ubuntu 24.04 / Python 3.12 or newer required"'
    if [[ "$(id -u)" == 0 ]]; then
        echo 'Run as your ordinary Ubuntu user; the virtualenv belongs in that user home.' >&2; exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-dev build-essential libgl1 libglib2.0-0 libxcb-cursor0 v4l-utils usbutils
    PYTHON_EXECUTABLE=python3 bash "$TASK_ROOT/tools/setup_edge.sh"
    "$TASK_ENV/bin/python" -m pip install -r "$TASK_ROOT/YOLOv5/requirements-person.txt"
    "$TASK_ENV/bin/python" -m pip check
    "$TASK_ENV/bin/python" "$TASK_ROOT/laptop/runtime.py" verify
    echo 'Setup complete. Use START.cmd for sample, webcam and cloud access.'
    exit 0
fi
if [[ ! -x "$TASK_ENV/bin/python" ]]; then
    echo 'Project virtualenv missing. Run menu 1 (Setup) first.' >&2; exit 1
fi
case "$action" in
    Verify) exec "$TASK_ENV/bin/python" "$TASK_ROOT/laptop/runtime.py" verify ;;
    Sample) exec "$TASK_ENV/bin/python" "$TASK_ROOT/laptop/runtime.py" sample ;;
    Webcam) exec "$TASK_ENV/bin/python" "$TASK_ROOT/laptop/runtime.py" webcam --source "${2:-0}" ;;
    Monitor) exec "$TASK_ENV/bin/python" "$TASK_ROOT/laptop/runtime.py" monitor --source "${2:-0}" ;;
    Video) exec "$TASK_ENV/bin/python" "$TASK_ROOT/laptop/runtime.py" video --source "${2:?Video path required}" ;;
    LocalServer)
        export HISTORY_LLM_CONFIG='' HISTORY_LLM_PROVIDER='' HISTORY_LLM_API_KEY='' HISTORY_EMBEDDING_API_KEY=''
        export DJANGO_DB_PATH="$TASK_ROOT/.local/laptop/db.sqlite3"
        export DJANGO_MEDIA_ROOT="$TASK_ROOT/.local/laptop/media"
        export HISTORY_MEDIA_ROOT="$TASK_ROOT/.local/laptop/private_tracking"
        mkdir -p "$TASK_ROOT/.local/laptop"
        "$TASK_ENV/bin/python" "$TASK_ROOT/PhotoBlogServer/manage.py" migrate --noinput
        echo 'Local empty database. For a local owner account, run manage.py createsuperuser with these paths; see START_HERE.md.'
        exec "$TASK_ENV/bin/python" "$TASK_ROOT/PhotoBlogServer/manage.py" runserver 0.0.0.0:8020 --noreload ;;
    *) echo 'Unknown menu action.' >&2; exit 2 ;;
esac
