"""Capture one local HTTP request for assessment ID 7, not photo synchronization.

Adapted from week3/assignment4_socket_server/server.py: receive_request,
save_raw_request, send_response and the socket accept loop. This standalone copy
does not depend on the old assignment repository. Raw headers may contain tokens;
the default destination is a unique, Git-ignored evidence/private directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
import socket
from uuid import uuid4


HEADER_SEPARATOR = b"\r\n\r\n"
BUFFER_SIZE = 16 * 1024
MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 6 * 1024 * 1024
SERVER_ROOT = Path(__file__).resolve().parents[1]


class SocketRequestCapture:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def receive_request(client: socket.socket) -> bytes:
        """Receive exactly one complete Content-Length-framed HTTP request."""
        received = bytearray()
        header_end = -1
        while header_end < 0:
            chunk = client.recv(BUFFER_SIZE)
            if not chunk:
                raise ValueError("Incomplete HTTP headers")
            received.extend(chunk)
            header_end = received.find(HEADER_SEPARATOR)
            # A valid boundary-sized header can end with a split CRLFCRLF.
            incomplete_limit = MAX_HEADER_BYTES + len(HEADER_SEPARATOR) - 1
            if (header_end < 0 and len(received) > incomplete_limit) or header_end > MAX_HEADER_BYTES:
                raise ValueError("HTTP headers exceed capture limit")

        lines = bytes(received[:header_end]).split(b"\r\n")
        if not re.fullmatch(rb"[A-Z]+ [^\x00-\x20]+ HTTP/1\.[01]", lines[0]):
            raise ValueError("Invalid HTTP request line")
        content_lengths = []
        for line in lines[1:]:
            name, separator, value = line.partition(b":")
            if not separator or not re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
                raise ValueError("Invalid HTTP header")
            if name.lower() == b"transfer-encoding":
                raise ValueError("Transfer-Encoding is not supported by this capture tool")
            if name.lower() == b"content-length":
                content_lengths.append(value.strip())

        if len(content_lengths) > 1:
            raise ValueError("Duplicate Content-Length")
        content_length = 0
        if content_lengths:
            value = content_lengths[0]
            if not value or not value.isdigit() or len(value) > 10:
                raise ValueError("Invalid Content-Length")
            content_length = int(value)
        if content_length > MAX_BODY_BYTES:
            raise ValueError("HTTP body exceeds capture limit")

        expected_size = header_end + len(HEADER_SEPARATOR) + content_length
        if len(received) > expected_size:
            raise ValueError("Unexpected bytes after the HTTP request")
        while len(received) < expected_size:
            chunk = client.recv(min(BUFFER_SIZE, expected_size - len(received)))
            if not chunk:
                raise ValueError("Incomplete HTTP body")
            received.extend(chunk)
        return bytes(received)

    def save_raw_request(self, request_data: bytes, timestamp: str | None = None) -> Path:
        stamp = timestamp or datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        if not re.fullmatch(r"\d{4}(?:-\d{2}){5}", stamp):
            raise ValueError("Invalid capture timestamp")
        suffix = 0
        while True:
            ending = "" if suffix == 0 else f"-{suffix}"
            output_path = self.output_dir / f"{stamp}{ending}.bin"
            try:
                with output_path.open("xb") as output:
                    output.write(request_data)
                return output_path
            except FileExistsError:
                suffix += 1

    @staticmethod
    def send_response(client: socket.socket, status: str, message: str) -> None:
        body = message.encode("utf-8")
        response = (
            f"HTTP/1.1 {status}\r\n"
            "Server: common01-request-capture/1.0\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii") + body
        client.sendall(response)

    def handle_client(self, client: socket.socket, address: tuple[str, int]) -> None:
        client.settimeout(10)
        try:
            request_data = self.receive_request(client)
        except (ValueError, OSError) as error:
            print(f"Capture rejected: {error}", flush=True)
            try:
                self.send_response(client, "400 Bad Request", "Request capture rejected.\n")
            except OSError:
                pass
            return
        try:
            raw_path = self.save_raw_request(request_data)
        except OSError:
            print("Could not save request; capture failed.", flush=True)
            try:
                self.send_response(client, "500 Internal Server Error", "Request capture could not be saved.\n")
            except OSError:
                pass
            return
        print(f"Received {len(request_data)} bytes from {address[0]}:{address[1]}", flush=True)
        print(f"Raw request: {raw_path.resolve()}", flush=True)
        try:
            self.send_response(
                client, "200 OK",
                "HTTP request captured. This diagnostic response is not the Django photo API.\n",
            )
        except OSError:
            print("Request saved; peer closed before diagnostic response completed.", flush=True)

    def run(self, host: str = "127.0.0.1", port: int = 8002, once: bool = True) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((host, port))
            server.listen(1)
            print(f"Request capture listening on {host}:{server.getsockname()[1]}", flush=True)
            print("Raw headers may contain credentials. Do not publish private captures.", flush=True)
            while True:
                client, address = server.accept()
                with client:
                    self.handle_client(client, address)
                if once:
                    return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    destination = args.output_dir or (
        SERVER_ROOT.parent / "evidence" / "private" / "request-captures"
        / f"{datetime.now():%Y-%m-%d-%H-%M-%S}-{uuid4().hex[:8]}"
    )
    SocketRequestCapture(destination).run(args.host, args.port)


if __name__ == "__main__":
    main()
