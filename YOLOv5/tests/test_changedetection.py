import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from changedetection import ChangeDetection, UploadError


class AppearanceTests(unittest.TestCase):
    def detector(self):
        instance = ChangeDetection(["person", "cat", "dog"], base_url="http://127.0.0.1:8012", token="test-only-token")
        instance.send = Mock(return_value={"post_id": 1})
        return instance

    def test_first_appearance_persistence_absence_and_reappearance(self):
        cd = self.detector()
        for flags in ([0, 0, 0], [1, 0, 0], [1, 0, 0], [0, 0, 0], [1, 0, 0]):
            cd.add(None, flags, ".", None)
        self.assertEqual(cd.send.call_count, 2)
        self.assertEqual(cd.send.call_args.args[2], [0])

    def test_new_classes_are_grouped_in_one_post(self):
        cd = self.detector()
        cd.add(None, [1, 1, 0], ".", None)
        cd.send.assert_called_once_with(".", None, [0, 1])

    def test_removed_class_does_not_generate_upload(self):
        cd = self.detector()
        cd.add(None, [1, 1, 0], ".", None)
        cd.add(None, [1, 0, 0], ".", None)
        self.assertEqual(cd.send.call_count, 1)

    def test_streams_and_instances_do_not_share_presence(self):
        cd = self.detector()
        cd.add(None, [1, 0, 0], ".", None, stream_id="a")
        cd.add(None, [1, 0, 0], ".", None, stream_id="b")
        other = self.detector()
        other.add(None, [1, 0, 0], ".", None)
        self.assertEqual(cd.send.call_count, 2)
        self.assertEqual(other.send.call_count, 1)

    def test_invalid_vector_is_rejected_without_advancing(self):
        cd = self.detector()
        with self.assertRaises(ValueError):
            cd.add(None, [1], ".", None)
        self.assertEqual(cd._previous, {})

    def test_credentials_in_url_and_plain_remote_http_are_rejected(self):
        for url in ("http://example.com", "https://user:password@example.com", "https://example.com/?token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                ChangeDetection(["person"], base_url=url, token="test-only-token")

    def test_photo_file_is_closed_and_real_encoded_jpeg_is_sent(self):
        import numpy as np
        import cv2
        session = Mock()
        response = Mock(status_code=201)
        response.json.return_value = {"id": 42}
        session.post.return_value = response
        captured = {}
        def inspect(*args, **kwargs):
            captured["file"] = kwargs["files"]["image"][1]
            image = cv2.imdecode(np.frombuffer(captured["file"].read(), dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertEqual(image.shape[:2], (240, 320))
            self.assertEqual(kwargs["headers"]["Authorization"], "Token test-only-token")
            self.assertFalse(kwargs["allow_redirects"])
            return response
        session.post.side_effect = inspect
        cd = ChangeDetection(["person"], base_url="http://localhost:8012", token="test-only-token", session=session)
        with tempfile.TemporaryDirectory() as folder:
            result = cd.add(None, [1], folder, np.zeros((90, 100, 3), dtype=np.uint8))
            self.assertEqual(result["post_id"], 42)
            self.assertTrue(Path(result["local_image"]).is_file())
        self.assertTrue(captured["file"].closed)

    def test_failed_registration_keeps_the_frame_and_does_not_claim_success(self):
        import numpy as np
        session = Mock()
        session.post.return_value.status_code = 403
        cd = ChangeDetection(["person"], base_url="http://localhost:8012", token="test-only-token", session=session)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(UploadError):
                cd.add(None, [1], folder, np.zeros((30, 30, 3), dtype=np.uint8))
            self.assertEqual(len(list(Path(folder).rglob("*.jpg"))), 1)


if __name__ == "__main__":
    unittest.main()
