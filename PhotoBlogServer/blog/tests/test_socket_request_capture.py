"""Independent socketpair tests for the ID 7 diagnostic, not Android sync."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tools.socket_request_capture import (
    MAX_BODY_BYTES, MAX_HEADER_BYTES, SocketRequestCapture,
)


class SocketRequestCaptureTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="common01-socket-test-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.capture = SocketRequestCapture(self.directory)

    def socket_pair(self):
        receiver, sender = socket.socketpair()
        receiver.settimeout(2)
        sender.settimeout(2)
        self.addCleanup(receiver.close)
        self.addCleanup(sender.close)
        return receiver, sender

    def receive_bytes(self, payload):
        receiver, sender = self.socket_pair()
        sender.sendall(payload)
        sender.shutdown(socket.SHUT_WR)
        return self.capture.receive_request(receiver)

    def receive_fragments(self, fragments):
        receiver, sender = self.socket_pair()
        errors = []

        def send():
            try:
                for fragment in fragments:
                    sender.sendall(fragment)
                    time.sleep(0.005)
                sender.shutdown(socket.SHUT_WR)
            except OSError as error:
                errors.append(error)

        writer = threading.Thread(target=send, daemon=True)
        writer.start()
        try:
            result = self.capture.receive_request(receiver)
        finally:
            writer.join(timeout=2)
        self.assertFalse(writer.is_alive(), "Fragment writer did not finish.")
        self.assertEqual(errors, [], "Real socketpair writer failed.")
        return result

    def test_public_get_is_received_and_saved_without_byte_changes(self):
        raw = b"GET /api_root/Post/ HTTP/1.1\r\nHost: 127.0.0.1:8002\r\nAccept: application/json\r\n\r\n"
        received = self.receive_bytes(raw)
        saved = self.capture.save_raw_request(received, "2026-10-10-09-30-00")
        self.assertEqual(received, raw)
        self.assertEqual(saved.name, "2026-10-10-09-30-00.bin")
        self.assertEqual(saved.read_bytes(), raw)

    def test_case_insensitive_content_length_and_zero_body(self):
        raw = b"GET /api_root/Post/ HTTP/1.1\r\nHost: localhost\r\ncontent-length: 0\r\n\r\n"
        self.assertEqual(self.receive_bytes(raw), raw)

    def test_fragmented_multipart_text_and_binary_are_received_and_saved_exactly(self):
        body = (
            b"--capture-boundary\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\n"
            + "사진 요청 테스트".encode("utf-8")
            + b"\r\n--capture-boundary\r\nContent-Disposition: form-data; name=\"image\"; filename=\"fixture.png\"\r\n"
            b"Content-Type: image/png\r\n\r\n\x89PNG\r\n\x1a\n\0\xff\x81\r\n--capture-boundary--\r\n"
        )
        headers = (
            b"POST /api_root/Post/ HTTP/1.1\r\nHost: localhost\r\n"
            b"Content-Type: multipart/form-data; boundary=capture-boundary\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode()
        )
        raw = headers + body
        fragments = [headers[:7], headers[7:-3], headers[-3:-1], headers[-1:], body[:1], body[1:47], body[47:]]
        received = self.receive_fragments(fragments)
        saved = self.capture.save_raw_request(received, "2026-10-10-09-30-01")
        self.assertEqual(received, raw)
        self.assertEqual(saved.read_bytes(), raw)

    def test_header_separator_split_across_chunks_is_supported(self):
        headers = b"GET /api_root/Post/ HTTP/1.1\r\nHost: localhost"
        fragments = [headers, b"\r", b"\n", b"\r", b"\n"]
        self.assertEqual(self.receive_fragments(fragments), headers + b"\r\n\r\n")

    def test_header_eof_before_separator_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Incomplete HTTP headers"):
            self.receive_bytes(b"GET /api_root/Post/ HTTP/1.1\r\nHost: localhost\r\n")

    def test_empty_eof_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Incomplete HTTP headers"):
            self.receive_bytes(b"")

    def test_body_eof_before_declared_length_is_rejected(self):
        raw = b"POST /api_root/Post/ HTTP/1.1\r\nContent-Length: 8\r\n\r\nabc"
        with self.assertRaisesRegex(ValueError, "Incomplete HTTP body"):
            self.receive_bytes(raw)

    def test_duplicate_content_lengths_even_identical_are_rejected(self):
        for second in (b"0", b"5"):
            with self.subTest(second=second):
                raw = b"GET /api_root/Post/ HTTP/1.1\r\nContent-Length: 0\r\ncontent-length: " + second + b"\r\n\r\n"
                with self.assertRaisesRegex(ValueError, "Duplicate Content-Length"):
                    self.receive_bytes(raw)

    def test_invalid_content_length_values_are_rejected(self):
        for value in (b"", b"-1", b"+1", b"NaN", b"1, 1", b"1.0", b"12345678901"):
            with self.subTest(value=value):
                raw = b"POST /api_root/Post/ HTTP/1.1\r\nContent-Length: " + value + b"\r\n\r\n"
                with self.assertRaisesRegex(ValueError, "Invalid Content-Length"):
                    self.receive_bytes(raw)

    def test_transfer_encoding_is_rejected_instead_of_silently_truncated(self):
        for value in (b"chunked", b"identity"):
            with self.subTest(value=value):
                raw = b"POST /api_root/Post/ HTTP/1.1\r\ntransfer-encoding: " + value + b"\r\n\r\n"
                with self.assertRaisesRegex(ValueError, "Transfer-Encoding"):
                    self.receive_bytes(raw)

    def test_oversized_header_is_rejected(self):
        raw = b"GET /api_root/Post/ HTTP/1.1\r\nX-Test: " + b"x" * MAX_HEADER_BYTES + b"\r\n\r\n"
        with self.assertRaisesRegex(ValueError, "headers.*limit"):
            self.receive_bytes(raw)

    def test_header_at_exact_limit_is_accepted(self):
        prefix = b"GET /api_root/Post/ HTTP/1.1\r\nX-Test: "
        headers = prefix + b"x" * (MAX_HEADER_BYTES - len(prefix))
        raw = headers + b"\r\n\r\n"
        self.assertEqual(len(headers), MAX_HEADER_BYTES)
        self.assertEqual(self.receive_bytes(raw), raw)

    def test_exact_limit_header_with_partial_separator_is_accepted(self):
        receiver, sender = self.socket_pair()
        prefix = b"GET /api_root/Post/ HTTP/1.1\r\nX-Test: "
        headers = prefix + b"x" * (MAX_HEADER_BYTES - len(prefix))
        prefix_observed = threading.Event()
        errors = []

        class ReceiveObserver:
            def __init__(self):
                self.total = 0

            def recv(self, count):
                data = receiver.recv(count)
                self.total += len(data)
                if self.total >= MAX_HEADER_BYTES + 1:
                    prefix_observed.set()
                return data

        def send():
            try:
                sender.sendall(headers + b"\r")
                if not prefix_observed.wait(timeout=2):
                    errors.append("The first separator byte was not observed.")
                sender.sendall(b"\n\r\n")
                sender.shutdown(socket.SHUT_WR)
            except OSError as error:
                errors.append(error)

        writer = threading.Thread(target=send, daemon=True)
        writer.start()
        try:
            raw = self.capture.receive_request(ReceiveObserver())
        finally:
            writer.join(timeout=2)
        self.assertTrue(prefix_observed.is_set())
        self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(raw, headers + b"\r\n\r\n")

    def test_oversized_body_length_rejected_before_waiting_for_body(self):
        raw = b"POST /api_root/Post/ HTTP/1.1\r\n" + f"Content-Length: {MAX_BODY_BYTES + 1}\r\n\r\n".encode()
        with self.assertRaisesRegex(ValueError, "body.*limit"):
            self.receive_bytes(raw)

    def test_bytes_after_declared_request_are_not_silently_saved(self):
        raw = b"POST /api_root/Post/ HTTP/1.1\r\nContent-Length: 1\r\n\r\nab"
        with self.assertRaisesRegex(ValueError, "Unexpected bytes"):
            self.receive_bytes(raw)

    def test_invalid_request_line_and_header_are_rejected(self):
        for raw in (
            b"not HTTP\r\nHost: localhost\r\n\r\n",
            b"GET / HTTP/1.1\r\nInvalid header line\r\n\r\n",
            b"GET / HTTP/1.1\r\nBad Name: value\r\n\r\n",
        ):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "Invalid HTTP"):
                    self.receive_bytes(raw)

    def test_filename_collision_uses_exclusive_file_without_overwriting(self):
        first = self.capture.save_raw_request(b"first request", "2026-10-10-09-30-02")
        second = self.capture.save_raw_request(b"second request", "2026-10-10-09-30-02")
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), b"first request")
        self.assertEqual(second.read_bytes(), b"second request")
        self.assertEqual(len(list(self.directory.glob("*.bin"))), 2)

    def test_default_filename_contains_date_time_to_seconds(self):
        saved = self.capture.save_raw_request(b"test request")
        self.assertRegex(saved.name, r"^\d{4}(?:-\d{2}){5}\.bin$")

    def test_invalid_timestamp_cannot_escape_capture_directory(self):
        with self.assertRaisesRegex(ValueError, "Invalid capture timestamp"):
            self.capture.save_raw_request(b"test request", "../unsafe")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_handle_client_saves_raw_request_and_returns_plain_diagnostic(self):
        receiver, sender = self.socket_pair()
        raw = b"GET /api_root/Post/ HTTP/1.1\r\nHost: localhost:8002\r\n\r\n"
        sender.sendall(raw)
        with redirect_stdout(StringIO()):
            self.capture.handle_client(receiver, ("127.0.0.1", 12345))
        receiver.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sender.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        response = b"".join(chunks)
        headers, body = response.split(b"\r\n\r\n", 1)
        self.assertTrue(headers.startswith(b"HTTP/1.1 200 OK\r\n"))
        self.assertIn(b"Content-Type: text/plain; charset=utf-8", headers)
        self.assertIn(f"Content-Length: {len(body)}".encode(), headers)
        self.assertIn(b"not the Django photo API", body)
        self.assertNotEqual(body.strip(), b"[]")
        captures = list(self.directory.glob("*.bin"))
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0].read_bytes(), raw)

    def test_handle_client_rejects_incomplete_request_without_saving(self):
        receiver, sender = self.socket_pair()
        sender.sendall(b"POST /api_root/Post/ HTTP/1.1\r\nContent-Length: 8\r\n\r\nabc")
        sender.shutdown(socket.SHUT_WR)
        with redirect_stdout(StringIO()):
            self.capture.handle_client(receiver, ("127.0.0.1", 12345))
        self.assertTrue(sender.recv(4096).startswith(b"HTTP/1.1 400 Bad Request\r\n"))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_storage_error_returns_fixed_500_without_saving_or_raising(self):
        receiver, sender = self.socket_pair()
        sender.sendall(b"GET /api_root/Post/ HTTP/1.1\r\nHost: localhost\r\n\r\n")
        with patch.object(self.capture, "save_raw_request", side_effect=OSError("fixture storage error")), redirect_stdout(StringIO()):
            self.capture.handle_client(receiver, ("127.0.0.1", 12345))
        response = sender.recv(4096)
        self.assertTrue(response.startswith(b"HTTP/1.1 500 Internal Server Error\r\n"))
        self.assertNotIn(b"fixture storage error", response)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_disconnected_peer_does_not_discard_received_file_or_raise(self):
        receiver, sender = self.socket_pair()
        raw = b"GET /api_root/Post/ HTTP/1.1\r\nHost: localhost\r\n\r\n"
        sender.sendall(raw)
        sender.close()
        with redirect_stdout(StringIO()):
            self.capture.handle_client(receiver, ("127.0.0.1", 12345))
        captures = list(self.directory.glob("*.bin"))
        self.assertEqual(len(captures), 1)
        self.assertEqual(captures[0].read_bytes(), raw)

    def test_capture_limits_match_declared_contract(self):
        self.assertEqual(MAX_HEADER_BYTES, 65536)
        self.assertEqual(MAX_BODY_BYTES, 6 * 1024 * 1024)
