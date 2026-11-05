"""Launch the original or assessed detector in WSL with the pinned trusted weights."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', action='store_true', help='Run the byte-identical upstream detect.py')
args, detector_args = parser.parse_known_args()
if platform.system() != 'Linux' or not os.environ.get('WSL_DISTRO_NAME'):
    raise SystemExit('Run in the WSL project virtual environment.')
weights = root / 'YOLOv5/yolov5s.pt'
if not weights.is_file() or hashlib.sha256(weights.read_bytes()).hexdigest() != '8b3b748c1e592ddd8868022e8732fde20025197328490623cc16c6f24d0782ee':
    raise SystemExit('Expected official YOLOv5 v7.0 yolov5s.pt weights are missing or changed.')
script = root / ('YOLOv5/baseline/detect.py' if args.baseline else 'YOLOv5/detect.py')
if args.baseline:
    provenance = json.loads((root / 'docs/upstream/provenance.json').read_text())
    if hashlib.sha256(script.read_bytes()).hexdigest() != provenance['detect_sha256']:
        raise SystemExit('The upstream baseline has changed.')
# torch 2.6 changed the default loader. This applies only after checking the trusted release hash.
env = dict(os.environ, TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='1', PYTHONPATH=str(root / 'YOLOv5'))
command = [sys.executable, str(script), '--weights', str(weights), '--data', str(root / 'YOLOv5/data/coco128.yaml'), *detector_args]
raise SystemExit(subprocess.call(command, cwd=root / 'YOLOv5', env=env))
