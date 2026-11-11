from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import openpyxl
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts"
sys.path.insert(0, str(SCRIPTS))
import geo_data
import gpt_evidence


class GPTEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "内部原件.xlsx"
        self.project = {
            "project_id": "fictional-gpt-test", "client_name": "虚构知桥", "brand_names": ["知桥"],
            "contexts": [{"platform": "虚构平台", "mode": "网页端", "online": "是", "round": 1}],
            "questions": [
                {"question_id": "Q001", "type": "自然需求", "intent": "推荐", "text": "知识服务平台有哪些？"},
                {"question_id": "Q002", "type": "品牌认知", "intent": "认知", "text": "知桥是什么？"},
            ],
            "collection_convention": "按本轮约定记录", "currency": "CNY",
        }
        geo_data.prepare_internal(self.project, self.source)
        book = openpyxl.load_workbook(self.source)
        for index, answer in ((2, "可选知桥与其他平台。"), (3, "知桥是知识服务平台。")):
            for header, value in {"采集状态": "已完成", "回答全文": answer, "引用展示": "未展示", "备注": "原始采集位置"}.items():
                book["回答记录"].cell(index, geo_data.SAMPLE_HEADERS.index(header) + 1, value)
        book.save(self.source)
        book.close()
        self.judgments = [
            {"sample_id": "Q001-C001-R01", "mention": "是", "recommendation": "是", "reason": "原答将知桥列入候选。"},
            {"sample_id": "Q002-C001-R01", "mention": "是", "recommendation": "否", "reason": "只介绍品牌定位，没有推荐。"},
        ]

    def set_images(self, paths, loose=None):
        book = openpyxl.load_workbook(self.source)
        book["回答记录"].cell(2, geo_data.SAMPLE_HEADERS.index("回答证据路径") + 1, "\n".join(map(str, paths)))
        if loose is not None:
            sheet = book["项目配置"]
            index = max(row[0].row for row in sheet if row[0].value) + 1
            sheet.cell(index, 1, "unlocated_screenshots")
            sheet.cell(index, 2, json.dumps(loose, ensure_ascii=False))
        book.save(self.source)
        book.close()

    def test_bundle_preserves_full_answers_and_sends_all_images_with_labels(self):
        first, second = self.root / "第一张.png", self.root / "第二张.png"
        for path in (first, second):
            Image.new("RGB", (4, 4), "white").save(path)
        self.set_images([first, second.name], [{"path": str(second), "original_location": "原表第4行"}])
        before = self.source.read_bytes()
        analysis, images = gpt_evidence.evidence_bundle(self.source)
        self.assertEqual(analysis["samples"][0]["回答全文"], "可选知桥与其他平台。")
        self.assertEqual(analysis["samples"][0]["品牌提及"], "待判")
        self.assertEqual({item["path"] for item in images}, {first.resolve(), second.resolve()})
        self.assertIn("Q001-C001-R01", images[0]["label"])
        self.assertIn("未定位截图", images[1]["label"])
        self.assertEqual(before, self.source.read_bytes())

    def test_bundle_rejects_missing_image_or_path_outside_internal_directory(self):
        outside = self.root.parent / "outside.png"
        for bad, message in (("不存在.png", "不存在"), (outside, "超出")):
            with self.subTest(path=str(bad)):
                self.set_images([bad])
                with self.assertRaisesRegex(ValueError, message):
                    gpt_evidence.evidence_bundle(self.source)

    def test_judgment_copy_updates_statistics_preserves_original_and_notes(self):
        before = self.source.read_bytes()
        out = self.root / "副本" / "GPT判读.xlsx"
        analysis = gpt_evidence.judged_copy(self.source, self.judgments, out)
        self.assertEqual(analysis["groups"][0]["mention_rate"], 1)
        self.assertEqual(analysis["groups"][0]["recommendation_rate"], 1)
        self.assertEqual(analysis["samples"][1]["品牌推荐"], "否")
        self.assertIn("原始采集位置", analysis["samples"][0]["备注"])
        self.assertIn("原答将知桥列入候选", analysis["samples"][0]["备注"])
        self.assertEqual(before, self.source.read_bytes())
        self.assertEqual(geo_data.analyze(self.source)["samples"][0]["品牌提及"], "待判")
        with self.assertRaises(FileExistsError):
            gpt_evidence.judged_copy(self.source, self.judgments, out)
        with self.assertRaises(FileExistsError):
            gpt_evidence.judged_copy(self.source, self.judgments, self.source)

    def test_judgments_require_exact_coverage_and_consistency_before_any_output(self):
        extra = copy.deepcopy(self.judgments)
        extra.append({**extra[0], "sample_id": "UNKNOWN"})
        cases = [self.judgments[:1], self.judgments + self.judgments[:1], extra,
                 [{**self.judgments[0], "mention": "否"}, self.judgments[1]],
                 [{**self.judgments[0], "reason": ""}, self.judgments[1]]]
        for index, value in enumerate(cases):
            out = self.root / f"invalid-{index}" / "判读.xlsx"
            with self.subTest(index=index), self.assertRaises(ValueError):
                gpt_evidence.judged_copy(self.source, value, out)
            self.assertFalse(out.parent.exists())


if __name__ == "__main__":
    unittest.main()
