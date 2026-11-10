"""Build the standalone WorkBuddy ZIP from the canonical project skill."""

import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    repo = Path(__file__).resolve().parents[1]
    skill = repo / ".codebuddy/skills/ruanwenjie-geo"
    required = {
        "SKILL.md", "requirements.txt", "scripts/geo_data.py", "scripts/media.py",
        "scripts/export_pdf.py", "references/commands.md", "references/pdf-output.md",
        "scripts/export_media_word.py", "references/media-word-output.md",
        "references/template-generation.md", "references/template-contract.json",
        "references/report-thinking.md", "references/media-catalog.csv.gz",
        "references/内部判读底表.xlsx",
        "templates/AI回答采集表.xlsx", "templates/软文街_GEO客户素材收集表.xlsx",
        "templates/诊断与执行明细模板.xlsx", "templates/客户业务方案模板.xlsx",
        "templates/GEO诊断报告版式示例.pdf", "templates/品牌传播与GEO执行方案版式示例.pdf",
        "templates/推荐媒体模板.docx",
        "templates/推荐媒体模板.xlsx",
        "assets/fonts/NotoSansSC-Regular.ttf", "assets/fonts/OFL.txt",
    }
    files = sorted(p for p in skill.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".md", ".json", ".txt", ".py", ".xlsx", ".pdf", ".docx", ".gz", ".ttf", ".otf"})
    relative = {p.relative_to(skill).as_posix() for p in files}
    if required - relative:
        raise ValueError("Missing release files: " + ", ".join(sorted(required - relative)))
    dist = repo / "dist"
    dist.mkdir(exist_ok=True)
    version = re.search(r'^  version:\s*"([0-9]+\.[0-9]+\.[0-9]+)"', (skill / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    if not version:
        raise ValueError("Missing release version in SKILL.md metadata")
    target = dist / f"ruanwenjie-geo-{version.group(1)}.zip"
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "ruanwenjie-geo/" + path.relative_to(skill).as_posix())
    with ZipFile(target) as archive:
        assert archive.testzip() is None, "Corrupt archive"
        assert "ruanwenjie-geo/SKILL.md" in archive.namelist()
        assert len(archive.namelist()) == len(files)
        for path in files:
            assert archive.read("ruanwenjie-geo/" + path.relative_to(skill).as_posix()) == path.read_bytes()
        assert not any(name.endswith(".pptx") for name in archive.namelist()), "PPT is no longer a release output"
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest + "  " + target.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(target), "files": len(files), "bytes": target.stat().st_size,
                      "unpacked_bytes": sum(p.stat().st_size for p in files), "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
