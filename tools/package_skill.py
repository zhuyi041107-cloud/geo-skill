"""Build the standalone WorkBuddy ZIP from the canonical project skill."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    repo = Path(__file__).resolve().parents[1]
    skill = repo / ".codebuddy/skills/ruanwenjie-geo"
    required = {
        "SKILL.md", "requirements.txt", "scripts/geo_data.py", "scripts/media.py",
        "scripts/export_ppt.py", "references/commands.md", "references/ppt-output.md",
        "templates/AI回答采集表.xlsx", "templates/软文街_GEO客户素材收集表.xlsx",
        "templates/诊断与执行明细模板.xlsx", "templates/GEO诊断报告模板.pptx",
        "templates/品牌传播与GEO执行方案模板.pptx",
    }
    files = sorted(p for p in skill.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".md", ".json", ".txt", ".py", ".xlsx", ".pptx"})
    relative = {p.relative_to(skill).as_posix() for p in files}
    if required - relative:
        raise ValueError("Missing release files: " + ", ".join(sorted(required - relative)))
    dist = repo / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / "ruanwenjie-geo-0.1.0.zip"
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, "ruanwenjie-geo/" + path.relative_to(skill).as_posix())
    with ZipFile(target) as archive:
        assert archive.testzip() is None, "Corrupt archive"
        assert "ruanwenjie-geo/SKILL.md" in archive.namelist()
        assert len(archive.namelist()) == len(files)
        for path in files:
            assert archive.read("ruanwenjie-geo/" + path.relative_to(skill).as_posix()) == path.read_bytes()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest + "  " + target.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(target), "files": len(files), "bytes": target.stat().st_size, "sha256": digest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
