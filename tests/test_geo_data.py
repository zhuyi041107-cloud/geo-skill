import copy
from datetime import date, datetime
import importlib.util
import tempfile
import unittest
from pathlib import Path

import openpyxl
from openpyxl.drawing.image import Image
from PIL import Image as PILImage

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
        geo.prepare_internal(self.project, self.path)

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
        return {"contents": [{"content_id": "C1", "title": "内容", "question_ids": ["Q1"], "scheduled_date": "2026-11-10"}],
                "placements": [{"placement_id": "P1", "content_id": "C1", "media_id": "FAKE-MEDIA-001", "media_name": "测试媒体", "source_file": "INTERNAL-SOURCE-SECRET.xlsx", "price_tier": "超级代理", "unit_price": "0.10", "client_unit_price": "2.10", "quantity": 3, "scheduled_date": "2026-11-10", "status": "已选"}],
                "fees": [{"fee_id": "F1", "amount": "0.20", "client_amount": "1.20", "status": "已选"}]}

    def test_blank_templates_have_no_fictitious_client(self):
        wb = openpyxl.load_workbook(geo.ROOT / "templates/AI回答采集表.xlsx", read_only=True, data_only=True)
        self.assertEqual(wb.sheetnames, ["回答采集"])
        self.assertEqual([c.value for c in wb["回答采集"][1]], ["问题", "引用截图", "答案"])
        self.assertIsNone(wb["回答采集"]["A2"].value)
        wb.close()

    def test_prepare_one_context_is_only_three_columns(self):
        geo.prepare(self.project, self.path)
        wb = openpyxl.load_workbook(self.path)
        self.assertEqual(wb.sheetnames, ["回答采集"])
        self.assertEqual(wb.active.max_column, 3)
        self.assertEqual(wb.active["A2"].value, self.project["questions"][0]["text"])
        self.assertIsNone(wb.active["B2"].value)
        self.assertIsNone(wb.active["C2"].value)
        wb.close()

    def test_prepare_multiple_contexts_and_merge_imports(self):
        self.project["contexts"].append(dict(self.project["contexts"][0], platform="第二平台"))
        result = geo.prepare(self.project, out_dir=Path(self.tmp.name) / "collections")
        self.assertEqual(len(result["outputs"]), 2)
        for i, source in enumerate(result["outputs"]):
            wb = openpyxl.load_workbook(source)
            wb.active["C2"] = f"平台{i+1}原始答案"
            wb.save(source)
            wb.close()
        first = Path(self.tmp.name) / "internal-one.xlsx"
        combined = Path(self.tmp.name) / "internal-all.xlsx"
        geo.normalize_collection(result["outputs"][0], self.project, "1", first)
        geo.normalize_collection(result["outputs"][1], self.project, "第二平台", combined, base=first)
        analysis = geo.analyze(combined)
        self.assertEqual(analysis["counts"]["completed"], 2)
        self.assertEqual(analysis["counts"]["valid"], 2)
        self.assertEqual(analysis["counts"]["condition_unknown"], 0)
        self.assertEqual({s["回答全文"] for s in analysis["samples"]}, {"平台1原始答案", "平台2原始答案"})
        self.assertTrue(all(s["采集时间"] == date.today().isoformat() and s["新对话"] is None for s in analysis["samples"]))

    def test_import_preserves_embedded_and_relative_screenshots(self):
        geo.prepare(self.project, self.path)
        image_path = Path(self.tmp.name) / "evidence.png"
        PILImage.new("RGB", (30, 20), "white").save(image_path)
        wb = openpyxl.load_workbook(self.path)
        wb.active["B2"] = image_path.name
        wb.active["C2"] = "无完整来源URL的原始答案"
        wb.active.add_image(Image(str(image_path)), "B2")
        wb.save(self.path)
        wb.close()
        original = self.path.read_bytes()
        target = Path(self.tmp.name) / "internal.xlsx"
        result = geo.normalize_collection(self.path, self.project, "1", target)
        self.assertEqual(result["screenshots"], 2)
        self.assertEqual(self.path.read_bytes(), original)
        analysis = geo.analyze(target)
        self.assertEqual(analysis["counts"]["citations"], 2)
        self.assertIsNone(analysis["groups"][0]["citation_rate"])
        for citation in analysis["citations"]:
            self.assertIsNone(citation["URL"])
            self.assertIsNone(citation["网站或媒体"])
            self.assertEqual(citation["核验状态"], "待核验")
            self.assertEqual(Path(citation["证据路径"]).read_bytes(), image_path.read_bytes())

    def test_import_does_not_read_outside_collection_directory(self):
        source_dir = Path(self.tmp.name) / "source"
        source_dir.mkdir()
        source = source_dir / "input.xlsx"
        geo.prepare(self.project, source)
        external = Path(self.tmp.name) / "outside.png"
        PILImage.new("RGB", (2, 2), "red").save(external)
        wb = openpyxl.load_workbook(source)
        wb.active["B2"], wb.active["C2"] = "../outside.png", "保留答案"
        wb.save(source)
        wb.close()
        output = Path(self.tmp.name) / "internal.xlsx"
        result = geo.normalize_collection(source, self.project, "1", output)
        self.assertEqual(result["screenshots"], 0)
        self.assertIn("超出", result["warnings"][0])
        self.assertEqual(geo.analyze(output)["samples"][0]["回答全文"], "保留答案")

    def test_unrecorded_sampling_conditions_allow_descriptive_analysis(self):
        self.prepare()
        self.completed(新对话="", 采集时间="")
        result = geo.analyze(self.path)
        self.assertEqual(result["counts"]["valid"], 1)
        self.assertEqual(result["counts"]["condition_unknown"], 0)
        self.assertEqual(result["counts"]["invalid_conditions"], 0)
        self.assertEqual(result["groups"][0]["mention_rate"], 1)
        self.assertTrue(result["evidence"][0]["comparable"])

    def test_explicit_collection_failure_and_no_sources_markers(self):
        geo.prepare(self.project, self.path)
        wb = openpyxl.load_workbook(self.path)
        wb.active["B2"], wb.active["C2"] = "未展示", "失败：平台连接失败"
        wb.save(self.path)
        wb.close()
        target = Path(self.tmp.name) / "internal.xlsx"
        result = geo.normalize_collection(self.path, self.project, "1", target)
        analysis = geo.analyze(target)
        self.assertEqual(analysis["counts"]["failed"], 1)
        self.assertEqual(analysis["counts"]["completed"], 0)
        self.assertEqual(analysis["counts"]["citations"], 0)
        self.assertEqual(result["warnings"], [])

    def test_prepare_more_than_200_questions(self):
        self.project["questions"] = [dict(self.project["questions"][0], question_id=f"Q{i}") for i in range(205)]
        self.prepare()
        result = geo.analyze(self.path)
        self.assertEqual(len(result["samples"]), 205)
        self.assertEqual(result["counts"]["questions"], 0)
        self.assertEqual(result["counts"]["uncollected"], 0)
        self.assertEqual(result["groups"], [])
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
        wb = openpyxl.load_workbook(self.path)
        for r in (2, 3):
            for h, v in {"采集状态": "已完成", "回答全文": "原始回答"}.items():
                wb["回答记录"].cell(r, geo.SAMPLE_HEADERS.index(h) + 1, v)
        wb.save(self.path)
        wb.close()
        result = geo.analyze(self.path)
        self.assertEqual(len(result["groups"]), 4)
        self.assertEqual({g["round"] for g in result["groups"]}, {1, 2})

    def test_deleted_task_is_detected(self):
        self.project["questions"].append(dict(self.project["questions"][0], question_id="Q2", text="第二题"))
        self.prepare()
        self.completed()
        wb = openpyxl.load_workbook(self.path)
        wb["回答记录"].delete_rows(3)
        wb.save(self.path)
        wb.close()
        with self.assertRaisesRegex(ValueError, "任务缺失"):
            geo.analyze(self.path)

    def test_one_returned_platform_reports_immediately_and_accepts_offset_image(self):
        self.project["contexts"][0].update(mode="未知", online="未知")
        self.project["contexts"] += [dict(self.project["contexts"][0], platform=p) for p in ["未回传二", "未回传三"]]
        collection = Path(self.tmp.name) / "returned.xlsx"
        wb = openpyxl.load_workbook(geo.ROOT / "templates/AI回答采集表.xlsx")
        wb.active["A2"], wb.active["C2"] = self.project["questions"][0]["text"], "实际回传回答"
        picture = Path(self.tmp.name) / "source.png"
        PILImage.new("RGB", (20, 10), "white").save(picture)
        wb.active.add_image(Image(str(picture)), "A2")
        wb.save(collection)
        wb.close()
        before = collection.read_bytes()
        output = Path(self.tmp.name) / "internal.xlsx"
        geo.normalize_collection(collection, self.project, "1", output)
        result = geo.analyze(output)
        self.assertEqual(collection.read_bytes(), before)
        self.assertEqual(len(result["samples"]), 3)
        self.assertEqual((result["counts"]["planned"], result["counts"]["valid"]), (1, 1))
        self.assertEqual(result["sampled_contexts"], [{"platform": "测试平台", "mode": "网页端", "online": "是", "round": 1}])
        self.assertEqual(result["report_scope"]["round_date"], date.today().isoformat())
        self.assertEqual(result["report_scope"]["platforms"], ["测试平台"])
        self.assertIsNone(result["groups"][0]["citation_rate"])
        self.assertEqual(result["counts"]["pending_source_verification"], 1)
        self.assertFalse(any("采样条件未记录" in i["issue"] or "新对话" in i["issue"] for i in result["issues"]))

    def test_unlocated_screenshot_is_saved_without_blocking_or_false_binding(self):
        geo.prepare(self.project, self.path)
        picture = Path(self.tmp.name) / "unlocated.png"
        PILImage.new("RGB", (10, 10), "white").save(picture)
        wb = openpyxl.load_workbook(self.path)
        wb.active["C2"] = "已有答案继续分析"
        wb.active.add_image(Image(str(picture)), "C1")
        wb.save(self.path)
        wb.close()
        output = Path(self.tmp.name) / "internal.xlsx"
        imported = geo.normalize_collection(self.path, self.project, "1", output)
        analysis = geo.analyze(output)
        self.assertEqual(analysis["counts"]["valid"], 1)
        self.assertEqual(analysis["counts"]["citations"], 0)
        self.assertIsNone(analysis["samples"][0]["回答证据路径"])
        self.assertEqual(len(imported["unlocated_screenshots"]), 1)
        self.assertTrue(Path(imported["unlocated_screenshots"][0]["path"]).is_file())

    def test_direct_old_workbook_gets_same_convention_without_editing_history(self):
        self.project["contexts"][0].update(mode="未知", online="未知")
        self.prepare()
        self.completed(采集时间="", 新对话="")
        before = self.path.read_bytes()
        result = geo.analyze(self.path)
        self.assertEqual(result["sampled_contexts"][0]["mode"], "网页端")
        self.assertEqual(result["sampled_contexts"][0]["online"], "是")
        self.assertEqual(result["report_scope"]["round_date"], date.today().isoformat())
        self.assertEqual(before, self.path.read_bytes())

    def test_explicit_historical_metadata_is_kept(self):
        self.project["contexts"][0].update(mode="历史模式", online="否")
        self.prepare()
        self.completed(采集时间="2024-03-02T10:00:00+09:00", 新对话="")
        result = geo.analyze(self.path)
        self.assertEqual(result["report_scope"]["round_date"], "2024-03-02")
        self.assertEqual(result["sampled_contexts"][0]["mode"], "历史模式")
        self.assertEqual(result["sampled_contexts"][0]["online"], "否")

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

    def test_default_twenty_thousand_budget_rejects_token_proposals(self):
        project = dict(self.project, budget_limit=None)
        plan = self.plan()
        plan["fees"] = []
        plan["placements"][0].update(client_unit_price="2015.00", quantity=1)
        budget = geo.calculate_budget(project, plan)
        self.assertEqual((budget["target"], budget["limit"]), ("20000.00", "20000.00"))
        with self.assertRaisesRegex(ValueError, "未达到"):
            geo.validate_delivery_budget(budget)
        plan["placements"][0]["client_unit_price"] = "19800.00"
        geo.validate_delivery_budget(geo.calculate_budget(project, plan))
        plan["placements"][0]["client_unit_price"] = "20100.00"
        with self.assertRaisesRegex(ValueError, "超出"):
            geo.validate_delivery_budget(geo.calculate_budget(project, plan))
        # An explicit smaller budget is a client override, not the skill default.
        project.update(budget_limit="2200.00", budget_target="2200.00")
        plan["placements"][0]["client_unit_price"] = "2015.00"
        geo.validate_delivery_budget(geo.calculate_budget(project, plan))

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
        self.assertEqual(wb.sheetnames, ["现状分析", "关键词与内容排期", "媒体投放", "费用汇总"])
        self.assertEqual(wb["关键词与内容排期"]["B5"].data_type, "s")
        self.assertEqual(wb["关键词与内容排期"]["B5"].value, plan["contents"][0]["title"])
        self.assertFalse(wb["媒体投放"].data_validations.dataValidation)
        self.assertEqual(wb["媒体投放"]["E5"].value, 2.1)
        self.assertEqual(wb["媒体投放"]["G5"].value, '=IF(OR(B5="",E5="",F5=""),"",E5*F5)')
        self.assertNotIn("FAKE-MEDIA-001", all_values)
        self.assertEqual(wb["媒体投放"].max_row, 5)
        self.assertTrue(geo.analyze(self.path)["evidence"][0]["answer"])
        wb.close()

    def test_old_client_sheet_uses_labels_instead_of_row_numbers(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "客户素材清单"
        ws.append(["素材分组", "所需素材项", "填写要求", "示例", "必填", "客户填写"])
        ws.append(["A. 企业身份", "公司全称", "", "", "选填", "虚构公司"])
        ws.append([None, "统一社会信用代码", "", "", "选填", None])
        ws.append([None, "品牌名称 / 英文名", "", "", "选填", "虚构品牌"])
        ws.append([None, "成立时间", "", "", "选填", date(2020, 1, 1)])
        source = Path(self.tmp.name) / "old-client.xlsx"
        wb.save(source)
        wb.close()
        result = geo.inspect_client(source)
        self.assertEqual([(f["field"], f["row"]) for f in result["fields"]], [("公司全称", 2), ("统一社会信用代码", 3), ("品牌名称 / 英文名", 4), ("成立时间", 5)])
        self.assertEqual(result["filled"], 3)

    def test_business_text_keeps_quarters_and_public_links(self):
        self.assertEqual(geo.business_text("2026Q4"), "2026Q4")
        self.assertEqual(geo.business_text("Q001需求，2027Q1"), "需求，2027Q1")
        self.assertEqual(geo.business_text('=HYPERLINK("https://example.org")'), '=HYPERLINK("https://example.org")')

    def test_business_excel_accepts_nested_report_sections(self):
        self.prepare(); self.completed()
        report = {"diagnosis": {"summary": "虚构品牌现状正文", "brand_status": [{"title": "业务认知", "detail": "这是虚构的品牌分析"}], "key_findings": [{"title": "核心发现", "detail": "这是虚构的需求缺口"}]}, "execution": {"keywords": [{"title": "虚构选型词", "detail": "根据客户决策安排内容"}]}}
        result = geo.export_excel(self.project, geo.analyze(self.path), self.plan(), Path(self.tmp.name)/"nested", report)
        wb = openpyxl.load_workbook(result["client"])
        values = [c.value for s in wb for row in s for c in row if c.value is not None]
        for expected in ["虚构品牌现状正文", "这是虚构的品牌分析", "这是虚构的需求缺口", "虚构选型词", "根据客户决策安排内容"]:
            self.assertIn(expected, values)
        wb.close()

    def test_business_report_strings_are_not_split_into_characters(self):
        report = {"diagnosis": {"key_findings": "完整核心发现", "priorities": "完整优先行动"}, "execution": {"keywords": "完整关键词"}}
        wb = geo.customer_workbook(self.project, {"groups": []}, self.plan(), report)
        values = [c.value for s in wb for row in s for c in row if c.value is not None]
        for item in ["完整核心发现", "完整优先行动", "完整关键词"]:
            self.assertEqual(values.count(item), 1)
        self.assertNotIn("优先行动2", values)
        wb.close()

    def test_business_excel_preserves_structured_diagnostic_matrix(self):
        report = {"diagnosis": {"sections": [{"key": "scenario_competition", "title": "客户场景", "paragraphs": [{"title": "本轮情况", "detail": "虚构需求对照"}], "tables": [{"columns": ["客户关注场景", "本品牌", "指定竞品"], "rows": [["本地选型", "本轮未出现", "演示竞品"]]}]}]}}
        plan = self.plan()
        plan["contents"][0]["keywords"] = ["本地虚构服务"]
        wb = geo.customer_workbook(self.project, {"groups": []}, plan, report)
        values = [c.value for s in wb for row in s for c in row if c.value is not None]
        self.assertIn("客户场景：本地选型", values)
        self.assertIn("本品牌：本轮未出现；指定竞品：演示竞品", values)
        self.assertIn("本地虚构服务", values)
        wb.close()

    def test_business_excel_uses_supplied_report_and_separates_unpriced_services(self):
        self.prepare()
        self.completed()
        analysis = geo.analyze(self.path)
        plan = self.plan()
        plan["placements"][0].update(price_tier="市场价格", unit_price=None, price_basis="市场参考价（非确认报价）", quotation_date="2026-11-10")
        plan["fees"][0].update(category="撰稿服务", client_amount=None)
        report = {"summary": "虚构业务结论", "findings": [{"title": "品牌场景覆盖", "detail": "Q001 需求选择尚未覆盖"}], "priorities": ["完善公开业务介绍"], "keywords": [{"title": "虚构业务关键词", "evidence_ref": ["Q1"]}]}
        result = geo.export_excel(self.project, analysis, plan, Path(self.tmp.name) / "business", report)
        wb = openpyxl.load_workbook(result["client"], data_only=False)
        values = [str(c.value) for ws in wb for row in ws for c in row if c.value is not None]
        self.assertIn("虚构业务结论", values)
        self.assertIn("虚构业务关键词", values)
        self.assertIn("单独核价", values)
        self.assertFalse(any("Q001" in v or "source_row" in v or "本地路径" in v for v in values))
        self.assertEqual(wb["媒体投放"]["F5"].value, 3)
        self.assertIn("市场参考价", wb["媒体投放"]["I5"].value)
        wb.close()

    def test_customer_execution_does_not_export_placeholder_or_unpriced_media(self):
        analysis = {"project": self.project, "groups": []}
        plan = self.plan()
        plan["placements"][0]["media_id"] = "TBD-M1"
        with self.assertRaisesRegex(ValueError, "占位"):
            geo.export_excel(self.project, analysis, plan, Path(self.tmp.name) / "bad")


if __name__ == "__main__":
    unittest.main()
