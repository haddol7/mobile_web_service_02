"""Download the official pretrained face package and record actual CPU model readiness."""
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=['buffalo_s','buffalo_l'],default='buffalo_s')
    args=parser.parse_args()
    if platform.system() != 'Linux' or not os.environ.get('WSL_DISTRO_NAME'):
        raise SystemExit('Run in the project WSL virtualenv.')
    sys.path.insert(0, str(ROOT / 'YOLOv5'))
    from person_tracking import create_face_app
    app = create_face_app(args.model)
    directory = Path.home() / '.insightface/models' / args.model
    files = [{'name':path.name, 'bytes':path.stat().st_size,
              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(directory.glob('*.onnx'))]
    providers = {name:model.session.get_providers() for name,model in app.models.items()}
    assert {'detection','recognition'} <= set(providers)
    assert all(value == ['CPUExecutionProvider'] for value in providers.values())
    result = {'verified_utc':datetime.now(timezone.utc).isoformat(), 'environment':'WSL Ubuntu CPU',
              'packages':{name:importlib.metadata.version(name) for name in [
                  'norfair','supervision','insightface','onnxruntime','onnx','opencv-python','numpy']},
              'face_model':args.model, 'model_files':files, 'providers':providers,
              'models_loaded':True, 'training_performed':False,
              'source':'https://github.com/deepinsight/insightface/releases/tag/model-zoo',
              'model_terms':'InsightFace supplied pretrained models: non-commercial research',
              'identity_accuracy_measured':False, 'production_changed':False}
    output = ROOT / 'evidence/person-libraries'
    output.mkdir(parents=True, exist_ok=True)
    (output / ('environment-'+args.model+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
