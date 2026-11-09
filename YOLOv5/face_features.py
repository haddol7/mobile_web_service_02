"""Reuse InsightFace alignment and recognition, with explicit scoring policy."""
import hashlib
import json
from pathlib import Path

import numpy as np

POLICY_PATH = Path(__file__).with_name("face_policy.json")
LEGACY_POLICY = {"version":"legacy-1","threshold":.55,"margin":.08,"embedding_mode":"single"}


def unit_vector(value):
    value=np.asarray(value,dtype=np.float32)
    if value.ndim!=1 or not np.isfinite(value).all() or np.linalg.norm(value)==0:
        raise ValueError("Invalid face feature")
    return value/np.linalg.norm(value)


def load_policy(model):
    if not POLICY_PATH.is_file():
        return dict(LEGACY_POLICY)
    policy=json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("model")!=model:
        return dict(LEGACY_POLICY)
    if policy.get("schema_version")!=1 or policy.get("embedding_mode") not in {"single","flip_mean"}:
        raise ValueError("Invalid face policy")
    for key in ["threshold","margin"]:
        value=policy.get(key)
        if type(value) not in (int,float) or not np.isfinite(value) or not 0<=value<=1:
            raise ValueError("Invalid face policy threshold")
    if not policy.get("version") or policy.get("automatic_confirmation_enabled") is not False:
        raise ValueError("Face policy must preserve candidate-only matching")
    return policy


def verify_policy_model(app,policy):
    expected=policy.get("recognizer_sha256")
    if expected:
        path=Path(app.models["recognition"].model_file)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError("Calibrated face policy does not match the loaded model")


def eligible_faces(faces,min_size=20):
    result=[]
    for face in faces:
        box=np.asarray(face.bbox,dtype=float)
        if box.shape!=(4,) or not np.isfinite(box).all():
            continue
        if min(box[2]-box[0],box[3]-box[1])>=min_size:
            result.append(face)
    return result


def reference_face(faces,image_shape,target=None):
    candidates=eligible_faces(faces)
    if target is not None:
        target=np.asarray(target,dtype=float)
        if target.shape!=(4,) or not np.isfinite(target).all() or (target<0).any() or (target>1).any() or target[2]<=target[0] or target[3]<=target[1]:
            raise ValueError("Reference target must be a normalized positive box")
        h,w=image_shape[:2]
        left,top,right,bottom=target*np.array([w,h,w,h])
        candidates=[f for f in candidates if left<=(f.bbox[0]+f.bbox[2])/2<=right
                    and top<=(f.bbox[1]+f.bbox[3])/2<=bottom]
    if len(candidates)==1:
        return candidates[0]
    if target is None and len(candidates)>1:
        ordered=sorted(candidates,key=lambda f:(f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]),reverse=True)
        area=lambda f:(f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1])
        if area(ordered[0])>=4*area(ordered[1]):
            return ordered[0]
    return None


def feature(app,face,image,mode="single"):
    if mode=="single":
        return unit_vector(face.normed_embedding)
    if mode!="flip_mean":
        raise ValueError("Unsupported face embedding mode")
    from insightface.utils.face_align import norm_crop
    aligned=norm_crop(image,landmark=face.kps,image_size=112)
    flipped=np.ascontiguousarray(aligned[:,::-1])
    other=app.models["recognition"].get_feat(flipped).reshape(-1)
    return unit_vector(np.asarray(face.embedding,dtype=np.float32)+other)


def rank_references(references,vector):
    vector=unit_vector(vector)
    if not references:
        raise ValueError("No enrolled face references")
    return sorted(((float((samples@vector).max()),identity) for identity,samples in references.items()),reverse=True)
