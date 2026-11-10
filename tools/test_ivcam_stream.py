"""Camera receiver failure cases. No real camera or external API is used."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("ivcam_stream", Path(__file__).with_name("ivcam_stream.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class CameraReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.frame = Path(self.temp.name) / "live.jpg"
        self.frame.write_bytes(b"\xff\xd8camera-test\xff\xd9")
        self.stop = threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.make_handler(self.frame, 2, self.stop))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_current_frame_health(self):
        with urlopen(self.base + "/health", timeout=2) as response:
            self.assertTrue(json.load(response)["live"])

    def test_missing_camera_is_unavailable(self):
        self.frame.unlink()
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/health", timeout=2)
        self.assertEqual(context.exception.code, 503)

    def test_frozen_frame_is_not_reported_as_live(self):
        old = time.time() - 10
        os.utime(self.frame, (old, old))
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/stream", timeout=2)
        self.assertEqual(context.exception.code, 503)

    def test_partial_jpeg_is_rejected(self):
        self.frame.write_bytes(b"\xff\xd8partial")
        with self.assertRaises(ValueError):
            bridge.read_frame(self.frame)

    def test_numbered_frames_select_latest_complete_filename(self):
        older = Path(self.temp.name) / "frame-000000001.jpg"
        newer = Path(self.temp.name) / "frame-000000002.jpg"
        older.write_bytes(b"\xff\xd8old\xff\xd9")
        newer.write_bytes(b"\xff\xd8new\xff\xd9")
        (Path(self.temp.name) / "frame-000000003.jpg.tmp").write_bytes(b"partial")
        _, data, _ = bridge.read_frame(self.temp.name)
        self.assertEqual(data, newer.read_bytes())

    def test_empty_frame_directory_is_unavailable(self):
        with self.assertRaises(FileNotFoundError):
            bridge.read_frame(self.temp.name)

    def test_no_other_files_are_served(self):
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/../private.json", timeout=2)
        self.assertEqual(context.exception.code, 404)

    def test_mjpeg_contains_received_frame(self):
        with urlopen(self.base + "/stream", timeout=2) as response:
            self.assertIn("multipart/x-mixed-replace", response.headers["Content-Type"])
            self.assertEqual(response.readline(), b"--ivcam\r\n")
            self.assertEqual(response.readline(), b"Content-Type: image/jpeg\r\n")
            length = int(response.readline().split(b":", 1)[1])
            self.assertEqual(response.readline(), b"\r\n")
            self.assertEqual(response.read(length), self.frame.read_bytes())


if __name__ == "__main__":
    unittest.main()
