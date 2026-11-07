"""Adapt existing YOLOv5 boxes to Norfair, Supervision and optional InsightFace.

Track IDs describe one stream session. Face matches are candidates, not confirmed
identities or real visit counts. No model training or server writes occur here.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

import cv2
import numpy as np
from norfair import Detection, Tracker
import supervision as sv


def create_face_app(model='buffalo_s', root='~/.insightface'):
    import onnxruntime as ort
    from insightface.app import FaceAnalysis

    if model not in {'buffalo_s', 'buffalo_l'}:
        raise ValueError('Use a documented pretrained Buffalo face package')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    app = FaceAnalysis(name=model, root=str(Path(root).expanduser()),
                       allowed_modules=['detection', 'recognition'],
                       providers=['CPUExecutionProvider'], sess_options=options)
    # SDK Auto combines 128 and 640 inputs, covering tight face crops as well as distant faces.
    app.prepare(ctx_id=-1, det_thresh=0.5)
    return app


class FaceReferences:
    """Use the SDK's pretrained embeddings for explicitly supplied references."""
    def __init__(self, manifest, *, model='buffalo_s', root='~/.insightface',
                 threshold=0.55, margin=0.08):
        if not 0 <= threshold <= 1 or not 0 <= margin <= 1:
            raise ValueError('Invalid experimental face thresholds')
        manifest = Path(manifest).resolve()
        content = json.loads(manifest.read_text(encoding='utf-8'))
        if content.get('schema_version') != 1 or not content.get('profiles'):
            raise ValueError('Expected schema_version 1 and nonempty profiles')
        self.app = create_face_app(model, root)
        self.threshold, self.margin = threshold, margin
        self.references = {}
        self.rejected_references = []
        for profile in content['profiles']:
            identity = profile['id']
            if not isinstance(identity, str) or not identity or identity in self.references:
                raise ValueError('Reference IDs must be unique nonempty strings')
            vectors = []
            for filename in profile['images']:
                image = cv2.imread(str(manifest.parent / filename))
                if image is None:
                    raise ValueError('Reference image could not be read')
                faces = self.app.get(image)
                if len(faces) != 1:
                    self.rejected_references.append({'profile_id':identity,'image':filename,
                        'reason':'no_face' if not faces else 'multiple_faces'})
                    continue
                vector = np.asarray(faces[0].normed_embedding, dtype=np.float32)
                if not np.isfinite(vector).all() or np.linalg.norm(vector) < 0.99:
                    raise ValueError('Reference feature is invalid')
                vectors.append(vector)
            if not vectors:
                raise ValueError('Each profile requires at least one reference image')
            self.references[identity] = np.stack(vectors)
        self.registration = {'profiles':len(self.references),
                             'accepted_images':sum(len(value) for value in self.references.values()),
                             'rejected_images':len(self.rejected_references)}

    def match_embedding(self, vector):
        vector = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if not np.isfinite(vector).all() or norm == 0:
            raise ValueError('Invalid face feature')
        vector = vector / norm
        ranked = sorted(((float((samples @ vector).max()), identity)
                         for identity, samples in self.references.items()), reverse=True)
        score, identity = ranked[0]
        gap = score - ranked[1][0] if len(ranked) > 1 else score + 1.0
        accepted = score >= self.threshold and gap >= self.margin
        return {'candidate_profile_id': identity if accepted else None,
                'similarity': score, 'margin': gap,
                'status': 'candidate' if accepted else 'unresolved'}

    def analyze(self, frame):
        records = []
        for face in self.app.get(frame):
            box = np.asarray(face.bbox, dtype=float)
            if min(box[2] - box[0], box[3] - box[1]) < 20:
                continue
            records.append({'bbox': box.tolist(), 'detection_score': float(face.det_score),
                            **self.match_embedding(face.normed_embedding)})
        return records


class PersonTracker:
    """One tracker and one counting state per source, consuming original-image boxes."""
    def __init__(self, *, line=None, face_references=None, face_stride=10,
                 initialization_delay=2, hit_counter_max=15):
        if face_stride < 1:
            raise ValueError('face_stride must be positive')
        if line is not None and (len(line) != 4 or not np.isfinite(line).all()
                                 or any(not 0 <= value <= 1 for value in line)
                                 or tuple(line[:2]) == tuple(line[2:])):
            raise ValueError('Line must have two distinct normalized points')
        self.line_config = line
        self.zone = None
        self.geometry = None
        self.faces = face_references
        self.face_stride = face_stride
        self.session_id = uuid4().hex
        self.tracker = Tracker(distance_function='iou', distance_threshold=0.7,
                               initialization_delay=initialization_delay,
                               hit_counter_max=hit_counter_max, detection_threshold=0.25)
        self.boxes = sv.BoxAnnotator(thickness=2, color_lookup=sv.ColorLookup.TRACK)
        self.labels = sv.LabelAnnotator(text_scale=0.5, text_padding=3,
                                        color_lookup=sv.ColorLookup.TRACK)
        self.line_annotator = sv.LineZoneAnnotator(text_scale=0.5, text_padding=3)

    def process(self, frame, boxes, *, frame_index, video_seconds=None, annotation_frame=None):
        started = time.perf_counter()
        rows = np.asarray(boxes, dtype=float)
        if rows.size == 0:
            rows = np.empty((0, 6), dtype=float)
        if rows.ndim != 2 or rows.shape[1] != 6 or not np.isfinite(rows).all():
            raise ValueError('Expected finite YOLO xyxy, confidence, class rows')
        if len(rows) and ((rows[:, 4] < 0).any() or (rows[:, 4] > 1).any()):
            raise ValueError('Detection confidence must be between zero and one')
        geometry = frame.shape[:2]
        if self.geometry is not None and geometry != self.geometry:
            raise ValueError('Start a new tracker when source geometry changes')
        self.geometry = geometry
        if self.zone is None and self.line_config is not None:
            height, width = geometry
            x1, y1, x2, y2 = self.line_config
            self.zone = sv.LineZone(sv.Point(x1 * width, y1 * height),
                                    sv.Point(x2 * width, y2 * height),
                                    triggering_anchors=[sv.Position.BOTTOM_CENTER],
                                    minimum_crossing_threshold=2,
                                    max_absent_frames=30)
        detections = []
        for x1, y1, x2, y2, confidence, label in rows:
            if int(label) != 0 or x2 <= x1 or y2 <= y1:
                continue
            detections.append(Detection(points=np.array([[x1, y1], [x2, y2]]),
                scores=np.array([confidence, confidence]), label=0,
                data={'frame_index': frame_index, 'confidence': float(confidence)}))
        objects = self.tracker.update(detections=detections)
        # Unobserved Kalman predictions cannot create a crossing or a face association.
        fresh = [obj for obj in objects if obj.last_detection.data['frame_index'] == frame_index]
        xyxy = np.array([obj.estimate.reshape(4) for obj in fresh], dtype=np.float32).reshape(-1, 4)
        ids = np.array([obj.id for obj in fresh], dtype=np.int64)
        tracked = sv.Detections(xyxy=xyxy, confidence=np.array([
            obj.last_detection.data['confidence'] for obj in fresh], dtype=np.float32),
            class_id=np.zeros(len(fresh), dtype=np.int64), tracker_id=ids)
        face_records = self.faces.analyze(frame) if self.faces and frame_index % self.face_stride == 0 else []
        for face in face_records:
            fx1, fy1, fx2, fy2 = face['bbox']
            cx, cy = (fx1 + fx2) / 2, (fy1 + fy2) / 2
            owners = [int(identity) for identity, (x1, y1, x2, y2) in zip(ids, xyxy)
                      if x1 <= cx <= x2 and y1 <= cy <= y2]
            face['body_track_id'] = owners[0] if len(owners) == 1 else None
        crossings = []
        if self.zone is not None:
            entered, exited = self.zone.trigger(tracked)
            for identity, did_enter, did_exit in zip(ids, entered, exited):
                for direction, happened in [('in', did_enter), ('out', did_exit)]:
                    if happened:
                        key = f'{self.session_id}:{int(identity)}:{frame_index}:{direction}'
                        crossings.append({'event_id': hashlib.sha256(key.encode()).hexdigest(),
                                          'track_id': int(identity), 'direction': direction})
        scene = frame if annotation_frame is None else annotation_frame
        output = self.boxes.annotate(scene=scene.copy(), detections=tracked)
        output = self.labels.annotate(scene=output, detections=tracked,
                                      labels=[f'track {identity}' for identity in ids])
        for face in face_records:
            x1, y1, x2, y2 = map(int, face['bbox'])
            cv2.rectangle(output, (x1, y1), (x2, y2), (50, 170, 240), 2)
            label = face['candidate_profile_id'] or 'unresolved'
            cv2.putText(output, str(label), (max(0, x1), max(14, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (50, 170, 240), 1)
        if self.zone is not None:
            output = self.line_annotator.annotate(frame=output, line_counter=self.zone)
        record = {'session_id': self.session_id, 'frame_index': int(frame_index),
                  'video_seconds': video_seconds,
                  'processed_at_utc': datetime.now(timezone.utc).isoformat(),
                  'tracks': [{'track_id': int(identity), 'bbox': box.tolist()}
                             for identity, box in zip(ids, xyxy)],
                  'faces': face_records, 'crossings': crossings,
                  'line_in_count': self.zone.in_count if self.zone else 0,
                  'line_out_count': self.zone.out_count if self.zone else 0,
                  'processing_seconds': time.perf_counter() - started}
        return output, record
