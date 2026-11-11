import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


ROOT = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo"
sys.path.insert(0, str(ROOT / "scripts"))
import gpt_client
import render_geo_diagnosis as renderer


SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}


def response(value=None, **changes):
    result = {"id": "resp_offline_test", "status": "completed", "model": gpt_client.MODEL,
              "output": [{"type": "message", "status": "completed", "content": [{"type": "output_text", "text": json.dumps({"ok": True} if value is None else value)}]}]}
    result.update(changes)
    return result


class GPTClientTests(unittest.TestCase):
    def call(self, value=None, **kwargs):
        opener = unittest.mock.Mock()
        opener.open.return_value = io.BytesIO(json.dumps(value or response()).encode("utf-8"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-secret"}), patch.object(gpt_client.urllib.request, "build_opener", return_value=opener):
            result = gpt_client.complete_json("业务分析", {"customer": "测试"}, SCHEMA, **kwargs)
        return result, opener

    def test_request_fixed_model_store_false_strict_and_single_call(self):
        value, opener = self.call()
        self.assertEqual(value, {"ok": True})
        self.assertEqual(opener.open.call_count, 1)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "gpt-6.1-sol")
        self.assertFalse(body["store"])
        self.assertEqual(body["reasoning"], {"effort": "max"})
        self.assertEqual(body["truncation"], "disabled")
        self.assertEqual(body["max_output_tokens"], 32000)
        self.assertNotIn("context_window", body)
        self.assertNotIn("model_context_window", body)
        self.assertEqual(gpt_client.MODEL_CONTEXT_WINDOW_TOKENS, 1_050_000)
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 600)

    def test_missing_key_fails_without_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(gpt_client.urllib.request, "build_opener") as opener:
            with self.assertRaisesRegex(gpt_client.GPTError, "OPENAI_API_KEY"):
                gpt_client.complete_json("分析", {}, SCHEMA)
            opener.assert_not_called()

    def test_provider_failures_never_echo_key_or_body_and_do_not_retry(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError(gpt_client.ENDPOINT, 401, "secret-customer offline-secret", {}, io.BytesIO(b"secret-customer"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-secret"}), patch.object(gpt_client.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(gpt_client.GPTError) as error:
                gpt_client.complete_json("分析", {}, SCHEMA)
        self.assertIn("401", str(error.exception))
        self.assertNotIn("offline-secret", str(error.exception))
        self.assertNotIn("secret-customer", str(error.exception))
        self.assertEqual(opener.open.call_count, 1)

    def test_refusal_incomplete_wrong_model_and_schema_rejected(self):
        invalid = [response(status="incomplete"), response(model="another-model"), response({"ok": "true"}),
                   response({"ok": True, "extra": "x"}), response(output=[{"type": "message", "content": None}]),
                   response(output=[{"type": "message", "content": [{"type": "refusal", "refusal": "private"}]}])]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(gpt_client.GPTError):
                    self.call(value)

    def test_visual_review_transmits_labeled_image_bytes(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "审核页.png"
            png = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2, 2), False)
            png.clear_with(255)
            png.save(path)
            value, opener = self.call(images=[{"label": "诊断报告第1页", "path": path}])
        self.assertTrue(value["ok"])
        content = json.loads(opener.open.call_args.args[0].data)["input"][0]["content"]
        self.assertEqual(content[1], {"type": "input_text", "text": "诊断报告第1页"})
        self.assertTrue(content[2]["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(content[2]["detail"], "high")

    def test_non_image_cannot_be_sent_as_review_image(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fake.png"
            path.write_text("not an image", encoding="utf-8")
            with self.assertRaises(gpt_client.GPTError):
                self.call(images=[{"label": "page", "path": path}])

    def test_bmp_and_multipage_tiff_convert_all_pages_and_gif_stays_intact(self):
        fixtures = [
            ("bmp", "Qk1OAAAAAAAAADYAAAAoAAAAAgAAAAMAAAABABgAAAAAABgAAADEDgAAxA4AAAAAAAAAAAAA////////AAD///////8AAP///////wAA", 1, "image/png"),
            ("tiff", "SUkqAAgAAAAKAAABBAABAAAAAgAAAAEBBAABAAAAAwAAAAIBAwADAAAAhgAAAAMBAwABAAAAAQAAAAYBAwABAAAAAgAAABEBBAABAAAAjAAAABUBAwABAAAAAwAAABYBBAABAAAAAwAAABcBBAABAAAAEgAAABwBAwABAAAAAQAAAKgAAAAIAAgACAD///////////////////////8AAElJKgAIAAAACgAAAQQAAQAAAAIAAAABAQQAAQAAAAMAAAACAQMAAwAAACYBAAADAQMAAQAAAAEAAAAGAQMAAQAAAAIAAAARAQQAAQAAACwBAAAVAQMAAQAAAAMAAAAWAQQAAQAAAAMAAAAXAQQAAQAAABIAAAAcAQMAAQAAAAEAAAAAAAAACAAIAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAA=", 2, "image/png"),
            ("gif", "R0lGODdhAgADAIEAAP///wAAAAAAAAAAACwAAAAAAgADAAAIBgABCBwYEAA7", 1, "image/gif"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            for extension, encoded, count, mime in fixtures:
                with self.subTest(extension=extension):
                    path = Path(folder) / ("screenshot." + extension)
                    raw = base64.b64decode(encoded)
                    path.write_bytes(raw)
                    _, opener = self.call(images=[{"label": "原始截图", "path": path}])
                    content = json.loads(opener.open.call_args.args[0].data)["input"][0]["content"]
                    images = [part for part in content if part["type"] == "input_image"]
                    self.assertEqual(len(images), count)
                    self.assertTrue(all(part["image_url"].startswith("data:" + mime + ";base64,") for part in images))
                    if extension == "gif":
                        self.assertEqual(base64.b64decode(images[0]["image_url"].split(",", 1)[1]), raw)
                    if count == 2:
                        self.assertIn("第2页", content[3]["text"])

    def test_request_limits_fail_before_network_without_silent_truncation(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-secret"}), patch.object(gpt_client, "MAX_REQUEST_BYTES", 16), patch.object(gpt_client.urllib.request, "build_opener") as opener:
            with self.assertRaisesRegex(gpt_client.GPTError, "请求超过"):
                gpt_client.complete_json("分析", {"text": "a" * 100}, SCHEMA)
            opener.assert_not_called()
        image = {"type": "input_image", "image_url": "data:image/png;base64,YQ==", "detail": "high"}
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-secret"}), patch.object(gpt_client, "MAX_IMAGES", 1), patch.object(gpt_client, "_image_content", return_value=[image]), patch.object(gpt_client.urllib.request, "build_opener") as opener:
            with self.assertRaisesRegex(gpt_client.GPTError, "最多支持"):
                gpt_client.complete_json("分析", {}, SCHEMA, images=[{}, {}])
            opener.assert_not_called()

    def test_api_adapter_roundtrip_retains_original_contract_and_sealed_bytes(self):
        path = ROOT / "references/customer-report.schema.json"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        report = json.loads((ROOT / "references/report.example.json").read_text(encoding="utf-8"))
        api = gpt_client.report_to_api(report)
        self.assertEqual(list(api["diagnosis"]["pages"]), [f"page_{i:02d}" for i in range(1, 9)])
        self.assertEqual(list(api["execution"]["pages"]), [f"page_{i:02d}" for i in range(1, 10)])
        self.assertEqual(list(api["execution"]["pages"]["page_09"]["items"]), ["item_01", "item_02"])
        restored = gpt_client.report_from_api(api)
        self.assertEqual(restored, report)
        self.assertEqual(renderer.validate_report(restored), [])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_api_schema_is_strict_and_omits_all_computed_fields(self):
        def walk(schema):
            self.assertNotIn("prefixItems", schema)
            self.assertNotIn("readOnly", schema)
            self.assertNotIn("uniqueItems", schema)
            self.assertNotIn("const", schema)
            if schema.get("type") == "object":
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                self.assertFalse(schema["additionalProperties"])
                for child in schema["properties"].values():
                    walk(child)
            if "items" in schema:
                walk(schema["items"])
            for child in schema.get("anyOf", []):
                walk(child)
        schema = gpt_client.report_api_schema()
        walk(schema)
        media_card = schema["properties"]["execution"]["properties"]["pages"]["properties"]["page_05"]["properties"]["items"]["items"]
        self.assertNotIn("amount", media_card["properties"])
        self.assertNotIn("quantity", media_card["properties"])
        quote = schema["properties"]["execution"]["properties"]["pages"]["properties"]["page_09"]["properties"]["items"]["properties"]["item_01"]
        self.assertNotIn("total", quote["properties"])

    def test_fixed_titles_injection_and_missing_page_fail(self):
        report = json.loads((ROOT / "references/report.example.json").read_text(encoding="utf-8"))
        api = gpt_client.report_to_api(report)
        changes = []
        value = copy.deepcopy(api); del value["diagnosis"]["pages"]["page_08"]; changes.append(value)
        value = copy.deepcopy(api); value["execution"]["pages"]["page_01"]["title"] = "临时新标题"; changes.append(value)
        value = copy.deepcopy(api); value["execution"]["pages"]["page_09"]["items"]["item_01"]["total"] = "2000"; changes.append(value)
        value = copy.deepcopy(api); value["diagnosis"]["pages"]["page_01"]["headline"] = "SKILL.md"; changes.append(value)
        for value in changes:
            with self.subTest():
                with self.assertRaises(gpt_client.GPTError):
                    gpt_client.report_from_api(value)


if __name__ == "__main__":
    unittest.main()
