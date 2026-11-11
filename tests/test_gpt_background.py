"""Background lifecycle checks use mocked HTTP and never call a paid provider."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error


ROOT = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo"
sys.path.insert(0, str(ROOT / "scripts"))
import gpt_client


SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
          "required": ["ok"], "additionalProperties": False}
RESPONSE_ID = "resp_offline_background"


def reply(status="queued", value=None, **changes):
    result = {"id": RESPONSE_ID, "model": gpt_client.MODEL, "status": status, "output": []}
    if status == "completed":
        result["output"] = [{"type": "message", "status": "completed", "content": [
            {"type": "output_text", "text": json.dumps({"ok": True} if value is None else value)}]}]
    result.update(changes)
    return io.BytesIO(json.dumps(result).encode("utf-8"))


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.checkpoint = Path(self.folder.name) / "内部后台任务.json"
        self.key = patch.dict(os.environ, {"OPENAI_API_KEY": "offline-secret"})
        self.key.start()
        self.addCleanup(self.key.stop)
        self.opener = Mock()
        self.network = patch.object(gpt_client.urllib.request, "build_opener", return_value=self.opener)
        self.network.start()
        self.addCleanup(self.network.stop)

    def call(self, payload=None):
        return gpt_client.complete_json("客户分析", {"brand": "虚构客户"} if payload is None else payload,
                                        SCHEMA, checkpoint_path=self.checkpoint)

    def state(self):
        return json.loads(self.checkpoint.read_text(encoding="utf-8"))

    def methods(self):
        return [call.args[0].get_method() for call in self.opener.open.call_args_list]

    def test_initial_post_returns_durable_pending_without_waiting_for_model(self):
        self.opener.open.return_value = reply()
        with self.assertRaises(gpt_client.GPTPending) as pending:
            self.call()
        self.assertEqual(pending.exception.response_id, RESPONSE_ID)
        self.assertEqual(pending.exception.status, "queued")
        self.assertEqual(pending.exception.checkpoint_path, str(self.checkpoint.resolve()))
        state = self.state()
        self.assertEqual(state["status"], "queued")
        self.assertEqual(state["response_id"], RESPONSE_ID)
        self.assertEqual(len(state["request_fingerprint"]), 64)
        record_text = self.checkpoint.read_text(encoding="utf-8")
        self.assertNotIn("offline-secret", record_text)
        self.assertNotIn("虚构客户", record_text)
        request = self.opener.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertTrue(body["background"])
        self.assertFalse(body["store"])
        self.assertEqual(body["model"], "gpt-6.1-sol")
        self.assertEqual(body["reasoning"], {"effort": "max"})
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 90)
        self.assertEqual(self.methods(), ["POST"])

    def test_long_generation_reconnects_get_and_completed_cache_is_network_free(self):
        self.opener.open.side_effect = [reply(), reply("in_progress"), reply("completed")]
        with patch.object(gpt_client, "_now", return_value="2026-11-11T00:00:00+00:00"):
            with self.assertRaises(gpt_client.GPTPending):
                self.call()
        with patch.object(gpt_client, "_now", return_value="2026-11-11T00:20:00+00:00"):
            with self.assertRaises(gpt_client.GPTPending) as pending:
                self.call()
            self.assertEqual(pending.exception.status, "in_progress")
            self.assertEqual(self.call(), {"ok": True})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.call(), {"ok": True})
        self.assertEqual(self.methods(), ["POST", "GET", "GET"])
        for call in self.opener.open.call_args_list[1:]:
            self.assertEqual(call.args[0].full_url, gpt_client.ENDPOINT + "/" + RESPONSE_ID)
            self.assertIsNone(call.args[0].data)
            self.assertEqual(call.kwargs["timeout"], 60)
        self.assertEqual(self.state()["result"], {"ok": True})
        self.assertEqual(list(self.checkpoint.parent.glob("*.tmp")), [])
        state = self.state()
        state['result'] = {'ok': 'corrupted'}
        self.checkpoint.write_text(json.dumps(state), encoding='utf-8')
        with self.assertRaises(gpt_client.GPTError):
            self.call()
        self.assertEqual(self.methods(), ["POST", "GET", "GET"])

    def test_get_network_failure_retains_id_and_can_resume_without_new_post(self):
        self.opener.open.side_effect = [reply(), TimeoutError("offline-secret"), reply("completed")]
        with self.assertRaises(gpt_client.GPTPending):
            self.call()
        with self.assertRaisesRegex(gpt_client.GPTError, "保留") as error:
            self.call()
        self.assertNotIn("offline-secret", str(error.exception))
        self.assertEqual(self.state()["status"], "queued")
        self.assertEqual(self.state()["response_id"], RESPONSE_ID)
        self.assertEqual(self.call(), {"ok": True})
        self.assertEqual(self.methods(), ["POST", "GET", "GET"])

    def test_unknown_post_never_repeats_after_timeout(self):
        self.opener.open.side_effect = TimeoutError("offline-secret")
        with self.assertRaisesRegex(gpt_client.GPTError, "禁止自动重新提交"):
            self.call()
        self.assertEqual(self.state()["status"], "unknown")
        self.assertIsNone(self.state()["response_id"])
        with self.assertRaisesRegex(gpt_client.GPTError, "禁止再次POST"):
            self.call()
        self.assertEqual(self.methods(), ["POST"])
        self.assertNotIn("offline-secret", self.checkpoint.read_text(encoding="utf-8"))

    def test_http_rejection_and_bad_first_response_never_repost(self):
        failures = [
            urllib.error.HTTPError(gpt_client.ENDPOINT, 401, "offline-secret", {}, io.BytesIO(b"private")),
            io.BytesIO(b"not-json"),
            reply(id=None),
        ]
        for index, failure in enumerate(failures):
            with self.subTest(index=index):
                self.checkpoint = Path(self.folder.name) / f"failure-{index}.json"
                self.opener.open.reset_mock()
                self.opener.open.side_effect = failure if isinstance(failure, Exception) else None
                self.opener.open.return_value = failure
                with self.assertRaises(gpt_client.GPTError):
                    self.call()
                self.assertIn(self.state()["status"], {"failed", "unknown"})
                with self.assertRaises(gpt_client.GPTError):
                    self.call()
                self.assertEqual(self.methods(), ["POST"])

    def test_expired_id_does_not_create_replacement(self):
        self.opener.open.side_effect = [reply(), urllib.error.HTTPError(gpt_client.ENDPOINT, 404, "private", {}, io.BytesIO(b"private"))]
        with self.assertRaises(gpt_client.GPTPending):
            self.call()
        with self.assertRaisesRegex(gpt_client.GPTError, "过期"):
            self.call()
        self.assertEqual(self.state()["status"], "expired")
        self.assertEqual(self.state()["response_id"], RESPONSE_ID)
        with self.assertRaises(gpt_client.GPTError):
            self.call()
        self.assertEqual(self.methods(), ["POST", "GET"])

    def test_request_fingerprint_conflict_blocks_get_or_post(self):
        self.opener.open.return_value = reply()
        with self.assertRaises(gpt_client.GPTPending):
            self.call()
        with self.assertRaisesRegex(gpt_client.GPTError, "内容不一致"):
            self.call({"brand": "不同客户"})
        self.assertEqual(self.methods(), ["POST"])

    def test_dictionary_order_does_not_invalidate_identical_request(self):
        self.opener.open.side_effect = [reply(), reply("completed")]
        with self.assertRaises(gpt_client.GPTPending):
            self.call({"a": 1, "b": 2})
        self.assertEqual(self.call({"b": 2, "a": 1}), {"ok": True})
        self.assertEqual(self.methods(), ["POST", "GET"])

    def test_completed_model_schema_and_response_id_are_verified(self):
        failures = [reply("completed", {"ok": "yes"}), reply("completed", model="another-model"),
                    reply("completed", id="resp_other"), reply("incomplete")]
        for index, failure in enumerate(failures):
            with self.subTest(index=index):
                self.checkpoint = Path(self.folder.name) / f"invalid-{index}.json"
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [reply(), failure]
                with self.assertRaises(gpt_client.GPTPending):
                    self.call()
                with self.assertRaises(gpt_client.GPTError):
                    self.call()
                self.assertEqual(self.state()["status"], "failed")
                self.assertNotIn("result", self.state())
                with self.assertRaises(gpt_client.GPTError):
                    self.call()
                self.assertEqual(self.methods(), ["POST", "GET"])

    def test_crashed_submitting_marker_and_corrupt_checkpoint_fail_closed(self):
        self.opener.open.return_value = reply()
        with self.assertRaises(gpt_client.GPTPending):
            self.call()
        state = self.state()
        state.update(status="submitting", response_id=None)
        self.checkpoint.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(gpt_client.GPTError, "禁止再次POST"):
            self.call()
        self.checkpoint.write_text("partial write", encoding="utf-8")
        with self.assertRaisesRegex(gpt_client.GPTError, "记录损坏"):
            self.call()
        self.assertEqual(self.methods(), ["POST"])

    def test_concurrent_same_checkpoint_allows_only_one_post(self):
        entered, release = threading.Event(), threading.Event()
        results = []
        def blocked_request(*_args, **_kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return reply()
        def first():
            try:
                self.call()
            except Exception as error:
                results.append(error)
        self.opener.open.side_effect = blocked_request
        thread = threading.Thread(target=first)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.state()["status"], "submitting")
            with self.assertRaisesRegex(gpt_client.GPTError, "正在处理"):
                self.call()
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], gpt_client.GPTPending)
        self.assertEqual(self.methods(), ["POST"])

    def test_os_lock_releases_after_process_crash(self):
        lock = self.checkpoint.with_name("task.lock")
        script = ("import os,sys; sys.path.insert(0,sys.argv[1]); import gpt_client; "
                  "guard=gpt_client.file_lock(sys.argv[2]); guard.__enter__(); os._exit(0)")
        run = subprocess.run([sys.executable, "-c", script, str(ROOT / "scripts"), str(lock)],
                             capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(lock.exists())
        with gpt_client.file_lock(lock):
            pass


if __name__ == "__main__":
    unittest.main()
