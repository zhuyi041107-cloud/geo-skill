"""Use the real stdio protocol without an API key or network calls."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo"
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None


@unittest.skipUnless(ClientSession, "Install requirements-mcp.txt for protocol checks")
class MCPProtocolTests(unittest.TestCase):
    def test_server_import_does_not_pollute_protocol_stdout(self):
        run = subprocess.run([sys.executable, "-c",
                              "import sys; sys.path.insert(0,sys.argv[1]); import geo_mcp",
                              str(SKILL / "scripts")], capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(run.stdout, b"")

    def check_protocol(self, use_launcher):
        async def run(root):
            env = os.environ.copy()
            env.pop("OPENAI_API_KEY", None)
            env["LOCALAPPDATA"] = str(root / "private")
            env["GEO_WORKSPACE"] = str(root)
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            command = sys.executable
            args = [str(SKILL / "scripts/geo_mcp.py")]
            if use_launcher:
                command = shutil.which("powershell.exe")
                args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-File", str(SKILL / "scripts/launch_local_mcp.ps1"),
                        "-PythonExe", sys.executable, "-ServerPath", str(SKILL / "scripts/geo_mcp.py")]
            server = StdioServerParameters(command=command, args=args, env=env)
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    initialized = await session.initialize()
                    self.assertTrue(initialized.serverInfo.name)
                    tools = await session.list_tools()
                    self.assertEqual({t.name for t in tools.tools}, {
                        "geo_status", "geo_analyze_customer", "geo_create_plan",
                        "geo_write_reports", "geo_review_deliverables", "geo_resume_task", "geo_publish"})
                    result = await session.call_tool("geo_status", {})
                    self.assertFalse(result.isError)
                    value = json.loads(result.content[0].text)
                    self.assertEqual(value["model"], "gpt-6.1-sol")
                    self.assertEqual(value["reasoning_effort"], "max")
                    self.assertEqual(value["model_context_window_tokens"], 1_050_000)
                    self.assertFalse(value["api_key_configured"])
                    self.assertTrue(value["workspace_configured"])
                    failed = await session.call_tool("geo_analyze_customer", {
                        "workspace": str(root), "project_file": str(root / "missing.json"),
                        "answers_file": str(root / "missing.xlsx")})
                    self.assertTrue(failed.isError)
                    self.assertIn("未配置", failed.content[0].text)
        with tempfile.TemporaryDirectory(prefix="geo-mcp-protocol-") as folder:
            asyncio.run(asyncio.wait_for(run(Path(folder)), timeout=45))

    def test_direct_stdio_handshake_tools_and_missing_key(self):
        self.check_protocol(False)

    @unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows launcher required")
    def test_workbuddy_windows_launcher_preserves_live_mcp_protocol(self):
        self.check_protocol(True)

    def test_generation_and_resume_pending_become_normal_tool_results(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        self.addCleanup(sys.path.remove, str(SKILL / "scripts"))
        import geo_mcp
        import gpt_client

        with tempfile.TemporaryDirectory(prefix="geo-mcp-pending-") as folder:
            run = Path(folder).resolve() / "run"
            checkpoint = run / "requests" / "analysis.json"
            calls = [
                ("geo_analyze_customer", "analyze_customer", (str(run), "project.json", "answers.xlsx")),
                ("geo_create_plan", "create_plan", (str(run),)),
                ("geo_write_reports", "write_reports", (str(run),)),
                ("geo_review_deliverables", "review_deliverables", (str(run),)),
                ("geo_resume_task", "resume_task", (str(run),)),
            ]
            for tool_name, business_name, args in calls:
                with self.subTest(tool=tool_name), patch.object(
                    geo_mcp.geo_gpt, business_name,
                    side_effect=gpt_client.GPTPending(checkpoint, "resp_offline_pending", "in_progress"),
                ):
                    value = getattr(geo_mcp, tool_name)(*args)
                    self.assertEqual(value["status"], "pending")
                    self.assertEqual(Path(value["run_dir"]), run)
                    self.assertEqual(value["response_id"], "resp_offline_pending")
                    self.assertEqual(value["provider_status"], "in_progress")
                    self.assertEqual(value["resume_tool"], "geo_resume_task")
                    self.assertEqual(value["retry_after_seconds"], 20)

    def test_resume_returns_completed_result_and_other_errors_are_not_pending(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        self.addCleanup(sys.path.remove, str(SKILL / "scripts"))
        import geo_mcp
        import gpt_client

        complete = {"status": "completed", "plan_file": "offline-plan.json"}
        with patch.object(geo_mcp.geo_gpt, "resume_task", return_value=complete) as resume:
            self.assertIs(geo_mcp.geo_resume_task("offline-run"), complete)
            resume.assert_called_once_with("offline-run")
        with patch.object(geo_mcp.geo_gpt, "resume_task", side_effect=gpt_client.GPTError("任务已过期")):
            with self.assertRaisesRegex(gpt_client.GPTError, "已过期"):
                geo_mcp.geo_resume_task("offline-run")


if __name__ == "__main__":
    unittest.main()
