"""Run backend evidence checks with isolated limit state and no real model credentials."""
import os
from pathlib import Path
import tempfile

import verify_content


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="common02-security-check-") as directory:
        os.environ.update(SECURITY_STATE_ROOT=directory, HISTORY_LLM_CONFIG="",
            HISTORY_LLM_API_KEY="", HISTORY_EMBEDDING_API_KEY="")
        verify_content.verify_baseline.EVIDENCE_ROOT = Path(__file__).resolve().parents[2] / "evidence/content/server"
        verify_content.verify_baseline.main()
