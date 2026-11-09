"""Boundary tests for portable packaging and local-only launch commands."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load("laptop_runtime", HERE / "runtime.py")
builder = load("laptop_builder", HERE.parent / "tools/build_laptop_bundle.py")


class TransferTests(unittest.TestCase):
    def test_secrets_caches_and_database_are_excluded(self):
        for path in ("PhotoBlogServer/.env", "PhotoBlogServer/.env.local", "PhotoBlogServer/db.sqlite3-wal",
                     "PhotoViewer/local.properties", "PhotoViewer/app/build/output.apk", "tools/private/credentials.json",
                     ".git/config", "YOLOv5/runs/frame.jpg", "laptop/MANIFEST.json", "laptop/data/references.json",
                     "PhotoBlogServer/site.pem", "laptop/models/buffalo_l/det_10g.onnx"):
            with self.subTest(path=path):
                self.assertFalse(builder.allowed(path))

    def test_current_source_and_yolo_weight_are_included(self):
        for path in ("YOLOv5/face_features.py", "YOLOv5/yolov5s.pt", "PhotoViewer/app/src/main/assets/model.tflite",
                     "PhotoBlogServer/blog/history_api.py", "laptop/run.sh"):
            self.assertTrue(builder.allowed(path))

    def test_sample_has_no_server_or_history_upload(self):
        with patch.dict(runtime.os.environ, {}, clear=True):
            cmd = runtime.command("sample", "0", HERE.parent)
        self.assertNotIn("--server", cmd)
        self.assertNotIn("--person-history", cmd)
        self.assertNotIn("--view-img", cmd)
        self.assertIn("--face-references", cmd)

    def test_assessed_webcam_uses_unchanged_baseline_and_real_index(self):
        cmd = runtime.command("webcam", "0", HERE.parent)
        self.assertIn("--baseline", cmd)
        self.assertEqual(cmd[cmd.index("--source") + 1], "0")
        self.assertNotIn("--server", cmd)
        self.assertNotIn("--person-tracking", cmd)

    def test_live_monitor_upload_is_explicit(self):
        cmd = runtime.command("monitor", "0", HERE.parent)
        self.assertEqual(cmd[cmd.index("--server") + 1], "https://daejinha.pythonanywhere.com")
        self.assertIn("--person-history", cmd)

    def test_face_sdk_root_resolves_to_packaged_models_directory(self):
        cmd = runtime.command("sample", "0", HERE.parent)
        sdk_root = Path(cmd[cmd.index("--face-model-root") + 1])
        self.assertEqual(sdk_root / "models/buffalo_l", HERE / "models/buffalo_l")

    def test_missing_camera_is_not_replaced_by_a_video(self):
        with patch.object(runtime.Path, "exists", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "No video-file fallback"):
                runtime.check_camera("0")

    def test_webcam_rejects_recorded_video(self):
        with self.assertRaises(ValueError):
            runtime.check_camera("recorded.mp4")

    def test_manifest_detects_tampering_and_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "laptop").mkdir()
            target = root / "test.txt"
            target.write_text("original")
            manifest = root / "laptop/MANIFEST.json"
            row = {"path": "test.txt", "bytes": target.stat().st_size, "sha256": runtime.sha(target)}
            manifest.write_text(json.dumps({"files": [row]}))
            self.assertEqual(runtime.validate_manifest(root), 1)
            target.write_text("changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                runtime.validate_manifest(root)
            row["path"] = "../outside.txt"
            manifest.write_text(json.dumps({"files": [row]}))
            with self.assertRaisesRegex(ValueError, "outside"):
                runtime.validate_manifest(root)


if __name__ == "__main__":
    unittest.main()
