"""One-off capture of the unchanged baseline with the Acer camera in MJPEG mode."""

from datetime import datetime, timezone
from pathlib import Path
import runpy
import subprocess
import sys

root = Path.cwd()
project = root / ".local/laptop/runs"
name = datetime.now(timezone.utc).strftime("webcam-mjpeg-%Y%m%d-%H%M%S")
destination = project / name
print(f"Capture output: {destination}", flush=True)

child_code = r"""
import json
import os
from pathlib import Path
import runpy
import sys
import threading
import time

import cv2
import numpy as np

output = Path(sys.argv[1])
detector = sys.argv[2]
sys.argv = sys.argv[2:]
original_capture = cv2.VideoCapture
original_show = cv2.imshow
original_wait = cv2.waitKey
frame_number = -1
first_display = None
best_score = None
evidence = None
active_camera = None
prefer_objects = os.environ.get("WEBCAM_EVIDENCE_PREFER_OBJECTS") == "1"
object_ids = {39, 41, 67, 73}  # bottle, cup, cell phone, book


class LiveCamera:
    def __init__(self):
        self.capture = original_capture(0, cv2.CAP_V4L2)
        self.reader = None
        self.stopping = False
        self.mjpeg = cv2.VideoWriter_fourcc(*"MJPG")
        if not self.capture.isOpened() or not self.configure():
            self.capture.release()
            raise RuntimeError("Could not open physical camera 0 in MJPEG mode")

    def configure(self):
        return self.capture.set(cv2.CAP_PROP_FOURCC, self.mjpeg) and (
            int(self.capture.get(cv2.CAP_PROP_FOURCC)) == self.mjpeg
        )

    def __getattr__(self, name):
        return getattr(self.capture, name)

    def isOpened(self):
        return not self.stopping and self.capture.isOpened()

    def grab(self):
        if self.reader is None:
            self.reader = threading.current_thread()
        return self.capture.grab()

    def open(self, source):
        return not self.stopping and self.capture.open(source, cv2.CAP_V4L2) and self.configure()

    def finish(self):
        self.stopping = True
        if self.reader is not None:
            self.reader.join(timeout=12)
            if self.reader.is_alive():
                raise RuntimeError("The camera reader did not stop")
        self.capture.release()


def open_capture(source, *args, **kwargs):
    global active_camera
    if source != 0:
        return original_capture(source, *args, **kwargs)
    active_camera = LiveCamera()
    print("Physical camera /dev/video0 negotiated MJPG via V4L2", flush=True)
    return active_camera


def show(name, frame):
    global frame_number, first_display, best_score, evidence
    original_show(name, frame)
    if name != "0":
        return
    if first_display is None:
        first_display = time.monotonic()
    frame_number += 1
    label_file = output / "labels" / f"0_{frame_number}.txt"
    if not label_file.is_file():
        return
    rows = [line.split() for line in label_file.read_text().splitlines()]
    classes = {int(row[0]) for row in rows}
    confidence = max(float(row[-1]) for row in rows)
    score = (0 not in classes, bool(classes & object_ids), confidence) if prefer_objects else (confidence,)
    if best_score is not None and score <= best_score:
        return
    b, g, r = frame.astype(np.int16).transpose(2, 0, 1)
    green_fraction = float(np.mean((g > 95) & (g > r + 55) & (g > b + 55)))
    if green_fraction > 0.04:
        return
    if not cv2.imwrite(str(output / "webcam-baseline-frame.png"), frame):
        raise RuntimeError("Failed to save the displayed inference frame")
    best_score = score
    evidence = {
        "source": 0,
        "device": "/dev/video0",
        "camera_format": "MJPG",
        "width": frame.shape[1],
        "height": frame.shape[0],
        "frame_index": frame_number,
        "labels_file": f"labels/{label_file.name}",
        "green_fraction": green_fraction,
        "max_confidence": confidence,
        "class_ids": sorted(classes),
        "capture": "Unmodified frame passed to the original YOLO display",
    }


def wait_key(delay):
    key = original_wait(delay)
    if first_display is not None and time.monotonic() - first_display >= 12:
        return ord("q")
    return key


cv2.VideoCapture = open_capture
cv2.imshow = show
cv2.waitKey = wait_key
try:
    runpy.run_path(detector, run_name="__main__")
finally:
    if active_camera is not None:
        active_camera.finish()
if evidence is None:
    raise SystemExit("No clean annotated detection frame was available")
(output / "webcam-baseline-frame.json").write_text(
    json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(evidence), flush=True)
"""


def run_detector(command, **kwargs):
    # The standard launcher verifies detect.py and the weights before this call.
    return subprocess.run(
        [command[0], "-c", child_code, str(destination), *command[1:]], **kwargs
    ).returncode


subprocess.call = run_detector
launcher = root / "tools/run_edge.py"
sys.argv = [
    str(launcher), "--baseline", "--source", "0", "--device", "cpu",
    "--view-img", "--nosave", "--save-txt", "--save-conf",
    "--project", str(project), "--name", name,
]
runpy.run_path(str(launcher), run_name="__main__")

