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
                        "geo_status", "geo_analyze_customer", "geo_search_media", "geo_create_plan",
                        "geo_write_reports", "geo_review_deliverables", "geo_publish"})
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


if __name__ == "__main__":
    unittest.main()
