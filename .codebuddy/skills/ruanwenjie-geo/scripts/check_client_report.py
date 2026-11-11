"""Locate internal research language in client PDF/TXT content.

This is a static aid. A clean result does not certify facts, client semantics,
scope, or page layout; those require separate review.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Shared with the renderer: business names and product terms are not evidence metadata.
PATTERNS = json.loads((Path(__file__).resolve().parents[1] /
                       "assets" / "client-report-process-patterns.json").read_text(encoding="utf-8"))



def extract(path):
    if path.suffix.lower() == ".pdf":
        import fitz
        with fitz.open(path) as doc:
            return [(i + 1, page.get_text()) for i, page in enumerate(doc)]
    if path.suffix.lower() in {".txt", ".md"}:
        return [(None, path.read_text(encoding="utf-8"))]
    raise ValueError("Use a PDF or UTF-8 TXT/MD. Image-based HTML must match the reviewed PDF.")


def check(pages):
    findings = []
    for page, text in pages:
        text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
        for pattern in PATTERNS:
            for hit in re.finditer(pattern, text, re.IGNORECASE):
                findings.append({"page": page, "match": hit.group(),
                                 "context": text[max(0, hit.start()-25):hit.end()+45].replace("\n", " ")})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    findings = check(extract(args.path))
    print(json.dumps({"file": str(args.path), "static_screen": "review_required" if findings else "clear",
                      "semantic_review_required": True, "matches": findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
