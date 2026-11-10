"""Expose Windows-captured iVCam JPEG frames to YOLO on WSL loopback only."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import platform
import threading
import time


def read_frame(path, max_age=3.0, now=None):
    """Reject old/partial frames instead of presenting them as live camera input."""
    path = Path(path)
    if path.is_dir():
        # Each JPEG is renamed to a new numbered file, so a Windows writer
        # never replaces a file while WSL has it open.
        try:
            path = max(path.glob("frame-[0-9]*.jpg"), key=lambda item: item.name)
        except ValueError:
            raise FileNotFoundError("No camera frame has arrived") from None
    before = path.stat()
    age = (time.time() if now is None else now) - before.st_mtime
    if age < -1 or age > max_age:
        raise ValueError("Camera frame is stale or has an invalid timestamp")
    data = path.read_bytes()
    after = path.stat()
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        raise ValueError("Camera frame changed during reading")
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("Incomplete camera JPEG")
    return after.st_mtime_ns, data, round(max(age, 0), 3)


def make_handler(frame_path, max_age, stop):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/health", "/stream"}:
                self.send_error(404)
                return
            try:
                stamp, data, age = read_frame(frame_path, max_age)
            except (OSError, ValueError) as error:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"live": False, "error": str(error)}).encode())
                return
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(json.dumps({"live": True, "frame_mtime_ns": stamp,
                                             "frame_age_seconds": age, "jpeg_bytes": len(data),
                                             "inference_environment": "WSL", "audio": False}).encode())
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=ivcam")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            last_stamp = None
            try:
                while not stop.is_set():
                    stamp, data, _ = read_frame(frame_path, max_age)
                    if stamp != last_stamp:
                        self.wfile.write(b"--ivcam\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n")
                        self.wfile.flush()
                        last_stamp = stamp
                    stop.wait(0.04)
            except (OSError, ValueError):
                # Close on camera failure; never loop the last captured frame.
                pass

        def log_message(self, format, *args):
            return
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--port", type=int, default=48765)
    parser.add_argument("--max-age", type=float, default=3.0)
    args = parser.parse_args()
    if platform.system() != "Linux":
        raise SystemExit("Run the frame receiver in the WSL project virtualenv.")
    if args.max_age <= 0 or not 0 <= args.port <= 65535:
        parser.error("Invalid age or port")
    stop = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.frame, args.max_age, stop))
    print(json.dumps({"started_utc": datetime.now(timezone.utc).isoformat(),
                      "url": f"http://127.0.0.1:{server.server_port}/stream",
                      "frame": str(args.frame), "bind": "127.0.0.1",
                      "production_requests": 0, "paid_api_calls": 0}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
