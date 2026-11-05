"""Read-only process identity and source-time audit; this tool never restarts servers."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time


SERVER_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = SERVER_ROOT.parent / "evidence" / "baseline" / "runtime-audit.json"


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def audit(pid):
    if platform.system() != "Linux" or not os.environ.get("WSL_DISTRO_NAME"):
        raise SystemExit("Read actual Linux /proc process state inside WSL.")
    proc = Path(f"/proc/{pid}")
    # Fields after the final ')' begin at field 3 (state). starttime is field 22.
    stat_fields = (proc / "stat").read_text().rpartition(")")[2].split()
    start_ticks = int(stat_fields[19])
    ticks_per_second = os.sysconf("SC_CLK_TCK")
    boot_epoch = int(next(line.split()[1] for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime ")))
    derived_start = boot_epoch + start_ticks / ticks_per_second
    now = time.time()
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    cmdline = (proc / "cmdline").read_bytes().split(b"\0")
    command = [item.decode("utf-8", errors="replace") for item in cmdline if item]
    cwd = (proc / "cwd").resolve()
    executable = (proc / "exe").resolve()
    owner_uid = int(next(line.split()[1] for line in (proc / "status").read_text().splitlines() if line.startswith("Uid:")))
    identity_matches = (
        cwd == SERVER_ROOT and executable == Path(sys.executable).resolve()
        and command[1:3] == ["manage.py", "runserver"]
        and "0.0.0.0:8000" in command and "--noreload" in command
        and owner_uid == os.getuid()
    )
    sources = [SERVER_ROOT / "manage.py"]
    for package in ("blog", "photoblog"):
        sources.extend((SERVER_ROOT / package).glob("*.py"))
    source_times = []
    for path in sorted(sources):
        modified = path.stat().st_mtime
        source_times.append({
            "path": str(path.relative_to(SERVER_ROOT)),
            "mtime_utc": iso(modified),
            "mtime_epoch": modified,
            # btime has integer-second precision; avoid treating subsecond noise as proof.
            "more_than_one_second_after_derived_start": modified > derived_start + 1,
        })
    result = {
        "observed_utc": iso(now), "environment": "WSL " + os.environ["WSL_DISTRO_NAME"],
        "pid": pid, "owner_uid": owner_uid, "command": command,
        "cwd": str(cwd), "executable": str(executable),
        "identity_matches_owned_common01_server": identity_matches,
        "start_ticks_since_boot": start_ticks,
        "clock_ticks_per_second": ticks_per_second,
        "kernel_boot_epoch": boot_epoch,
        "derived_start_utc": iso(derived_start),
        "wall_clock_vs_boot_plus_uptime_seconds": now - (boot_epoch + uptime),
        "source_times": source_times,
        "time_comparison_shows_later_source": any(row["more_than_one_second_after_derived_start"] for row in source_times),
        "clock_caution": "WSL wall-clock corrections can shift derived process wall time. Time comparison alone is not proof when conflicting historical observations exist.",
        "action": "Read-only audit; process was not signalled or restarted.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Actual process/source audit: {OUTPUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, default=267)
    audit(parser.parse_args().pid)
