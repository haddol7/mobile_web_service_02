import unittest
from chokepoint_identity import ground_truth_identity,dataset_track_identity


class IdentityEvidenceTests(unittest.TestCase):
    def test_both_eyes_are_required_and_background_face_has_no_label(self):
        people=[{"identity":"0001","eyes":[(15,15),(25,15)]}]
        self.assertEqual(ground_truth_identity([10,10,30,30],people),"0001")
        self.assertIsNone(ground_truth_identity([10,10,20,30],people))
        self.assertIsNone(ground_truth_identity([40,40,60,60],people))

    def test_two_subjects_inside_one_box_are_ambiguous(self):
        people=[{"identity":key,"eyes":[(10,10),(20,10)]} for key in ("0001","0002")]
        self.assertIsNone(ground_truth_identity([0,0,30,30],people))

    def test_repeated_concordant_annotations_can_confirm_matching_model_candidate(self):
        self.assertEqual(dataset_track_identity(["0001",None,"0001"],"chokepoint-0001"),"0001")

    def test_id_switch_wrong_candidate_and_single_annotation_cannot_confirm(self):
        self.assertIsNone(dataset_track_identity(["0001","0002","0001"],"chokepoint-0001"))
        self.assertIsNone(dataset_track_identity(["0001","0001"],"chokepoint-0002"))
        self.assertIsNone(dataset_track_identity([None,"0001"],"chokepoint-0001"))
        self.assertIsNone(dataset_track_identity([None,None],None))


if __name__=="__main__":
    unittest.main()
