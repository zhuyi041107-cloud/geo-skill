"""Offline persistence checks. Model requests are mocked; no API is called."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts"
sys.path.insert(0, str(SCRIPTS))
import gpt_client
import gpt_tasks

REAL_FILE_LOCK = gpt_client.file_lock


@contextmanager
def offline_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb"):
        pass
    try:
        yield
    finally:
        path.unlink()


class GPTTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geo-task-offline-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.run = self.workspace / ".work" / "gpt" / "fictional-run"
        self.run.mkdir(parents=True)
        (self.run / "run.json").write_text(json.dumps({"workspace": str(self.workspace)}), encoding="utf-8")
        self.source = self.workspace / "虚构素材.json"
        self.source.write_text('{"brand":"虚构知桥"}', encoding="utf-8")
        self.inputs = {str(self.source): hashlib.sha256(self.source.read_bytes()).hexdigest()}
        self.requests = [{"name": name, "instructions": "核对虚构数据", "payload": {"fictional": True},
                          "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
                          "images": [], "max_output_tokens": 32000} for name in ("diagnosis", "execution")]
        lock = patch.object(gpt_client, "file_lock", offline_lock, create=True)
        lock.start()
        self.addCleanup(lock.stop)

    def create(self, **changes):
        params = {"run_dir": self.run, "kind": "review", "arguments": {"run_dir": str(self.run)},
                  "inputs": self.inputs, "requests": self.requests, "context": {"draft": "fictional"}}
        params.update(changes)
        return gpt_tasks.create_task(**params)

    def test_same_spec_reenters_same_descriptor_and_survives_reload(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first, second)
        self.assertEqual(len(list((self.run / "tasks").glob("*.json"))), 1)
        self.assertEqual(gpt_tasks.load_current(self.run), first)
        gpt_tasks.finish_task(first, {"ok": True})
        changed = self.create(context={"draft": "another-fictional-draft"})
        self.assertNotEqual(first["task_id"], changed["task_id"])
        self.assertTrue((self.run / "tasks" / (first["task_id"] + ".json")).is_file())

    def test_two_requests_resume_with_first_result_cached_and_no_duplicate_submission(self):
        task = self.create()
        submitted, completed, visits = set(), set(), []

        def offline_request(instructions, payload, schema, **kwargs):
            checkpoint = str(kwargs["checkpoint_path"])
            name = kwargs["schema_name"]
            visits.append(name)
            self.assertTrue(Path(checkpoint).is_relative_to(self.run / "requests"))
            if checkpoint in completed:
                return {"ok": True}
            if checkpoint not in submitted:
                submitted.add(checkpoint)
                if name == "execution":
                    raise gpt_client.GPTPending(checkpoint, "resp_offline_execution", "queued")
            completed.add(checkpoint)
            return {"ok": True}

        with patch.object(gpt_client, "complete_json", side_effect=offline_request):
            with self.assertRaises(gpt_client.GPTPending):
                gpt_tasks.run_requests(task)
            task = gpt_tasks.load_current(self.run)
            results = gpt_tasks.run_requests(task)
        self.assertEqual(results, {"diagnosis": {"ok": True}, "execution": {"ok": True}})
        self.assertEqual(len(submitted), 2)
        self.assertEqual(visits, ["diagnosis", "execution", "diagnosis", "execution"])

    def test_result_cache_validates_output_hash_and_never_overwrites(self):
        task = self.create()
        self.assertIsNone(gpt_tasks.cached_result(task))
        output = self.run / "虚构结果.pdf"
        output.write_bytes(b"offline-fixture-output")
        result = {"passed": True, "files": [str(output)]}
        with gpt_tasks.task_lock(task):
            self.assertEqual(gpt_tasks.finish_task(task, result, [output]), result)
        self.assertEqual(gpt_tasks.cached_result(task), result)
        self.assertEqual(gpt_tasks.finish_task(task, result, [output]), result)
        with self.assertRaises(gpt_client.GPTError):
            gpt_tasks.finish_task(task, {"passed": False}, [output])
        output.write_bytes(b"changed")
        with self.assertRaisesRegex(gpt_client.GPTError, "输出已改变"):
            gpt_tasks.cached_result(task)

    def test_changed_input_rejects_before_model_call_or_cached_result(self):
        task = self.create()
        gpt_tasks.finish_task(task, {"ok": True})
        self.source.write_text("changed", encoding="utf-8")
        with patch.object(gpt_client, "complete_json") as model:
            for action in (lambda: gpt_tasks.run_requests(task), lambda: gpt_tasks.load_current(self.run), lambda: gpt_tasks.cached_result(task)):
                with self.assertRaises(gpt_client.GPTError):
                    action()
            model.assert_not_called()

    def test_task_and_result_receipt_corruption_or_model_change_is_rejected(self):
        task = self.create()
        path = self.run / "tasks" / (task["task_id"] + ".json")
        changed = dict(task, context={"rewritten": True})
        path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(gpt_client.GPTError, "哈希"):
            gpt_tasks.load_current(self.run)
        path.write_text(json.dumps(task), encoding="utf-8")
        with patch.object(gpt_client, "REASONING_EFFORT", "medium"):
            with self.assertRaisesRegex(gpt_client.GPTError, "推理强度"):
                gpt_tasks.load_current(self.run)
        gpt_tasks.finish_task(task, {"ok": True})
        receipt_path = self.run / "tasks" / (task["task_id"] + ".result.json")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["result"] = {"ok": False}
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(gpt_client.GPTError, "收据哈希"):
            gpt_tasks.cached_result(task)

    def test_image_input_is_bound_and_workspace_escape_is_rejected(self):
        image = self.workspace / "虚构截图.png"
        image.write_bytes(b"offline-image-placeholder")
        requests = json.loads(json.dumps(self.requests))
        requests[0]["images"] = [{"label": "虚构截图", "path": str(image)}]
        task = self.create(requests=requests)
        self.assertIn(str(image), task["inputs"])
        image.write_bytes(b"changed")
        with self.assertRaises(gpt_client.GPTError):
            gpt_tasks.validate_inputs(task)
        outside = self.workspace.parent / "outside-fictional-input.json"
        with self.assertRaisesRegex(gpt_client.GPTError, "超出"):
            self.create(inputs={str(outside): "0" * 64})
        image.write_bytes(b"offline-image-placeholder")
        with self.assertRaisesRegex(gpt_client.GPTError, "超出"):
            gpt_tasks.finish_task(task, {"ok": True}, [outside])

    def test_duplicate_or_unsafe_request_names_fail_before_descriptor(self):
        for names in (("duplicate", "duplicate"), ("../escape", "safe")):
            requests = [{**item, "name": name} for item, name in zip(self.requests, names)]
            with self.subTest(names=names), self.assertRaises(gpt_client.GPTError):
                self.create(requests=requests)
        self.assertFalse((self.run / "task-current.json").exists())

    def test_real_file_lock_rejects_parallel_finish_and_releases_after_exit(self):
        task = self.create()
        with patch.object(gpt_client, "file_lock", REAL_FILE_LOCK):
            with gpt_tasks.task_lock(task):
                with self.assertRaises(gpt_client.GPTError):
                    with gpt_tasks.task_lock(task):
                        self.fail("Concurrent entry must not execute")
                gpt_tasks.finish_task(task, {"ok": True})
            with gpt_tasks.task_lock(task):
                self.assertEqual(gpt_tasks.cached_result(task), {"ok": True})

    def checkpoint(self, task, name, status):
        path = self.run / "requests" / (task["task_id"] + "-" + name + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"version": 1, "status": status, "request_fingerprint": "a" * 64,
                                    "response_id": "resp_offline_fixture", "model": gpt_client.MODEL,
                                    "result": {"ok": True}}), encoding="utf-8")

    def test_pending_failed_unknown_and_missing_checkpoint_preserve_original_pointer(self):
        task = self.create()
        pointer = self.run / "task-current.json"
        original = pointer.read_bytes()
        for status in (None, "queued", "in_progress", "submitting", "unknown", "failed", "expired", "cancelled"):
            if status is not None:
                self.checkpoint(task, "diagnosis", status)
            with self.subTest(status=status), self.assertRaises(gpt_client.GPTError):
                self.create(arguments={"revision_instructions": "明确调整文案"})
            self.assertEqual(pointer.read_bytes(), original)
            self.assertEqual(len(list((self.run / "tasks").glob("*.json"))), 1)

    def test_only_explicit_same_phase_revision_can_replace_completed_requests_without_business_result(self):
        task = self.create()
        for name in ("diagnosis", "execution"):
            self.checkpoint(task, name, "completed")
        with self.assertRaisesRegex(gpt_client.GPTError, "同阶段修正"):
            self.create(context={"draft": "new"})
        with self.assertRaises(gpt_client.GPTError):
            self.create(kind="plan", arguments={"revision_instructions": "不能跳阶段"})
        revised = self.create(arguments={"revision_instructions": "精简费用页说明并保留同范围报价"})
        self.assertNotEqual(revised["task_id"], task["task_id"])
        self.assertEqual(gpt_tasks.load_current(self.run), revised)
        self.assertTrue((self.run / "tasks" / (task["task_id"] + ".json")).exists())

    def test_valid_business_result_allows_next_phase_but_changed_input_does_not(self):
        task = self.create()
        gpt_tasks.finish_task(task, {"ok": True})
        next_phase = self.create(kind="plan")
        gpt_tasks.finish_task(next_phase, {"ok": True})
        pointer = (self.run / "task-current.json").read_bytes()
        self.source.write_text("updated-client-facts", encoding="utf-8")
        inputs = {str(self.source): hashlib.sha256(self.source.read_bytes()).hexdigest()}
        with self.assertRaisesRegex(gpt_client.GPTError, "输入文件已变化"):
            self.create(kind="report", inputs=inputs)
        self.assertEqual((self.run / "task-current.json").read_bytes(), pointer)

    def test_real_run_registration_lock_blocks_concurrent_different_spec(self):
        task = self.create()
        pointer = (self.run / "task-current.json").read_bytes()
        with patch.object(gpt_client, "file_lock", REAL_FILE_LOCK):
            with gpt_client.file_lock(self.run / "tasks" / ".registration.lock"):
                with self.assertRaises(gpt_client.GPTError):
                    self.create(arguments={"revision_instructions": "不同请求也不能并发注册"})
        self.assertEqual((self.run / "task-current.json").read_bytes(), pointer)
        self.assertEqual(gpt_tasks.load_current(self.run), task)

    def test_reentering_completed_historical_task_preserves_latest_active_pointer(self):
        first = self.create()
        gpt_tasks.finish_task(first, {"version": "A"})
        newer = self.create(arguments={"revision_instructions": "明确修正为B版本"})
        gpt_tasks.finish_task(newer, {"version": "B"})
        pointer = (self.run / "task-current.json").read_bytes()
        historical = self.create()
        self.assertEqual(historical["task_id"], first["task_id"])
        self.assertEqual(gpt_tasks.cached_result(historical), {"version": "A"})
        self.assertEqual((self.run / "task-current.json").read_bytes(), pointer)
        self.assertEqual(gpt_tasks.load_current(self.run), newer)

    def test_historical_cache_cannot_displace_pending_active_task(self):
        historical = self.create()
        gpt_tasks.finish_task(historical, {"version": "A"})
        pending = self.create(arguments={"revision_instructions": "明确修正为B版本"})
        self.checkpoint(pending, "diagnosis", "queued")
        pointer = (self.run / "task-current.json").read_bytes()
        with self.assertRaisesRegex(gpt_client.GPTError, "geo_resume_task"):
            self.create()
        self.assertEqual((self.run / "task-current.json").read_bytes(), pointer)
        self.assertEqual(gpt_tasks.load_current(self.run), pending)


if __name__ == "__main__":
    unittest.main()
