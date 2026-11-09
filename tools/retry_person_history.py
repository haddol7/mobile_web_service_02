"""Replay a retained outbox in the foreground using privately supplied Edge credentials."""
import argparse
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--outbox", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Run in the project WSL virtualenv.")
    sys.path.insert(0, str(ROOT/"YOLOv5"))
    from changedetection import ChangeDetection
    from history_sender import HistorySender
    uploader = ChangeDetection(["person"], base_url=args.server)
    count = 0
    for packet in sorted(args.outbox.rglob("*.json")):
        HistorySender.send_file(uploader, packet)
        count += 1
    print(f"History packets accepted: {count}")


if __name__ == "__main__":
    main()
