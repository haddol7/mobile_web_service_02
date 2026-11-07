from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from person_tracking import FaceReferences, PersonTracker


class TrackingIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((120, 200, 3), dtype=np.uint8)

    def test_actual_tracker_keeps_id_and_counts_one_crossing(self):
        tracker = PersonTracker(line=[0.5, 0, 0.5, 1])
        seen = set(); events = []
        for i, x in enumerate(list(range(20, 161, 5)) + [160] * 8):
            _, record = tracker.process(self.frame, [[x, 20, x + 30, 100, 0.9, 0]], frame_index=i)
            seen.update(row['track_id'] for row in record['tracks'])
            events.extend(record['crossings'])
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(record['line_in_count'] + record['line_out_count'], 1)
        self.assertEqual(len(events[0]['event_id']), 64)

    def test_unobserved_predictions_do_not_count(self):
        tracker = PersonTracker(line=[0.5, 0, 0.5, 1], initialization_delay=0)
        for i, x in enumerate([30, 40, 50]):
            tracker.process(self.frame, [[x, 20, x + 30, 100, 0.9, 0]], frame_index=i)
        for i in range(3, 15):
            _, record = tracker.process(self.frame, [], frame_index=i)
            self.assertEqual(record['tracks'], [])
            self.assertEqual(record['crossings'], [])

    def test_stream_sessions_do_not_share_counts(self):
        first = PersonTracker(); second = PersonTracker()
        self.assertNotEqual(first.session_id, second.session_id)
        _, record = second.process(self.frame, [], frame_index=1)
        self.assertEqual(record['line_in_count'], 0)

    def test_other_object_classes_are_not_people(self):
        tracker = PersonTracker(initialization_delay=0)
        _, record = tracker.process(self.frame, [[10, 10, 80, 90, 0.99, 2]], frame_index=1)
        self.assertEqual(record['tracks'], [])

    def test_invalid_geometry_and_input_rejected(self):
        with self.assertRaises(ValueError):
            PersonTracker(line=[0.5, 0.5, 0.5, 0.5])
        tracker = PersonTracker()
        with self.assertRaises(ValueError):
            tracker.process(self.frame, [[0, 0, 10, 10, np.nan, 0]], frame_index=1)
        tracker.process(self.frame, [], frame_index=1)
        with self.assertRaises(ValueError):
            tracker.process(np.zeros((60, 100, 3), np.uint8), [], frame_index=2)

    def test_existing_object_annotations_preserved(self):
        annotation = self.frame.copy(); annotation[2, 2] = [20, 40, 60]
        output, _ = PersonTracker().process(self.frame, [], frame_index=1, annotation_frame=annotation)
        self.assertTrue(np.array_equal(output[2, 2], [20, 40, 60]))
        self.assertFalse(self.frame.any())

    def test_face_between_overlapping_bodies_is_not_forcibly_assigned(self):
        class Faces:
            def analyze(self, frame):
                return [{'bbox':[55, 20, 65, 40], 'candidate_profile_id':'reference-a',
                         'status':'candidate', 'similarity':0.9, 'margin':0.3}]
        tracker = PersonTracker(face_references=Faces(), face_stride=1, initialization_delay=0)
        _, record = tracker.process(self.frame,
            [[10, 0, 100, 115, 0.9, 0], [40, 0, 140, 115, 0.9, 0]], frame_index=1)
        self.assertEqual(len(record['tracks']), 2)
        self.assertIsNone(record['faces'][0]['body_track_id'])
        self.assertEqual(record['faces'][0]['status'], 'candidate')


class FaceCandidateTests(unittest.TestCase):
    def test_bad_reference_is_reported_and_valid_reference_retained(self):
        fake=SimpleNamespace(get=lambda image:[] if int(image[0,0,0])==0 else [
            SimpleNamespace(normed_embedding=np.array([1,0,0],np.float32))])
        import cv2
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            cv2.imwrite(str(folder/'bad.png'),np.zeros((32,32,3),np.uint8))
            cv2.imwrite(str(folder/'good.png'),np.ones((32,32,3),np.uint8))
            manifest=folder/'references.json'
            manifest.write_text(json.dumps({'schema_version':1,'profiles':[
                {'id':'a','images':['bad.png','good.png']}]}))
            with patch('person_tracking.create_face_app',return_value=fake):
                matcher=FaceReferences(manifest)
            self.assertEqual(matcher.registration,{'profiles':1,'accepted_images':1,'rejected_images':1})
            self.assertEqual(matcher.rejected_references[0]['reason'],'no_face')

    def matcher(self, references):
        matcher = FaceReferences.__new__(FaceReferences)
        matcher.references = {key:np.array(value,dtype=np.float32) for key,value in references.items()}
        matcher.threshold, matcher.margin = 0.55, 0.08
        return matcher

    def test_multiple_references_for_one_person_are_not_runners_up(self):
        matcher = self.matcher({'a':[[1,0,0],[0.99,0.01,0]],'b':[[0,1,0]]})
        result = matcher.match_embedding([1,0,0])
        self.assertEqual(result['candidate_profile_id'], 'a')
        self.assertEqual(result['status'], 'candidate')
        self.assertGreater(result['margin'], 0.9)

    def test_unknown_and_ambiguous_faces_are_unresolved(self):
        matcher = self.matcher({'a':[[1,0,0]],'b':[[0,1,0]]})
        self.assertIsNone(matcher.match_embedding([0,0,1])['candidate_profile_id'])
        self.assertIsNone(matcher.match_embedding([1,1,0])['candidate_profile_id'])

    def test_invalid_features_rejected(self):
        matcher = self.matcher({'a':[[1,0,0]]})
        for value in [[0,0,0],[np.nan,0,1]]:
            with self.assertRaises(ValueError): matcher.match_embedding(value)


if __name__ == '__main__':
    unittest.main()
