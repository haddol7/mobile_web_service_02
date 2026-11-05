"""Record an actual GNU telnet HTTP exchange; never fabricate terminal pixels."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess


DEFAULT_BINARY = Path(shutil.which("telnet") or "telnet")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "evidence" / "baseline" / "telnet-http.txt"


def capture(binary, output):
    request = (
        "GET /api_root/Post/ HTTP/1.1\r\n"
        "Host: 127.0.0.1:8000\r\n"
        "Accept: application/json\r\n"
        "Connection: close\r\n\r\n"
    )
    command = [str(binary), "-E", "127.0.0.1", "8000"]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    input_stream = process.stdin
    try:
        # Keep stdin open until the server closes the connection. communicate(input)
        # can make telnet exit on stdin EOF before it receives the HTTP response.
        # telnet applies NVT newline conversion itself. A literal CR becomes CR-NUL,
        # so enter LF-delimited lines as one would type them in a terminal.
        input_stream.write(request.replace("\r\n", "\n").encode("ascii"))
        input_stream.flush()
        process.stdin = None
        raw, _ = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        raw, _ = process.communicate()
        raise RuntimeError("Actual telnet exchange timed out; no successful evidence was written.")
    finally:
        input_stream.close()
    transcript = raw.decode("utf-8", errors="replace")
    match = re.search(r"HTTP/1\.[01] 200 OK\r?\n", transcript)
    if not match:
        raise RuntimeError("Actual telnet did not receive HTTP 200:\n" + transcript)
    http = transcript[match.start():]
    separator = re.search(r"\r?\n\r?\n", http)
    if not separator:
        raise RuntimeError("HTTP headers/body separator is missing.")
    body = http[separator.end():].lstrip()
    data, _ = json.JSONDecoder().raw_decode(body)
    if not isinstance(data, list):
        raise RuntimeError("The assessed /api_root/Post/ response is not a JSON array.")
    report = (
        "ACTUAL TELNET HTTP VERIFICATION (WSL)\n"
        f"UTC: {datetime.now(timezone.utc).isoformat()}\n"
        f"Command: {' '.join(command)}\n"
        "HTTP request entered as LF terminal lines (telnet converts newlines; public GET, no credentials):\n" + request.replace("\r\n", "\n")
        + "\nActual telnet stdout/stderr:\n" + transcript
        + f"\nVerified: HTTP 200; JSON array; {len(data)} photo posts.\n"
        "This is a command transcript, not a terminal screenshot.\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    print(f"Evidence written: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telnet", type=Path, default=DEFAULT_BINARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.telnet.is_file():
        parser.error("Actual telnet binary is missing; install the official Ubuntu package first.")
    capture(args.telnet, args.output)
