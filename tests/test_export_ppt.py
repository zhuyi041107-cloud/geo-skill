"""Small behavioral checks for customer data isolation and complete pagination."""

import copy
from pathlib import Path
import tempfile
import unittest
import sys

from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts"))

import export_ppt
from geo_data import calculate_budget


class ExportPptTests(unittest.TestCase):
    def fixture(self):
        project = {"project_id": "demo", "client_name": "演示客户", "brand_names": ["演示品牌"], "currency": "CNY", "budget_limit": "10000.00"}
        plan = {
            "contents": [{"content_id": "C1", "title": "选题示例", "status": "待确认", "question_ids": ["Q1"]}],
            "placements": [
                {"placement_id": "P1", "content_id": "C1", "media_id": "M1", "media_name": "已选媒体示例", "status": "已选", "unit_price": "123.45", "client_unit_price": "789.01", "price_tier": "内部成本档位SECRET", "quantity": 1, "scheduled_date": "2026-11-20"},
                {"placement_id": "P2", "content_id": "C1", "media_id": "M2", "media_name": "候选媒体SECRET", "status": "候选", "unit_price": "99.00", "client_unit_price": "99.00", "quantity": 1},
            ], "fees": [],
        }
        analysis = {"schema_version": 1, "project": project, "groups": [], "counts": {}, "budget": calculate_budget(project, plan)}
        return analysis, plan

    def test_customer_price_and_stale_plan(self):
        analysis, plan = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            report = {"targets": [{"title": "提及与引用", "detail": "待建立基线", "method": "相同问句与条件，独立新对话，按平台、模式、轮次与意图分别统计。"}]}
            path = export_ppt.export("execution", analysis, plan, report, Path(folder) / "client.pptx")
            presentation = Presentation(path)
            text = export_ppt.visible_text(presentation).replace("\n", "")
            self.assertIn("789.01", text)
            self.assertNotIn("123.45", text)
            self.assertNotIn("SECRET", text)
            for slide in presentation.slides:
                for shape in slide.shapes:
                    if shape.has_table:
                        for row in shape.table.rows:
                            self.assertNotEqual("".join(cell.text for cell in row.cells), "续。")
            changed = copy.deepcopy(plan)
            changed["placements"][0]["client_unit_price"] = "999.99"
            with self.assertRaisesRegex(ValueError, "预算不一致"):
                export_ppt.export("execution", analysis, changed, {}, Path(folder) / "stale.pptx")
            self.assertFalse((Path(folder) / "stale.pptx").exists())

    def test_long_content_keeps_editable_text_on_continuation_pages(self):
        analysis = {"schema_version": 1, "project": {"client_name": "演示客户"}, "counts": {}, "groups": []}
        analysis["project"].update(start_date="2027-01-01", end_date="2027-12-31")
        analysis["samples"] = [{"采集状态": "已完成", "采集时间": "2026-11-10T14:00:00+09:00"}]
        self.assertEqual(export_ppt.sampling_dates(analysis), "2026-11-10 至 2026-11-10")
        findings = [{"title": f"问题{i:02d}", "detail": f"问题{i:02d}的完整依据" + "可核验事实" * 25, "evidence_ref": [f"E{i:02d}"]} for i in range(13)]
        summary = "长段叙述需要完整保留" * 100
        with tempfile.TemporaryDirectory() as folder:
            path = export_ppt.export("diagnosis", analysis, {}, {"summary": summary, "findings": findings}, Path(folder) / "long.pptx")
            prs = Presentation(path)
            text = export_ppt.visible_text(prs).replace("\n", "")
            self.assertGreater(len(prs.slides), 10)
            summary_text = "".join(shape.text for slide in prs.slides
                                   if any(x.name == "geo_section_summary" for x in slide.shapes)
                                   for shape in slide.shapes if shape.name == "geo_content").replace("\n", "")
            self.assertIn(summary, summary_text)
            for i in range(13):
                self.assertIn(f"问题{i:02d}的完整依据", text)
                self.assertIn(f"E{i:02d}", text)
            self.assertTrue(any(shape.has_table for slide in prs.slides for shape in slide.shapes))
            self.assertFalse(any(shape.shape_type == 13 for slide in prs.slides for shape in slide.shapes))
            self.assertNotRegex(text, r"\{\{[^}]+\}\}|\$\{[^}]+\}")
            for slide in prs.slides:
                for shape in slide.shapes:
                    self.assertLessEqual(shape.top + shape.height, prs.slide_height + 12700)


if __name__ == "__main__":
    unittest.main()
