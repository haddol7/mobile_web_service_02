"""Run the bundled DOCX renderer with native Word PDF export on Windows."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path("C:/Users/1/.codex/plugins/cache/openai-primary-runtime/documents/26.1104.22356/skills/documents")
DEPENDENCIES = Path(sys.executable).resolve().parent.parent
os.environ["PATH"] = str(DEPENDENCIES / "native/poppler/Library/bin") + os.pathsep + os.environ["PATH"]
temporary = ROOT / "evidence/private/report-refresh-20261109/temp"
temporary.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = str(temporary)
spec = importlib.util.spec_from_file_location("bundled_docx_renderer", SKILL / "render_docx.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def word_pdf(input_path, user_profile, convert_dir, stem, verbose=False):
    target = str(Path(convert_dir) / (stem + ".pdf"))
    if str(input_path).lower().endswith(".pdf"):
        shutil.copy2(input_path, target)
    else:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(ROOT / "tools/export_report_pdf.ps1"),
                                 "-InputDocx", str(input_path), "-OutputPdf", target],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stdout)
    return target, "Native Microsoft Word PDF conversion; bundled renderer rasterization"


renderer.convert_to_pdf = word_pdf
if __name__ == "__main__":
    renderer.main()
