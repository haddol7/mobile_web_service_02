from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

import numpy as np
from history_sender import HistorySender, HistoryUploadError


class HistorySenderTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.session = uuid4().hex
        self.uploader = SimpleNamespace(base_url="http://127.0.0.1:1234", token="isolated-history-token", session=Mock())
        self.sender = HistorySender(self.uploader, SimpleNamespace(session_id=self.session, faces=None),
            self.folder.name, source_label="test", source_kind="video")
        self.frame = np.zeros((60,100,3), np.uint8)
        self.record = {"session_id": self.session, "frame_index": 1, "video_seconds": 0.,
            "processed_at_utc": "2026-11-08T00:00:00+00:00",
            "tracks": [{"track_id": 1, "bbox": [0,0,20,30]}], "faces": [], "crossings": []}

    def accepted(self, index):
        self.uploader.session.post.return_value.status_code = 201
        self.uploader.session.post.return_value.json.return_value = {
            "id": hashlib.sha256(f"{self.session}:{index}".encode()).hexdigest()}

    def test_success_keeps_no_secret_or_pending_packet_and_throttles_sampling(self):
        self.accepted(1)
        self.sender.consider(self.record, self.frame)
        self.assertEqual(self.sender.sent, 1)
        self.assertEqual(list(self.sender.directory.iterdir()), [])
        self.record.update(frame_index=2, video_seconds=1.)
        self.sender.consider(self.record, self.frame)
        self.assertEqual(self.uploader.session.post.call_count, 1)
        self.assertFalse(self.uploader.session.post.call_args.kwargs["allow_redirects"])

    def test_failed_packet_retained_and_replay_reuses_id(self):
        self.uploader.session.post.return_value.status_code = 503
        with self.assertRaises(HistoryUploadError):
            self.sender.consider(self.record, self.frame)
        pending = list(self.sender.directory.glob("*.json"))
        self.assertEqual(len(pending), 1)
        text = pending[0].read_text()
        self.assertNotIn(self.uploader.token, text)
        self.assertTrue(pending[0].with_suffix(".jpg").exists())
        self.accepted(1)
        HistorySender.send_file(self.uploader, pending[0])
        self.assertFalse(pending[0].exists())

    def test_replay_does_not_send_to_different_server(self):
        self.uploader.session.post.return_value.status_code = 503
        with self.assertRaises(HistoryUploadError):
            self.sender.consider(self.record, self.frame)
        self.uploader.base_url = "https://different.example"
        calls = self.uploader.session.post.call_count
        with self.assertRaises(HistoryUploadError):
            HistorySender.send_file(self.uploader, next(self.sender.directory.glob("*.json")))
        self.assertEqual(self.uploader.session.post.call_count, calls)

    def test_new_track_or_crossing_is_saved_between_periodic_samples(self):
        self.accepted(1); self.sender.consider(self.record, self.frame)
        self.record.update(frame_index=2, video_seconds=1.)
        self.record["tracks"].append({"track_id": 2, "bbox": [30,0,50,30]})
        self.accepted(2); self.sender.consider(self.record, self.frame)
        self.record.update(frame_index=3, video_seconds=2.)
        self.record["crossings"] = [{"event_id": "test-event", "track_id": 2, "direction": "in"}]
        self.accepted(3); self.sender.consider(self.record, self.frame)
        self.assertEqual(self.sender.sent, 3)

    def test_unknown_date_is_preserved_and_naive_start_rejected(self):
        self.assertIsNone(self.sender.config["recording_started_at"])
        with self.assertRaises(ValueError):
            HistorySender(self.uploader, SimpleNamespace(session_id=self.session, faces=None),
                self.folder.name, source_label="test", source_kind="video", recording_started_at="2026-11-08T12:00:00")


if __name__ == "__main__":
    unittest.main()
