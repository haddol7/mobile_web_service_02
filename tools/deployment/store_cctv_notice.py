"""Retain the original research licence beside private cloud derivatives."""
import hashlib,json,os
from pythonanywhere_deploy import API,BASE,WORKSPACE
import pythonanywhere_auth as auth

assert os.environ.get('WSL_DISTRO_NAME'),'Use WSL'
raw=(WORKSPACE/'docs/testing/licenses/ChokePoint.txt').read_bytes()
api=API(auth.load_credentials())
path=BASE+'/shared/private_tracking/CHOKEPOINT_LICENSE.txt'
api.file(path,raw)
assert hashlib.sha256(api.file(path)).digest()==hashlib.sha256(raw).digest()
print(json.dumps({'pass':True,'original_licence_retained_with_private_cloud_derivatives':True}))
