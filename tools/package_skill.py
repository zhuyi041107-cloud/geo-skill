"""Build the standalone WorkBuddy ZIP from the canonical project skill."""

import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def main():
    repo = Path(__file__).resolve().parents[1]
    skill = repo / ".codebuddy/skills/ruanwenjie-geo"
    required = {
        "SKILL.md", "requirements.txt", "scripts/geo_data.py",
        "scripts/export_pdf.py", "references/commands.md", "references/pdf-output.md",
        "references/template-generation.md", "references/customer-report.schema.json",
        "references/report.example.json", "references/project.example.json", "references/plan-category.example.json",
        "references/report-thinking.md", "references/workflow.md", "references/evidence-and-planning.md",
        "references/内部判读底表.xlsx",
        "templates/AI回答采集表.xlsx", "templates/软文街_GEO客户素材收集表.xlsx",
        "templates/GEO诊断报告版式示例.pdf", "templates/品牌传播与GEO执行方案版式示例.pdf",
        "scripts/render_geo_diagnosis.py", "scripts/check_client_report.py",
        "assets/report-assets-manifest.json", "assets/client-report-process-patterns.json",
        "assets/geo-diagnosis-template/backgrounds.pdf", "assets/geo-diagnosis-template/font.ttf",
        "assets/geo-execution-template/backgrounds.pdf",
        "assets/geo-diagnosis-template/FONT-NOTICE.txt",
        "assets/geo-diagnosis-template/doubao.png", "assets/geo-diagnosis-template/qwen.png",
        "assets/geo-diagnosis-template/deepseek.png",
        "scripts/gpt_evidence.py",
    }
    required.update({
        "scripts/brand_plan.py", "scripts/render_brand_report.py",
        "references/brand-report.schema.json", "references/brand-report.example.json",
        "references/brand-plan.example.json", "references/pricing-contract.md",
        "references/strategy-playbook.md", "references/legacy-fixed-rules.md",
    })
    library = skill / "references/case-library"
    library_manifest = json.loads((library / "manifest.json").read_text(encoding="utf-8"))
    required.update(path.relative_to(skill).as_posix() for path in library.glob("*.md"))
    required.add("references/case-library/manifest.json")
    reference_files = []
    for case in library_manifest["cases"]:
        for info in case["files"]:
            path = (library / info["path"]).resolve()
            if not path.is_relative_to((library / "sources").resolve()) or not path.is_file():
                raise ValueError("Invalid reference resource: " + info["path"])
            raw = path.read_bytes()
            if len(raw) != info["bytes"] or hashlib.sha256(raw).hexdigest() != info["sha256"]:
                raise ValueError("Reference changed after review: " + info["path"])
            reference_files.append(path)
    if len(reference_files) != library_manifest["source_document_count"] or len(set(reference_files)) != len(reference_files):
        raise ValueError("Reference manifest contains missing or duplicate documents")
    # Only ship the standalone workflow; historical API/MCP tools stay in the repository.
    files = sorted(skill / name for name in required if (skill / name).is_file())
    relative = {p.relative_to(skill).as_posix() for p in files}
    if required - relative:
        raise ValueError("Missing release files: " + ", ".join(sorted(required - relative)))
    manifest = json.loads((skill / "assets/report-assets-manifest.json").read_text(encoding="utf-8"))
    for info in manifest["files"]:
        name = info["path"]
        resource = (skill / name).resolve()
        if not resource.is_relative_to(skill.resolve()) or name not in relative:
            raise ValueError("Invalid or unpackaged fixed resource: " + name)
        raw = resource.read_bytes()
        if len(raw) != info["bytes"] or hashlib.sha256(raw).hexdigest() != info["sha256"]:
            raise ValueError("Fixed resource changed after review: " + name)
    dist = repo / "dist"
    dist.mkdir(exist_ok=True)
    version = re.search(r'^  version:\s*"([0-9]+\.[0-9]+\.[0-9]+)"', (skill / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    if not version:
        raise ValueError("Missing release version in SKILL.md metadata")
    if manifest.get("version") != version.group(1):
        raise ValueError("Fixed resource manifest version does not match SKILL.md")
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
        assert not any(name.endswith(".pptx") for name in archive.namelist()), "PPT belongs only in reference packs"
    # Reference originals are already compressed; split them below GitHub's per-file limit.
    packs = [[]]
    max_pack_bytes = 60 * 1024 * 1024
    for path in sorted(reference_files, key=lambda p: (-p.stat().st_size, p.as_posix())):
        if path.stat().st_size > max_pack_bytes:
            raise ValueError("Reference exceeds pack limit: " + path.name)
        for pack in packs:
            if sum(p.stat().st_size for p in pack) + path.stat().st_size <= max_pack_bytes:
                pack.append(path)
                break
        else:
            packs.append([path])
    targets = [target]
    for number, pack in enumerate(packs, 1):
        part = dist / f"ruanwenjie-geo-{version.group(1)}-references-{number:02}.zip"
        with ZipFile(part, "w", ZIP_STORED) as archive:
            for path in sorted(pack):
                archive.write(path, "ruanwenjie-geo/" + path.relative_to(skill).as_posix())
        with ZipFile(part) as archive:
            assert archive.testzip() is None
            for path in pack:
                assert archive.read("ruanwenjie-geo/" + path.relative_to(skill).as_posix()) == path.read_bytes()
        targets.append(part)
    installation = {"version": version.group(1), "root": "ruanwenjie-geo", "required_parts": []}
    for part in targets:
        if part.stat().st_size >= 100 * 1024 * 1024:
            raise ValueError("Release exceeds GitHub file limit: " + part.name)
        part_digest = hashlib.sha256(part.read_bytes()).hexdigest()
        part.with_suffix(".zip.sha256").write_text(part_digest + "  " + part.name + "\n", encoding="ascii")
        installation["required_parts"].append({"file": part.name, "bytes": part.stat().st_size, "sha256": part_digest})
    install_path = dist / f"ruanwenjie-geo-{version.group(1)}-install.json"
    install_path.write_text(json.dumps(installation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest + "  " + target.name + "\n", encoding="ascii")
    print(json.dumps({"archive": str(target), "files": len(files), "bytes": target.stat().st_size,
                      "unpacked_bytes": sum(p.stat().st_size for p in files + reference_files), "sha256": digest, "parts": installation["required_parts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
