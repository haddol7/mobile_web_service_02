import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock

import numpy as np
from face_features import unit_vector,reference_face,feature,load_policy,LEGACY_POLICY


def face(box,vector=(1.,0.,0.)):
    return SimpleNamespace(bbox=np.array(box,dtype=float),normed_embedding=np.array(vector,dtype=np.float32),
                           embedding=np.array(vector,dtype=np.float32),kps=np.zeros((5,2),dtype=np.float32))


class FaceFeatureTests(unittest.TestCase):
    def test_small_background_face_does_not_block_main_reference(self):
        main=face([40,10,160,180]);background=face([1,1,13,18])
        self.assertIs(reference_face([main,background],(224,224,3)),main)

    def test_dominant_foreground_can_be_selected_but_similar_faces_require_target(self):
        main=face([0,0,160,180]);background=face([180,10,205,40])
        self.assertIs(reference_face([main,background],(224,224,3)),main)
        other=face([100,10,220,180])
        self.assertIsNone(reference_face([main,other],(224,224,3)))

    def test_explicit_target_selects_one_reference_without_guessing(self):
        left=face([0,0,80,180]);right=face([120,0,210,180])
        self.assertIs(reference_face([left,right],(224,224,3),[.5,0,1,1]),right)
        self.assertIsNone(reference_face([left,right],(224,224,3),[0,0,1,1]))
        with self.assertRaises(ValueError):reference_face([left],(224,224,3),[1,0,0,1])

    def test_flip_features_use_original_and_sdk_flipped_embedding(self):
        model=Mock();model.get_feat.return_value=np.array([[0,2,0]],np.float32)
        app=SimpleNamespace(models={"recognition":model})
        image=np.arange(6*6*3,dtype=np.uint8).reshape(6,6,3)
        item=face([0,0,6,6],(2.,0.,0.))
        aligned=image.copy()
        with patch("insightface.utils.face_align.norm_crop",return_value=aligned):
            result=feature(app,item,image,"flip_mean")
        self.assertTrue(np.allclose(result,[2**-.5,2**-.5,0]))
        self.assertTrue(np.array_equal(model.get_feat.call_args.args[0],aligned[:,::-1]))
        self.assertAlmostEqual(float(np.linalg.norm(result)),1.,places=6)

    def test_invalid_features_and_unsupported_mode_fail(self):
        for value in [[0,0,0],[float("nan"),0,1],[[1,0],[0,1]]]:
            with self.assertRaises(ValueError):unit_vector(value)
        with self.assertRaises(ValueError):feature(None,None,None,"unknown")

    def test_policy_preserves_candidate_only_and_model_specific_contract(self):
        with TemporaryDirectory() as temporary:
            path=Path(temporary)/"policy.json"
            data={"schema_version":1,"version":"unit","model":"buffalo_l","threshold":.4,
                  "margin":.06,"embedding_mode":"flip_mean","automatic_confirmation_enabled":False}
            path.write_text(json.dumps(data))
            with patch("face_features.POLICY_PATH",path):
                self.assertEqual(load_policy("buffalo_l")["threshold"],.4)
                self.assertEqual(load_policy("buffalo_s"),LEGACY_POLICY)
                data["automatic_confirmation_enabled"]=True;path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):load_policy("buffalo_l")


if __name__=="__main__":
    unittest.main()
