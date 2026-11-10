import copy
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from docx import Document
from docx.oxml.ns import qn
from openpyxl import load_workbook

SCRIPT_DIR = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import export_media_word as media_word
from geo_data import calculate_budget


class ExportMediaWordTests(unittest.TestCase):
    def fixture(self):
        project = {"client_name": "虚构客户", "brand_names": ["知桥演示（虚构）"], "currency": "CNY", "budget_target": "1440.00"}
        plan = {"contents": [{"content_id": "C001", "title": "实施服务边界（虚构）", "status": "已选"}], "fees": [], "placements": [], "media_recommendations": []}
        for i, sheet in enumerate(["网络媒体报价", "网络媒体报价", "自媒体报价"], 1):
            plan["placements"].append({"placement_id": f"P{i:03}", "content_id": "C001", "media_id": f"DEMO-{i}", "media_name": f"虚构媒体{i}", "source_sheet": sheet,
                "media_group": "行业服务", "category": "企业服务", "region": "浙江", "market_price": "80.00", "client_unit_price": "480.00", "unit_price": "17.00", "quantity": 1,
                "scheduled_date": "2026-11-20", "status": "已选", "contact_policy": "不带", "entry_type": "自媒体号" if i == 3 else "频道刊发"})
            recommendation = copy.deepcopy(plan["placements"][-1])
            recommendation["status"] = "推荐"
            for field in ("content_id", "placement_id", "client_unit_price", "unit_price", "quantity", "scheduled_date"):
                recommendation.pop(field)
            plan["media_recommendations"].append(recommendation)
        return {"project": project, "budget": calculate_budget(project, plan)}, plan

    def document(self, analysis, plan):
        return Document(BytesIO(media_word.build_docx(analysis, plan)))

    def test_original_column_order_template_geometry_and_no_case_rows(self):
        a, p = self.fixture()
        doc = self.document(a, p)
        network = ["序号", "媒体类别", "媒体分类", "媒体名称", "文章案例", "市场价格", "超级代理", "核心代理", "高级代理", "普通代理", "普通会员", "联系方式", "新闻源", "地区", "备注", "简介"]
        own = network[:12] + ["地区", "粉丝量", "认证", "备注", "认证主体"]
        self.assertEqual(len(doc.tables), 2)
        self.assertEqual([c.text for c in doc.tables[0].rows[2].cells], network)
        self.assertEqual([c.text for c in doc.tables[1].rows[2].cells], own)
        self.assertAlmostEqual(doc.sections[0].page_width.mm, 420, places=1)
        self.assertAlmostEqual(doc.sections[0].page_height.mm, 297, places=1)
        for table in doc.tables:
            self.assertIn("按需选择，按实际发布媒体计算总费用", table.cell(1, 0).text)
            self.assertEqual(table.cell(2, 0)._tc.tcPr.find(qn("w:shd")).get(qn("w:fill")), "C4BD97")
            self.assertEqual(table.cell(1, 0)._tc.tcPr.find(qn("w:shd")).get(qn("w:fill")), "FFC000")
            self.assertEqual(table.cell(3, 8)._tc.tcPr.find(qn("w:shd")).get(qn("w:fill")), "FDE9D9")
        blank = Document(media_word.TEMPLATE)
        self.assertEqual([len(t.rows) for t in blank.tables], [4, 4])
        self.assertTrue(all(not c.text for t in blank.tables for c in t.rows[3].cells))
        self.assertTrue(all(len(t.cell(1, 4).paragraphs) == 1 for t in blank.tables))
        self.assertFalse(blank.styles["Title"]._element.xpath("./w:pPr/w:pBdr"))
        self.assertNotIn("维晏", "".join(c.text for t in blank.tables for r in t.rows for c in r.cells))

    def test_no_cost_inference_market_price_and_group_merge(self):
        a, p = self.fixture()
        doc = self.document(a, p)
        network = doc.tables[0]
        self.assertEqual(network.cell(3, 5).text, "80.00")
        self.assertTrue(all(not network.cell(3, col).text for col in range(6, 11)))
        self.assertIs(network.cell(3, 1)._tc, network.cell(4, 1)._tc)
        self.assertEqual(network.cell(3, 1).text, "行业服务")
        self.assertEqual(network.cell(3, 11).text, "不带")
        self.assertEqual(network.cell(3, 14).text, "刊发形态：频道刊发")
        self.assertTrue(all(not network.cell(3, col).text for col in [4, 12, 15]))
        self.assertTrue(all(not doc.tables[1].cell(3, col).text for col in [13, 14, 16]))
        changed = copy.deepcopy(p)
        changed["media_recommendations"][0].pop("market_price")
        a["budget"] = calculate_budget(a["project"], changed)
        self.assertEqual(self.document(a, changed).tables[0].cell(3, 5).text, "")
        changed["media_recommendations"][0]["tier_prices"] = {"超级代理": "63.00"}
        with self.assertRaisesRegex(ValueError, "tier_price_source"):
            self.document(a, changed)
        changed["media_recommendations"][0]["tier_price_source"] = "虚构外部报价，第2行超级代理档"
        self.assertEqual(self.document(a, changed).tables[0].cell(3, 6).text, "63.00")
        self.assertEqual(self.document(a, changed).tables[0].cell(3, 7).text, "")

    def test_catalog_join_uses_id_and_sheet_not_media_label(self):
        a, p = self.fixture()
        p["media_recommendations"][0]["media_id"] = "SAME"
        p["media_recommendations"][2]["media_id"] = "SAME"
        for item in p["media_recommendations"]:
            item.pop("category"); item.pop("region"); item.pop("entry_type")
        catalog = {
            ("网络媒体报价", "SAME"): {"media_name": "虚构媒体1", "category": "网络分类", "region": "杭州", "editorial_note": "修改须确认", "entry_type": "新闻频道", "market_price": "80.00"},
            ("自媒体报价", "SAME"): {"media_name": "虚构媒体3", "category": "账号分类", "region": "宁波", "entry_type": "账号刊发", "market_price": "80.00"},
        }
        rows = media_word.selected_rows(p, catalog)
        self.assertEqual(rows["网络媒体报价"][0]["媒体分类"], "网络分类")
        self.assertEqual(rows["自媒体报价"][0]["地区"], "宁波")
        self.assertEqual(rows["网络媒体报价"][0]["备注"], "修改须确认；刊发形态：新闻频道")
        p["media_recommendations"][0]["market_price"] = "999.00"
        with self.assertRaisesRegex(ValueError, "市场价格与目录不一致"):
            media_word.selected_rows(p, catalog)

    def test_catalog_fills_original_tiers_without_plan_prices_and_keeps_unknown_blank(self):
        a, p = self.fixture()
        item = p["media_recommendations"][0]
        catalog = {("网络媒体报价", item["media_id"]): {"media_name": item["media_name"], "market_price": "80.00",
            "super_agent_price": "0.00", "core_agent_price": "51.20", "senior_agent_price": "63.00", "regular_agent_price": "", "member_price": "75.00"}}
        rows = media_word.selected_rows(p, catalog)
        row = rows["网络媒体报价"][0]
        self.assertEqual([row[tier] for tier in media_word.TIERS], ["0.00", "51.20", "63.00", "", "75.00"])
        self.assertNotIn("tier_prices", item)
        item.update(tier_prices={"核心代理": "54.00", "高级代理": None}, tier_price_source="虚构更新报价，第2行核心代理档")
        updated = media_word.selected_rows(p, catalog)["网络媒体报价"][0]
        self.assertEqual([updated[tier] for tier in media_word.TIERS], ["0.00", "54.00", "63.00", "", "75.00"])
        item["tier_prices"]["市场价格"] = "81.00"
        with self.assertRaisesRegex(ValueError, "市场价格.*不一致"):
            media_word.selected_rows(p, catalog)

    def test_real_catalog_auto_fills_all_six_word_price_columns(self):
        catalog = media_word.catalog_records(media_word.CATALOG)
        plan = {"media_recommendations": []}
        expected = []
        for index, sheet in enumerate(media_word.HEADERS, 1):
            (source_sheet, mid), source = next((key, row) for key, row in catalog.items() if key[0] == sheet and all(row.get(field) not in (None, "") for field in media_word.TIER_FIELDS.values()))
            plan["media_recommendations"].append({"media_id": mid, "media_name": source["media_name"], "source_sheet": source_sheet, "status": "推荐"})
            expected.append([source[field] for field in media_word.TIER_FIELDS.values()])
        project = {"client_name": "六档测试虚构客户", "brand_names": ["六档测试（虚构）"], "budget_limit": "1000000.00"}
        document = self.document({"project": project}, plan)
        for table, prices in zip(document.tables, expected):
            self.assertEqual([table.cell(3, col).text for col in range(5, 11)], prices)

    def test_explicit_external_row_does_not_fill_unknown_tiers_from_old_catalog(self):
        a, p = self.fixture()
        item = p["media_recommendations"][0]
        catalog = {("网络媒体报价", item["media_id"]): {"media_name": item["media_name"], "market_price": "80.00", "source_file": "虚构旧报价.xlsx",
            "super_agent_price": "50.00", "core_agent_price": "60.00", "senior_agent_price": "65.00", "regular_agent_price": "70.00", "member_price": "75.00"}}
        item.update(source_file="虚构更新报价.xlsx", quotation_date="2026-11-11", market_price="96.00",
                    tier_prices={"市场价格": "96.00", "超级代理": "61.00", "高级代理": None}, tier_price_source="虚构更新报价.xlsx，网络媒体报价第2行")
        updated = media_word.selected_rows(p, catalog)["网络媒体报价"][0]
        self.assertEqual(updated["市场价格"], "96.00")
        self.assertEqual([updated[tier] for tier in media_word.TIERS], ["61.00", "", "", "", ""])

    def test_missing_pool_refuses_placement_fallback_and_preserves_existing_file(self):
        a, p = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "推荐媒体.docx"
            changed = copy.deepcopy(p)
            changed.pop("media_recommendations")
            with self.assertRaisesRegex(ValueError, "media_recommendations.*广泛推荐"):
                media_word.export_docx(a, changed, output)
            self.assertFalse(output.exists())
            output.write_bytes(b"existing-user-file")
            with self.assertRaises(FileExistsError):
                media_word.export_docx(a, p, output)
            self.assertEqual(output.read_bytes(), b"existing-user-file")

    def test_complete_pool_ignores_missing_stale_or_underfunded_budget(self):
        a, p = self.fixture()
        p["media_recommendations"] = [{"media_id": f"BROAD-{i}", "media_name": f"虚构广泛推荐{i}", "source_sheet": "网络媒体报价" if i % 2 == 0 else "自媒体报价",
            "media_type": "有意与来源表不同的标签", "market_price": "10000.00", "status": ["推荐", "候选", "需核实"][i % 3], "editorial_note": "需确认具体题材与排期"} for i in range(18)]
        for budget in (None, {"client": {"total": "100.00"}}, {"client": {"total": "99999999.00"}}):
            with self.subTest(budget=budget):
                changed_analysis = {"project": {**a["project"], "budget_target": "20000.00", "budget_limit": "20000.00"}}
                if budget is not None:
                    changed_analysis["budget"] = budget
                document = self.document(changed_analysis, p)
                self.assertEqual([len(t.rows) - 3 for t in document.tables], [9, 9])
                self.assertTrue(all(t.cell(3, 5).text == "10000.00" for t in document.tables))
                names = [r.cells[3].text for t in document.tables for r in t.rows[3:]]
                self.assertNotIn("虚构媒体1", names)
                workbook = load_workbook(BytesIO(media_word.build_xlsx(changed_analysis, p)))
                self.assertEqual(workbook.sheetnames, ["sheet1", "sheet2"])
                self.assertEqual([sheet.max_row - 3 for sheet in workbook], [9, 9])
                self.assertTrue(all(sheet["F4"].value == 10000 for sheet in workbook))
                workbook.close()
        self.assertEqual(len(p["placements"]), 3)

    def test_exclusions_dedup_and_unverified_conditions_are_kept_separate(self):
        a, p = self.fixture()
        first = p["media_recommendations"][0]
        p["media_recommendations"].append(copy.deepcopy(first))
        for index, status in enumerate(("取消", "排除"), 4):
            p["media_recommendations"].append({**first, "media_id": f"DEMO-{index}", "media_name": f"应排除媒体{index}", "status": status})
        p["media_recommendations"].append({**first, "media_id": "NO-GEO", "media_name": "拒发GEO媒体", "editorial_note": "普通说明"})
        p["media_recommendations"].append({**first, "media_id": "NEW-PRICE-NO-GEO", "media_name": "新报价拒发媒体", "source_file": "虚构更新价格.xlsx", "quotation_date": "2026-11-11", "market_price": "96.00"})
        p["media_recommendations"][1].update(status="需核实", editorial_note="客户补充条件")
        catalog = {("网络媒体报价", "NO-GEO"): {"media_name": "拒发GEO媒体", "market_price": "80.00", "editorial_note": "明确不发GEO"},
                   ("网络媒体报价", "NEW-PRICE-NO-GEO"): {"media_name": "新报价拒发媒体", "market_price": "80.00", "source_file": "虚构旧价格.xlsx", "editorial_note": "不发GEO"},
                   ("网络媒体报价", "DEMO-2"): {"media_name": "虚构媒体2", "market_price": "80.00", "editorial_note": "GEO需提供真实案例"}}
        rows = media_word.selected_rows(p, catalog)
        self.assertEqual([len(value) for value in rows.values()], [2, 1])
        note = rows["网络媒体报价"][1]["备注"]
        self.assertIn("GEO需提供真实案例", note)
        self.assertIn("客户补充条件", note)
        self.assertIn("尚未确认可发", note)
        p["media_recommendations"].append({**first, "market_price": "90.00"})
        with self.assertRaisesRegex(ValueError, "不同属性或报价"):
            media_word.selected_rows(p, catalog)

    def test_empty_second_category_keeps_original_header_and_blank_row(self):
        a, p = self.fixture()
        p["media_recommendations"] = p["media_recommendations"][:2]
        document = self.document({"project": a["project"]}, p)
        self.assertEqual(len(document.tables[1].rows), 4)
        self.assertEqual([c.text for c in document.tables[1].rows[2].cells], list(media_word.HEADERS["自媒体报价"]))
        self.assertTrue(all(not c.text for c in document.tables[1].rows[3].cells))

    def test_contact_column_refuses_personal_phone_and_missing_sheet(self):
        a, p = self.fixture()
        p["media_recommendations"][0]["contact_policy"] = "张先生 13800000000"
        with self.assertRaisesRegex(ValueError, "不能填写联系人或电话"):
            self.document(a, p)
        p["media_recommendations"][0]["contact_policy"] = "不带"
        p["media_recommendations"][0]["source_sheet"] = ""
        with self.assertRaisesRegex(ValueError, "source_sheet"):
            self.document(a, p)

    def test_dated_external_quote_replaces_old_catalog_row(self):
        a, p = self.fixture()
        item = p["media_recommendations"][0]
        catalog = {("网络媒体报价", item["media_id"]): {"media_name": "旧版虚构媒体1", "market_price": "80.00", "source_file": "虚构旧报价.xlsx", "category": "旧分类", "region": "旧地区", "editorial_note": "旧备注"}}
        item.update(source_file="虚构更新报价.xlsx", quotation_date="2026-11-11", market_price="96.00", category="更新分类", region="更新地区")
        updated = media_word.selected_rows(p, catalog)["网络媒体报价"][0]
        self.assertEqual(updated["媒体名称"], "虚构媒体1")
        self.assertEqual(updated["市场价格"], "96.00")
        self.assertEqual(updated["媒体分类"], "更新分类")
        self.assertEqual(updated["地区"], "更新地区")
        self.assertNotIn("旧备注", updated["备注"])
        self.assertTrue(all(not updated[tier] for tier in media_word.TIERS))
        for field, value in [("source_file", "虚构旧报价.xlsx"), ("source_file", "未知"), ("quotation_date", ""), ("market_price", None)]:
            changed = copy.deepcopy(p)
            changed["media_recommendations"][0][field] = value
            with self.assertRaisesRegex(ValueError, "名称与目录"):
                media_word.selected_rows(changed, catalog)

    def test_xlsx_template_keeps_original_two_tables_and_source_format(self):
        template = load_workbook(media_word.XLSX_TEMPLATE)
        self.assertEqual(template.sheetnames, ["sheet1", "sheet2"])
        for sheet, headers in zip(template, media_word.HEADERS.values()):
            self.assertEqual(sheet.max_column, len(headers))
            self.assertEqual(tuple(cell.value for cell in sheet[3]), headers)
            self.assertEqual(sheet.max_row, 4)
            self.assertTrue(all(cell.value is None for cell in sheet[4]))
            self.assertFalse(any("维晏" in str(cell.value or "") for row in sheet for cell in row))
        source_path = Path(__file__).resolve().parents[2] / "维晏艺术中心开业前媒体投放计划表2026_10_16.xlsx"
        if source_path.exists():
            source = load_workbook(source_path)
            for original, blank in zip(source, template):
                self.assertEqual({k: (v.min, v.max, v.width) for k, v in original.column_dimensions.items()}, {k: (v.min, v.max, v.width) for k, v in blank.column_dimensions.items()})
                self.assertEqual(sorted(str(r) for r in original.merged_cells.ranges if r.max_row < 4), sorted(str(r) for r in blank.merged_cells.ranges))
                for row in range(1, 5):
                    for column in range(1, original.max_column + 1):
                        self.assertEqual(original.cell(row, column)._style, blank.cell(row, column)._style)
            source.close()
        template.close()

    def test_xlsx_six_numeric_prices_blank_unknown_and_literal_text(self):
        a, p = self.fixture()
        item = p["media_recommendations"][0]
        item.update(media_name="=1+1", editorial_note="长备注" * 60,
                    tier_prices={"超级代理": "0.00", "核心代理": "51.20", "高级代理": "63.00", "普通会员": "75.00"}, tier_price_source="虚构报价，五档原值")
        workbook = load_workbook(BytesIO(media_word.build_xlsx({"project": a["project"]}, p)))
        sheet = workbook["sheet1"]
        self.assertEqual([sheet.cell(4, c).value for c in range(6, 12)], [80, 0, 51.2, 63, None, 75])
        self.assertTrue(all(sheet.cell(4, c).data_type == "n" for c in [6, 7, 8, 9, 11]))
        self.assertEqual(sheet["D4"].value, "=1+1")
        self.assertEqual(sheet["D4"].data_type, "s")
        self.assertTrue(sheet["O4"].alignment.wrap_text)
        self.assertGreater(sheet.row_dimensions[4].height, sheet.sheet_format.defaultRowHeight)
        self.assertIn("B4:B5", {str(r) for r in sheet.merged_cells.ranges})
        blank = load_workbook(media_word.XLSX_TEMPLATE)
        self.assertEqual(copy.copy(sheet["I4"].fill), copy.copy(blank["sheet1"]["I4"].fill))
        self.assertEqual(copy.copy(sheet["I4"].font), copy.copy(blank["sheet1"]["I4"].font))
        blank.close()
        workbook.close()

    def test_xlsx_missing_pool_and_overwrite_preserve_original(self):
        a, p = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "推荐媒体.xlsx"
            with self.assertRaisesRegex(ValueError, "media_recommendations"):
                media_word.export_xlsx(a, {"placements": p["placements"]}, output)
            self.assertFalse(output.exists())
            output.write_bytes(b"existing-user-workbook")
            with self.assertRaises(FileExistsError):
                media_word.export_xlsx(a, p, output)
            self.assertEqual(output.read_bytes(), b"existing-user-workbook")

    def test_cli_defaults_to_excel_and_preserves_explicit_word_output(self):
        a, p = self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            analysis_path, plan_path = folder / "analysis.json", folder / "plan.json"
            analysis_path.write_text(json.dumps({"project": a["project"]}, ensure_ascii=False), encoding="utf-8")
            plan_path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(folder)
                argv = ["export_media_word.py", "--analysis", str(analysis_path), "--plan", str(plan_path)]
                with patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
                    self.assertEqual(media_word.main(), 0)
                workbook = load_workbook(folder / "推荐媒体.xlsx")
                self.assertEqual(workbook.sheetnames, ["sheet1", "sheet2"])
                workbook.close()
                with patch.object(sys, "argv", argv + ["--output", str(folder / "兼容推荐媒体.docx")]), redirect_stdout(StringIO()):
                    self.assertEqual(media_word.main(), 0)
                self.assertEqual(len(Document(folder / "兼容推荐媒体.docx").tables), 2)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
