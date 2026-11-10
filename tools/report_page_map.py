"""Record printed section pages from the actual rendered assessment report."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "docs/report-page-map.json"
REPORT = ROOT / "모바일웹서비스 프로젝트 공통평가 02_수행 결과 보고서.docx"


def compact_pages(pages):
    values = sorted(set(pages))
    chunks = []
    for value in values:
        if chunks and value == chunks[-1][-1] + 1:
            chunks[-1].append(value)
        else:
            chunks.append([value])
    return ", ".join(str(chunk[0]) if len(chunk) == 1 else f"{chunk[0]}-{chunk[-1]}" for chunk in chunks)


def section_location(keys, label=None, select=None):
    data = json.loads(MAP.read_text(encoding="utf-8"))
    pages = [page for key in keys for page in data["sections"].get(key, [])]
    if select is not None:
        pages = select(sorted(set(pages)))
    return (label or ", ".join(keys)) + "\n" + compact_pages(pages) + "쪽"


def rendered_map(pdf):
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    sections = {}
    current = None
    for number, page in enumerate(reader.pages, 1):
        if number <= 3:
            continue
        headings = []
        def heading_text(text, cm, tm, font, size):
            # Section headings are 13 pt (Word exports 12.96); body references
            # and table cells must never be mistaken for section starts.
            if size >= 12.5 and text.strip():
                headings.append(text.strip())
        page.extract_text(visitor_text=heading_text)
        if headings:
            match = re.match(r"^(B\d{2})\s+", " ".join(headings))
            current = match[1] if match else None
        if current:
            sections.setdefault(current, []).append(number - 1)
    return len(reader.pages), {key: sorted(set(pages)) for key, pages in sections.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    count, sections = rendered_map(args.pdf)
    if args.check:
        stored = json.loads(MAP.read_text(encoding="utf-8"))
        assert stored["physical_page_count"] == count and stored["sections"] == sections
        assert stored["report_sha256"] == hashlib.sha256(REPORT.read_bytes()).hexdigest()
        print(json.dumps({"actual_render_page_map_matches": True, "pages": count, "sections": len(sections)}))
        return
    result = {"page_basis": "Printed footer page numbers; the unnumbered cover is excluded",
              "physical_page_count": count, "report_sha256": hashlib.sha256(REPORT.read_bytes()).hexdigest(),
              "sections": sections}
    MAP.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pages": count, "sections": len(sections), "last_section": list(sections)[-1]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
