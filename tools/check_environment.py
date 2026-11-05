"""Record the actual WSL inference/runtime setup without printing credentials."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

if platform.system()!='Linux' or not os.environ.get('WSL_DISTRO_NAME'):
    raise SystemExit('Run inside the WSL project virtual environment.')
root=Path(__file__).resolve().parents[1]
import cv2
import torch
import django
expected='8b3b748c1e592ddd8868022e8732fde20025197328490623cc16c6f24d0782ee'
weights=root/'YOLOv5/yolov5s.pt'
packages=['torch','torchvision','numpy','opencv-python','Django','djangorestframework','pillow','requests']
check=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True,timeout=45)
record={'verified_utc':datetime.now(timezone.utc).isoformat(),'environment':'WSL '+os.environ['WSL_DISTRO_NAME'],
        'python':platform.python_version(),'virtualenv':sys.prefix,'source_tree':str(root),
        'packages':{name:importlib.metadata.version(name) for name in packages},
        'opencv_imported':True,'torch_cpu_tensor_ok':bool(torch.tensor([1,2,3]).sum().item()==6),
        'weights_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),
        'video_devices':[str(path) for path in Path('/dev').glob('video*')],
        'pip_check_exit_code':check.returncode,'pip_check_output':check.stdout.strip()}
record['pass']=check.returncode==0 and record['weights_sha256']==expected and record['torch_cpu_tensor_ok']
out=root/'evidence/environment';out.mkdir(parents=True,exist_ok=True)
(out/'wsl-runtime.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
freeze=subprocess.run([sys.executable,'-m','pip','freeze'],capture_output=True,text=True,check=True)
(out/'wsl-installed.txt').write_text(freeze.stdout,encoding='utf-8')
print(json.dumps(record,indent=2))
raise SystemExit(0 if record['pass'] else 1)
