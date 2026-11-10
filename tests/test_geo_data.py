import copy
from datetime import datetime
import importlib.util
import tempfile
import unittest
from pathlib import Path

import openpyxl

SCRIPT = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts/geo_data.py"
spec = importlib.util.spec_from_file_location("geo_data", SCRIPT)
geo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geo)


class GeoDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "samples.xlsx"
        self.project = {"project_id": "test-only", "client_name": "测试项目", "brand_names": ["测试品牌"],
                        "currency": "CNY", "budget_limit": "500.00", "repeats": 1,
                        "questions": [{"question_id": "Q1", "type": "自然需求", "intent": "推荐", "theme": "主题", "text": "有哪些选择？"}],
                        "contexts": [{"platform": "测试平台", "mode": "标准", "online": "是", "round": 1}]}

    def prepare(self):
        geo.prepare(self.project, self.path)

    def edit_sample(self, changes, citation=None):
        wb = openpyxl.load_workbook(self.path)
        ws = wb["回答记录"]
        for key, value in changes.items():
            ws.cell(2, geo.SAMPLE_HEADERS.index(key) + 1, value)
        if citation:
            for i, value in enumerate(citation, 1):
                wb["引用明细"].cell(2, i, value)
        wb.save(self.path)
        wb.close()

    def completed(self, **extra):
        changes = {"采集状态": "已完成", "回答全文": "测试原始回答", "品牌提及": "是", "品牌推荐": "是", "引用展示": "未展示", "新对话": "是", "采集时间": "2026-11-10T12:00:00+09:00"}
        changes.update(extra)
        self.edit_sample(changes)

    def plan(self):
        return {"contents": [{"content_id": "C1", "title": "内容"}],
                "placements": [{"placement_id": "P1", "content_id": "C1", "media_name": "测试媒体", "source_file": "INTERNAL-SOURCE-SECRET.xlsx", "price_tier": "超级代理", "unit_price": "0.10", "client_unit_price": "2.10", "quantity": 3, "scheduled_date": "2026-11-10", "status": "已选"}],
                "fees": [{"fee_id": "F1", "amount": "0.20", "client_amount": "1.20", "status": "已选"}]}

    def test_blank_templates_have_no_fictitious_client(self):
        wb = openpyxl.load_workbook(geo.ROOT / "templates/AI回答采集表.xlsx", read_only=True, data_only=True)
        self.assertIsNone(wb["问题清单"]["A2"].value)
        self.assertIsNone(wb["回答记录"]["A2"].value)
        wb.close()

    def test_prepare_more_than_200_questions(self):
        self.project["questions"] = [dict(self.project["questions"][0], question_id=f"Q{i}") for i in range(205)]
        self.prepare()
        result = geo.analyze(self.path)
        self.assertEqual(result["counts"]["questions"], 205)
        self.assertEqual(result["counts"]["uncollected"], 205)
        self.assertIsNone(result["groups"][0]["mention_rate"])
        wb = openpyxl.load_workbook(self.path)
        self.assertTrue(any("B2:B206" == str(rule.sqref) for rule in wb["问题清单"].data_validations.dataValidation))
        wb.close()

    def test_pending_mention_is_not_negative(self):
        self.prepare()
        self.completed(品牌提及="待判", 品牌推荐="待判")
        group = geo.analyze(self.path)["groups"][0]
        self.assertEqual(group["mention_pending"], 1)
        self.assertEqual(group["mention_no"], 0)
        self.assertIsNone(group["mention_rate"])
        self.assertIsNone(group["recommendation_rate"])

    def test_no_sources_is_zero_observable_support_not_no_sources_claim(self):
        self.prepare()
        self.completed()
        group = geo.analyze(self.path)["groups"][0]
        self.assertEqual(group["unobserved_sources"], 1)
        self.assertEqual(group["citation_rate"], 0)

    def test_verified_supporting_citation_scores(self):
        self.prepare()
        self.completed(引用展示="已展示")
        self.edit_sample({}, ["CIT1", "Q1-C001-R01", "https://example.org/article", "来源", "站点", "已核验", "是", "支持品牌", None, None])
        group = geo.analyze(self.path)["groups"][0]
        self.assertEqual(group["citation_rate"], 1)
        self.edit_sample({}, ["CIT1", "Q1-C001-R01", "https://example.org/article", "来源", "站点", "待核验", "是", None, None, None])
        self.assertIsNone(geo.analyze(self.path)["groups"][0]["citation_rate"])

    def test_citation_orphan_bad_url_and_duplicate_ids(self):
        self.prepare()
        self.completed(引用展示="已展示")
        ref = ["CIT1", "UNKNOWN", "https://example.org", None, None, "已核验", "是", None, None, None]
        self.edit_sample({}, ref)
        with self.assertRaisesRegex(ValueError, "孤儿引用"):
            geo.analyze(self.path)
        ref[1], ref[2] = "Q1-C001-R01", "javascript:alert(1)"
        self.edit_sample({}, ref)
        with self.assertRaisesRegex(ValueError, "http"):
            geo.analyze(self.path)
        self.edit_sample({"sample_id": ""})
        with self.assertRaisesRegex(ValueError, "缺失或重复"):
            geo.analyze(self.path)

    def test_contexts_and_question_types_remain_separate(self):
        self.project["questions"].append(dict(self.project["questions"][0], question_id="Q2", type="品牌认知"))
        self.project["contexts"].append(dict(self.project["contexts"][0], mode="深度", round=2, online="否"))
        self.prepare()
        result = geo.analyze(self.path)
        self.assertEqual(len(result["groups"]), 4)
        self.assertEqual({g["round"] for g in result["groups"]}, {1, 2})

    def test_deleted_task_is_detected(self):
        self.prepare()
        wb = openpyxl.load_workbook(self.path)
        wb["回答记录"].delete_rows(2)
        wb.save(self.path)
        wb.close()
        with self.assertRaisesRegex(ValueError, "任务缺失"):
            geo.analyze(self.path)

    def test_recommendation_only_for_recommendation_intent(self):
        self.project["questions"][0]["intent"] = "认知"
        self.prepare()
        self.completed()
        self.assertIsNone(geo.analyze(self.path)["groups"][0]["recommendation_rate"])

    def test_offline_and_not_applicable_do_not_enter_citation_rate(self):
        self.project["contexts"][0]["online"] = "否"
        self.prepare()
        self.completed()
        self.assertIsNone(geo.analyze(self.path)["groups"][0]["citation_rate"])

    def test_candidates_do_not_enter_execution_budget(self):
        plan = self.plan()
        plan["placements"][0]["status"] = "候选"
        plan["fees"][0]["status"] = "候选"
        b = geo.calculate_budget(self.project, plan)
        self.assertEqual(b["candidate_placement_count"], 1)
        self.assertEqual(b["content_count"], 0)
        self.assertEqual(b["planned_content_count"], 1)
        self.assertIsNone(b["client"]["total"])

    def test_out_of_project_dates_are_rejected(self):
        self.project.update(start_date="2026-01-01", end_date="2026-10-31")
        with self.assertRaisesRegex(ValueError, "超出"):
            geo.calculate_budget(self.project, self.plan())

    def test_contradictory_brand_judgments_are_rejected(self):
        self.prepare()
        self.completed(品牌提及="否", 品牌推荐="是")
        with self.assertRaisesRegex(ValueError, "矛盾判读"):
            geo.analyze(self.path)

    def test_missing_sample_conditions_remain_evidence_but_not_metrics(self):
        self.prepare()
        self.completed(新对话="否", 采集时间="")
        result = geo.analyze(self.path)
        self.assertEqual(result["counts"]["completed"], 1)
        self.assertEqual(result["counts"]["invalid_conditions"], 1)
        self.assertEqual(result["counts"]["valid"], 0)
        self.assertIsNone(result["groups"][0]["mention_rate"])
        self.assertFalse(result["evidence"][0]["comparable"])
        self.assertEqual(result["evidence"][0]["answer"], "测试原始回答")

    def test_excel_text_is_never_silently_truncated(self):
        wb = openpyxl.Workbook()
        with self.assertRaisesRegex(ValueError, "禁止静默截断"):
            geo.put_rows(wb.active, [["全文" * 20000]])

    def test_actual_excel_dates_encode_as_iso_without_swallowing_unknown_types(self):
        self.prepare()
        self.completed(采集时间=datetime(2026, 11, 10, 12, 30))
        analysis = geo.analyze(self.path)
        output = Path(self.tmp.name) / "analysis.json"
        geo.write_json(analysis, output)
        self.assertEqual(geo.read_json(output)["samples"][0]["采集时间"], "2026-11-10T12:30:00")
        self.assertTrue(any("时区" in i["issue"] for i in analysis["issues"]))
        with self.assertRaises(TypeError):
            geo.json_default(object())

    def test_outputs_refuse_overwrite(self):
        self.prepare()
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(before, self.path.read_bytes())
        output = Path(self.tmp.name) / "existing.json"
        output.write_text("original", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            geo.write_json({"new": "data"}, output)
        self.assertEqual(output.read_text(encoding="utf-8"), "original")

    def test_decimal_budget_missing_price_and_quarters(self):
        plan = self.plan()
        budget = geo.calculate_budget(self.project, plan)
        self.assertEqual(budget["internal"]["total"], "0.50")
        self.assertEqual(budget["client"]["total"], "7.50")
        self.assertEqual(budget["internal"]["quarterly"]["2026Q4"]["total"], "0.30")
        self.assertEqual(budget["internal"]["quarterly"]["未排期"]["total"], "0.20")
        del plan["placements"][0]["unit_price"]
        budget = geo.calculate_budget(self.project, plan)
        self.assertIsNone(budget["internal"]["total"])
        self.assertEqual(budget["internal"]["missing_prices"], ["P1"])
        self.assertEqual(budget["internal"]["missing_count"], 1)
        self.assertEqual(budget["internal"]["known_subtotal"], "0.20")
        self.assertIsNone(budget["internal"]["exceeds_limit"])

    def test_budget_duplicate_orphan_negative_overbudget(self):
        plan = self.plan()
        plan["placements"].append(dict(plan["placements"][0]))
        with self.assertRaisesRegex(ValueError, "重复"):
            geo.calculate_budget(self.project, plan)
        plan = self.plan()
        plan["placements"][0]["content_id"] = "orphan"
        with self.assertRaisesRegex(ValueError, "不存在"):
            geo.calculate_budget(self.project, plan)
        plan = self.plan()
        plan["placements"][0]["unit_price"] = "-1"
        with self.assertRaises(ValueError):
            geo.calculate_budget(self.project, plan)
        plan["placements"][0]["unit_price"] = "999"
        self.assertTrue(geo.calculate_budget(self.project, plan)["internal"]["exceeds_limit"])

    def test_distinct_content_and_publication_counts(self):
        plan = self.plan()
        plan["placements"].append(dict(plan["placements"][0], placement_id="P2", quantity=2))
        b = geo.calculate_budget(self.project, plan)
        self.assertEqual((b["content_count"], b["placement_count"], b["publication_count"]), (1, 2, 5))

    def test_export_does_not_leak_cost_or_execute_text(self):
        self.prepare()
        self.completed()
        analysis = geo.analyze(self.path)
        plan = self.plan()
        plan["contents"][0]["title"] = "=HYPERLINK(\"https://example.org\")"
        result = geo.export_excel(self.project, analysis, plan, Path(self.tmp.name) / "exports")
        wb = openpyxl.load_workbook(result["client"], data_only=False)
        all_values = [c.value for ws in wb for row in ws for c in row if c.value is not None]
        self.assertNotIn("INTERNAL-SOURCE-SECRET.xlsx", all_values)
        self.assertNotIn("超级代理", all_values)
        self.assertNotIn("内部单价", all_values)
        self.assertEqual(wb["内容排期"]["B2"].data_type, "s")
        self.assertEqual(wb["内容排期"]["B2"].value, plan["contents"][0]["title"])
        self.assertFalse(wb["媒体投放"].data_validations.dataValidation)
        self.assertEqual(wb["媒体投放"]["G2"].value, 2.1)
        self.assertEqual(wb["媒体投放"]["H2"].value, '=IF(OR(A2="",G2="",F2=""),"",G2*F2)')
        self.assertEqual(wb["预算汇总"]["B10"].value, 7.5)
        self.assertTrue(geo.analyze(self.path)["evidence"][0]["answer"])
        wb.close()


if __name__ == "__main__":
    unittest.main()
