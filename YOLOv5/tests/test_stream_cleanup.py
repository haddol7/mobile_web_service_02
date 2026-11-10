"""Regression checks for native stream readers surviving the preview window."""
import threading
import time
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np

from utils.dataloaders import LoadStreams


class StreamCleanupTests(unittest.TestCase):
    def test_constructor_initializes_reader_lifecycle(self):
        capture = Mock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda key: {
            cv2.CAP_PROP_FRAME_WIDTH: 64, cv2.CAP_PROP_FRAME_HEIGHT: 48,
            cv2.CAP_PROP_FPS: 6, cv2.CAP_PROP_FRAME_COUNT: 0,
        }.get(key, 0)
        capture.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
        with patch('utils.dataloaders.cv2.VideoCapture', return_value=capture), \
                patch('utils.dataloaders.Thread') as thread_class, \
                patch('utils.dataloaders.cv2.destroyAllWindows'):
            loader = LoadStreams('http://127.0.0.1/test')
            self.assertTrue(loader.running)
            self.assertEqual(loader.caps, [capture])
            thread_class.return_value.is_alive.return_value = False
            loader.close()

    def loader(self):
        loader = LoadStreams.__new__(LoadStreams)
        loader.running = True
        loader.count = -1
        loader.caps = [Mock()]
        return loader

    def test_reader_finishes_before_capture_release(self):
        loader = self.loader()
        reading = threading.Event()
        finished = threading.Event()

        def reader():
            reading.set()
            while loader.running:
                time.sleep(0.005)
            finished.set()

        thread = threading.Thread(target=reader)
        loader.threads = [thread]
        thread.start()
        self.assertTrue(reading.wait(1))
        loader.caps[0].release.side_effect = lambda: self.assertTrue(finished.is_set())
        with patch('utils.dataloaders.cv2.destroyAllWindows'):
            loader.close()
        self.assertFalse(thread.is_alive())
        loader.caps[0].release.assert_called_once()

    def test_q_stops_iteration_and_releases_finished_reader(self):
        loader = self.loader()
        thread = Mock()
        thread.is_alive.side_effect = [True, True, False]
        loader.threads = [thread]
        with patch('utils.dataloaders.cv2.waitKey', return_value=ord('q')), \
                patch('utils.dataloaders.cv2.destroyAllWindows'):
            with self.assertRaises(StopIteration):
                next(loader)
        thread.join.assert_called_once()
        loader.caps[0].release.assert_called_once()
        self.assertFalse(loader.running)

    def test_no_concurrent_release_if_reader_has_not_stopped(self):
        loader = self.loader()
        thread = Mock()
        thread.is_alive.return_value = True
        loader.threads = [thread]
        with patch('utils.dataloaders.cv2.destroyAllWindows'):
            loader.close()
        loader.caps[0].release.assert_not_called()


if __name__ == '__main__':
    unittest.main()
