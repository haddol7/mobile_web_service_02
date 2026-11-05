"""Keep additional-feature verification separate from historical baseline evidence."""
from pathlib import Path
import verify_baseline


if __name__ == "__main__":
    verify_baseline.EVIDENCE_ROOT = Path(__file__).resolve().parents[2] / "evidence" / "content" / "server"
    verify_baseline.main()
