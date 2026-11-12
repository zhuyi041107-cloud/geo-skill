"""Exercise an installed copy independently of the repository path and browser tools."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
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

# A clean Python process must complete local work even if every service import and network connection is forbidden.
NO_SERVICES = '''
import sys
def no_services(event, args):
    if event == "import" and args[0].split(".")[0] in {"mcp", "openai", "geo_mcp", "geo_gpt", "gpt_client", "gpt_tasks"}:
        raise AssertionError("Service import: " + args[0])
    if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
        raise AssertionError("Network access: " + event)
sys.addaudithook(no_services)
'''


class SkillPortabilityTests(unittest.TestCase):
    def test_zip_contains_fixed_assets_and_complete_service_free_workflow(self):
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
                for excluded in ("requirements-mcp.txt", "scripts/geo_mcp.py", "scripts/geo_gpt.py",
                                 "scripts/gpt_client.py", "scripts/gpt_tasks.py", "scripts/setup_local_mcp.ps1",
                                 "scripts/launch_local_mcp.ps1", "references/local-mcp.md",
                                 "references/workbuddy-mcp.example.json"):
                    self.assertNotIn(prefix + excluded, archive.namelist())
                self.assertIn(prefix + "scripts/gpt_evidence.py", archive.namelist())
                requirements = archive.read(prefix + "requirements.txt").decode("utf-8")
                self.assertNotIn("mcp", requirements.lower())
                self.assertNotIn("openai", requirements.lower())
                for name in archive.namelist():
                    if name.endswith(".md"):
                        for target in re.findall(r'\]\(([^)#]+)(?:#[^)]*)?\)', archive.read(name).decode("utf-8")):
                            if "://" not in target:
                                linked = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                                self.assertIn(linked, archive.namelist(), (name, target))
                self.assertFalse(any(name.endswith(".html") for name in archive.namelist()))

    def test_packaged_manual_judgment_pipeline_without_mcp_api_or_network(self):
        with tempfile.TemporaryDirectory(prefix="geo-package-runtime-") as temp:
            repo = Path(temp) / "repo"
            source = repo / ".codebuddy/skills/ruanwenjie-geo"
            shutil.copytree(SKILL, source, ignore=shutil.ignore_patterns("__pycache__"))
            with patch.object(packager, "__file__", str(repo / "tools/package_skill.py")):
                packager.main()
            archive = next((repo / "dist").glob("*.zip"))
            install = Path(temp) / "install"
            install.mkdir()
            with ZipFile(archive) as z:
                z.extractall(install)
            code = NO_SERVICES + '''
import hashlib, json, runpy
from pathlib import Path
import openpyxl
skill, work = Path(sys.argv[1]), Path(sys.argv[2])
work.mkdir()
sys.path.insert(0, str(skill / "scripts"))
def cli(*args):
    sys.argv = [str(skill / "scripts/geo_data.py"), *map(str, args)]
    runpy.run_path(sys.argv[0], run_name="__main__")
project = skill / "references/project.example.json"
plan = skill / "references/plan-category.example.json"
collected, original, judged = [work / name for name in ("采集表.xlsx", "内部原答.xlsx", "内部判读.xlsx")]
cli("prepare", "--project", project, "--out", collected)
book = openpyxl.load_workbook(collected)
assert book.active.max_column == 3
for row in book.active.iter_rows(min_row=2):
    if row[0].value:
        row[2].value = "知桥协同提供知识服务。这里只介绍业务。"
book.save(collected)
book.close()
collected_hash = hashlib.sha256(collected.read_bytes()).digest()
cli("normalize", "--input", collected, "--project", project, "--context", "1", "--out", original)
original_hash = hashlib.sha256(original.read_bytes()).digest()
cli("analyze", "--input", original, "--out", work / "raw.json")
raw = json.loads((work / "raw.json").read_text(encoding="utf-8"))
assert all(row["品牌提及"] == "待判" for row in raw["samples"])
judgments = [{"sample_id": row["sample_id"], "mention": "是", "recommendation": "否",
              "reason": "只介绍服务，没有推荐。"} for row in raw["samples"]]
(work / "judgments.json").write_text(json.dumps(judgments, ensure_ascii=False), encoding="utf-8")
cli("judge", "--input", original, "--judgments", work / "judgments.json", "--out", judged)
cli("analyze", "--input", judged, "--plan", plan, "--out", work / "final.json")
final = json.loads((work / "final.json").read_text(encoding="utf-8"))
assert all(row["品牌提及"] == "是" and row["品牌推荐"] == "否" for row in final["samples"])
assert final["budget"]["client"]["total"] == "20400.00"
assert hashlib.sha256(collected.read_bytes()).digest() == collected_hash
assert hashlib.sha256(original.read_bytes()).digest() == original_hash
print("installed manual pipeline ok")
'''
            result = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(install / "ruanwenjie-geo"), str(Path(temp) / "客户 中文 空格")],
                                    capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("installed manual pipeline ok", result.stdout)

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
            source = root / ".codebuddy/skills/ruanwenjie-geo"
            shutil.copytree(SKILL, source, ignore=shutil.ignore_patterns("__pycache__"))
            with patch.object(packager, "__file__", str(root / "tools/package_skill.py")):
                packager.main()
            with ZipFile(next((root / "dist").glob("*.zip"))) as archive:
                archive.extractall(root / "安装技能")
            skill = root / "安装技能/ruanwenjie-geo"
            output = root / "客户文件夹" / "正式输出"
            env = os.environ.copy()
            env["PATH"] = str(Path(sys.executable).parent)
            env["PYTHONUTF8"] = "1"
            run = subprocess.run([
                sys.executable, "-X", "utf8", "-c", NO_SERVICES + "\nimport runpy; sys.path.insert(0, str(__import__('pathlib').Path(sys.argv[1]).parent)); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')", str(skill / "scripts/export_pdf.py"),
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
