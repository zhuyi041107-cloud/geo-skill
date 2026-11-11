"""Exercise an installed copy independently of the repository path and browser tools."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import fitz


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / ".codebuddy/skills/ruanwenjie-geo"
spec = importlib.util.spec_from_file_location("package_skill", REPO / "tools/package_skill.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class SkillPortabilityTests(unittest.TestCase):
    def test_zip_contains_verified_renderer_font_and_media_catalog(self):
        with tempfile.TemporaryDirectory(prefix="geo-release-") as temp:
            repo = Path(temp) / "发布 中文 空格"
            skill = repo / ".codebuddy/skills/ruanwenjie-geo"
            shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__"))
            with patch.object(packager, "__file__", str(repo / "tools/package_skill.py")):
                packager.main()
            version = re.search(r'^  version:\s*"([^\"]+)"', (skill / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE).group(1)
            target = repo / "dist" / f"ruanwenjie-geo-{version}.zip"
            with ZipFile(target) as archive:
                prefix = "ruanwenjie-geo/"
                manifest = json.loads(archive.read(prefix + "assets/report-assets-manifest.json"))
                for item in manifest["files"]:
                    with self.subTest(resource=item["path"]):
                        raw = archive.read(prefix + item["path"])
                        self.assertEqual(hashlib.sha256(raw).hexdigest(), item["sha256"])
                        self.assertEqual(len(raw), item["bytes"])
                self.assertIn(prefix + "assets/geo-diagnosis-template/font.ttf", archive.namelist())
                self.assertIn(prefix + "assets/geo-diagnosis-template/FONT-NOTICE.txt", archive.namelist())
                self.assertNotIn(prefix + "references/media-catalog.csv.gz", archive.namelist())
                self.assertNotIn(prefix + "scripts/media.py", archive.namelist())
                self.assertNotIn(prefix + "scripts/export_media_word.py", archive.namelist())
                self.assertIn(prefix + "references/plan-category.example.json", archive.namelist())
                self.assertIn(prefix + "references/customer-report.schema.json", archive.namelist())
                self.assertFalse(any(name.endswith(".html") for name in archive.namelist()))

    def test_packaged_server_starts_without_legacy_media_modules(self):
        with tempfile.TemporaryDirectory(prefix="geo-package-runtime-") as temp:
            repo = Path(temp) / "repo"
            source = repo / ".codebuddy/skills/ruanwenjie-geo"
            shutil.copytree(SKILL, source, ignore=shutil.ignore_patterns("__pycache__"))
            with patch.object(packager, "__file__", str(repo / "tools/package_skill.py")):
                packager.main()
            archive = repo / "dist" / "ruanwenjie-geo-0.11.0.zip"
            install = Path(temp) / "install"
            install.mkdir()
            with ZipFile(archive) as z:
                z.extractall(install)
            scripts = install / "ruanwenjie-geo" / "scripts"
            code = ("import asyncio,sys; sys.path.insert(0,sys.argv[1]); import geo_gpt,geo_mcp; "
                    "tools=asyncio.run(geo_mcp.mcp.list_tools()); "
                    "assert 'geo_search_media' not in {x.name for x in tools}; "
                    "assert len(geo_gpt.CUSTOMER_FILES)==2; print('installed MCP ok')")
            result = subprocess.run([sys.executable, "-I", "-c", code, str(scripts)],
                                    capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("installed MCP ok", result.stdout)

    def test_modified_fixed_asset_is_rejected_before_packaging(self):
        with tempfile.TemporaryDirectory(prefix="geo-release-invalid-") as temp:
            repo = Path(temp)
            skill = repo / ".codebuddy/skills/ruanwenjie-geo"
            shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__"))
            font = skill / "assets/geo-diagnosis-template/font.ttf"
            with font.open("ab") as stream:
                stream.write(b"changed")
            with patch.object(packager, "__file__", str(repo / "tools/package_skill.py")):
                with self.assertRaisesRegex(ValueError, "Fixed resource changed"):
                    packager.main()

    def test_relocated_install_generates_both_fixed_reports_without_browser_path(self):
        with tempfile.TemporaryDirectory(prefix="geo-install-") as temp:
            root = Path(temp) / "安装验收 中文 空格"
            skill = root / "技能"
            shutil.copytree(SKILL, skill, ignore=shutil.ignore_patterns("__pycache__"))
            output = root / "客户文件夹" / "正式输出"
            env = os.environ.copy()
            env["PATH"] = str(Path(sys.executable).parent)
            env["PYTHONUTF8"] = "1"
            run = subprocess.run([
                sys.executable, str(skill / "scripts/export_pdf.py"),
                "--project", str(skill / "references/project.example.json"),
                "--plan", str(skill / "references/plan-category.example.json"),
                "--report", str(skill / "references/report.example.json"),
                "--output-dir", str(output),
            ], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            customer = json.loads((skill / "references/report.example.json").read_text(encoding="utf-8"))["customer"]
            for filename, pages in [("GEO诊断报告.pdf", 8), ("品牌传播与GEO执行方案.pdf", 9)]:
                with self.subTest(filename=filename), fitz.open(output / filename) as pdf:
                    self.assertEqual(len(pdf), pages)
                    self.assertTrue(all(abs(page.rect.width - 1200) < 0.01 and abs(page.rect.height - 675) < 0.01 for page in pdf))
                    visible = "\n".join(page.get_text() for page in pdf)
                    self.assertIn(customer["brand"], visible)
                    self.assertNotIn("geo_read_work_context", visible)
                    self.assertNotIn("本轮以豆包网页端联网", visible)
            self.assertFalse(list(output.glob("*.xlsx")))
            self.assertFalse((skill/"references/pdf-review").exists(),"Generating an example must not write into the installed skill")


if __name__ == "__main__":
    unittest.main()
