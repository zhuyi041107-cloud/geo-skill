"""Offline business-flow checks; GPT responses are explicit mocks, files are real."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import fitz
import openpyxl
from PIL import Image

SKILL = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo"
sys.path.insert(0, str(SKILL / "scripts"))
import geo_data
import geo_gpt
import gpt_client
import media


class LocalGPTBusinessFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project_fixture, cls.plan_fixture, cls.report_fixture = (
            json.loads((SKILL / "references" / f"{name}.example.json").read_text(encoding="utf-8"))
            for name in ("project", "plan", "report")
        )
        wanted = {geo_gpt.identity(item) for item in cls.plan_fixture["media_recommendations"]}
        cls.candidates = []
        for sheet, row_number, row in media.catalog_rows(media.CATALOG):
            if (sheet, str(row["软文街id"])) not in wanted:
                continue
            cls.candidates.append({
                "media_id": str(row["软文街id"]), "media_name": row["媒体名称"],
                "source_sheet": sheet, "source_row": row_number,
                "source_file": row["原报价文件"], "quotation_date": row["报价日期"],
                "category": row["媒体分类"], "region": row["地区"], "portal": row["综合门户"],
                "entry_type": row["入口类型"], "editorial_note": row["备注"],
                "market_price": media.price(row["市场价格"]),
                "market_reference_price": media.price(row["市场价格"]),
                "tier_prices": {tier: media.price(row[tier]) for tier in media.TIERS},
                "tier_price_source": f"{row['原报价文件']} / {sheet} / 第{row_number}行 / 原表六档报价",
                "unit_price": None, "status": media.restriction(row["备注"]),
            })
        if {geo_gpt.identity(item) for item in cls.candidates} != wanted:
            raise AssertionError("Fictional fixture references missing real media rows")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="geo-gpt-offline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = copy.deepcopy(self.project_fixture)
        self.project_path = self.root / "project.json"
        self.project_path.write_text(json.dumps(self.project, ensure_ascii=False), encoding="utf-8")
        self.screenshot = self.root / "虚构原始引用截图.png"
        Image.new("RGB", (40, 30), "white").save(self.screenshot)
        self.answers = self.root / "内部回答.xlsx"
        geo_data.prepare_internal(self.project, self.answers)
        book = openpyxl.load_workbook(self.answers)
        for header, value in {
            "采集状态": "已完成", "回答全文": "虚构测试：知桥协同提供知识服务，可按团队权限和出处需求比较。",
            "引用展示": "未展示", "采集时间": "2026-11-11",
            "回答证据路径": str(self.screenshot),
        }.items():
            book["回答记录"].cell(2, geo_data.SAMPLE_HEADERS.index(header) + 1, value)
        book.save(self.answers)
        book.close()
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "offline-test-placeholder-not-real", "GEO_WORKSPACE": str(self.root)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []
        self.fail_review = False

    def draft(self):
        plan = self.plan_fixture
        fields = ("content_id", "title", "content_group", "question_ids", "keywords", "evidence", "stage", "scheduled_date")
        return {
            "stages": copy.deepcopy(plan["stages"]),
            "contents": [{key: copy.deepcopy(item[key]) for key in fields} for item in plan["contents"]],
            "allocations": [
                {"content_id": ordinary["content_id"], "strategy_role": ordinary["strategy_role"],
                 "strategy_basis": ordinary["strategy_basis"], "quantity": ordinary["quantity"],
                 "ordinary": {key: ordinary[key] for key in ("source_sheet", "media_id")},
                 "higher": {key: higher[key] for key in ("source_sheet", "media_id")}}
                for ordinary, higher in zip(plan["placements"], plan["quote_options"][0]["placements"])
            ],
            "recommendations": [
                {"resource": {key: item[key] for key in ("source_sheet", "media_id")},
                 "reason": item.get("recommendation_reason") or "按虚构客户的知识服务业务筛选。"}
                for item in plan["media_recommendations"]
            ],
            "work_items": copy.deepcopy(plan["service_scope"]["work_items"]),
            "review_schedule": plan["service_scope"]["review_schedule"],
            "writing_mode": plan["service_scope"]["writing_mode"],
            "logic_links": ["权限与出处的选择理由对应内容、三类媒体和阶段复核。"],
        }

    def mocked_gpt(self, instructions, payload, schema, **kwargs):
        name = kwargs["schema_name"]
        self.calls.append((name, payload, kwargs.get("images", [])))
        if name == "geo_analysis":
            finding = {"finding": "能够识别知识服务方向。", "evidence_refs": ["Q001-C001-R01"], "implication": "补强采购场景的选择理由。"}
            result = {
                "judgments": [{"sample_id": "Q001-C001-R01", "mention": "是", "recommendation": "是", "reason": "回答将品牌列为可比较对象。"}],
                "brand_perception": [finding], "competitor_analysis": [], "brand_strengths": [],
                "business_scenes": [{"scene": "团队知识检索", "audience": "知识管理员", "selection_reason": "按权限与出处要求比较", "evidence_refs": ["Q001-C001-R01"], "priority": "高"}],
                "fact_issues": [], "content_directions": ["权限与出处"], "media_queries": ["IT科技"],
                "overall_conclusion": "围绕业务场景补强可核验的选择理由。",
            }
        elif name == "geo_plan":
            result = self.draft()
        elif name == "geo_customer_report":
            result = gpt_client.report_to_api(copy.deepcopy(self.report_fixture))
        elif name == "geo_final_review":
            count = 8 if payload["document"] == "diagnosis" else 9
            result = {
                "overall_pass": not self.fail_review, "content_findings": [],
                "pages": [{"page": index, "passed": not self.fail_review,
                           "issues": ["离线测试模拟未通过"] if self.fail_review and index == 1 else [],
                           "fix": "精简该页文字" if self.fail_review else "无需修改"}
                          for index in range(1, count + 1)],
            }
        else:
            self.fail("Unexpected model request: " + name)
        gpt_client.validate_json(result, schema)
        return result

    def prepare_draft(self):
        analyzed = geo_gpt.analyze_customer(str(self.root), str(self.project_path), str(self.answers))
        run = Path(analyzed["run_dir"])
        candidate_file = run / "offline-candidates.json"
        geo_gpt.write(candidate_file, {"candidates": self.candidates})
        created = geo_gpt.create_plan(str(run), [str(candidate_file)])
        self.assertEqual([item["total"] for item in created["budgets"]], ["20400.00", "28800.00"])
        geo_gpt.write_reports(str(run))
        return run

    def test_offline_flow_requires_review_and_publishes_only_exact_reviewed_files(self):
        source_bytes = self.answers.read_bytes()
        with patch.object(gpt_client, "complete_json", side_effect=self.mocked_gpt):
            run = self.prepare_draft()
            with self.assertRaises(ValueError):
                geo_gpt.publish(str(run), str(self.root / "未审输出"))
            self.assertFalse((self.root / "未审输出").exists())
            reviewed = geo_gpt.review_deliverables(str(run))
            self.assertTrue(reviewed["passed"])
            review_calls = [call for call in self.calls if call[0] == "geo_final_review"]
            self.assertEqual([len(call[2]) for call in review_calls], [17, 19])
            self.assertTrue(all(Path(image["path"]).is_file() for call in review_calls for image in call[2]))
            self.assertTrue(all(self.screenshot in {Path(image["path"]) for image in call[2]} for call in review_calls))
            record = geo_gpt.read(geo_gpt.latest(run, "draft"))
            actual_pdf = Path(record["documents"]["diagnosis"]["pdf"])
            original_pdf = actual_pdf.read_bytes()
            actual_pdf.write_bytes(original_pdf + b"\nchanged-after-review")
            with self.assertRaisesRegex(ValueError, "改变|变化"):
                geo_gpt.publish(str(run), str(self.root / "变更输出"))
            actual_pdf.write_bytes(original_pdf)
            self.project_path.write_bytes(self.project_path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "原始资料"):
                geo_gpt.publish(str(run), str(self.root / "原件变更输出"))
            self.project_path.write_text(json.dumps(self.project, ensure_ascii=False), encoding="utf-8")
            output = self.root / "正式输出"
            published = geo_gpt.publish(str(run), str(output))
            self.assertTrue(published["passed"])
            self.assertEqual({path.name for path in output.iterdir()}, set(geo_gpt.CUSTOMER_FILES))
            for kind, count in (("diagnosis", 8), ("execution", 9)):
                with fitz.open(output / geo_gpt.export_pdf.FILES[kind]) as doc:
                    self.assertEqual(len(doc), count)
                self.assertEqual((output / geo_gpt.export_pdf.FILES[kind]).read_bytes(), Path(record["documents"][kind]["pdf"]).read_bytes())
            book = openpyxl.load_workbook(output / "推荐媒体.xlsx", read_only=True)
            self.assertEqual(book.sheetnames, ["sheet1", "sheet2"])
            book.close()
            with self.assertRaises(FileExistsError):
                geo_gpt.publish(str(run), str(output))
            with patch.object(gpt_client, "complete_json", side_effect=gpt_client.GPTError("离线模拟API中断")):
                with self.assertRaises(gpt_client.GPTError):
                    geo_gpt.review_deliverables(str(run))
            with self.assertRaises(ValueError):
                geo_gpt.publish(str(run), str(self.root / "终审中断输出"))
            self.fail_review = True
            self.assertFalse(geo_gpt.review_deliverables(str(run))["passed"])
            with self.assertRaisesRegex(ValueError, "终审尚未通过"):
                geo_gpt.publish(str(run), str(self.root / "审核未通过输出"))
        self.assertEqual(source_bytes, self.answers.read_bytes())

    def test_unknown_or_contaminated_media_cannot_enter_hydrated_plan(self):
        draft = self.draft()
        draft["allocations"][0]["ordinary"]["media_id"] = "UNKNOWN-OFFLINE-ID"
        with self.assertRaises(ValueError):
            geo_gpt.hydrate_plan(draft, self.candidates, self.project)
        contaminated = copy.deepcopy(self.candidates)
        target = next(item for item in contaminated if geo_gpt.identity(item) == geo_gpt.identity(self.draft()["allocations"][0]["ordinary"]))
        canonical = next(item for item in self.candidates if geo_gpt.identity(item) == geo_gpt.identity(target))
        target["tier_prices"]["超级代理"] = "0.01"
        try:
            plan = geo_gpt.hydrate_plan(self.draft(), contaminated, self.project)
        except ValueError:
            return
        row = next(item for item in plan["placements"] if geo_gpt.identity(item) == geo_gpt.identity(canonical))
        self.assertEqual(row["tier_prices"], canonical["tier_prices"], "Candidate-file edits must not become original quote data")

    def test_intent_budget_is_not_a_ceiling_and_media_fee_minimum_is_enforced(self):
        project = {**self.project, "budget_target": "2000.00", "budget_limit": None}
        plan = geo_gpt.hydrate_plan(self.draft(), self.candidates, project)
        budget = geo_data.calculate_budget(project, plan)
        self.assertEqual(budget["client"]["total"], "20400.00")
        short = self.draft()
        short["contents"] = short["contents"][:1]
        chosen_id = short["contents"][0]["content_id"]
        short["allocations"] = [item for item in short["allocations"] if item["content_id"] == chosen_id]
        with self.assertRaises(ValueError):
            geo_gpt.hydrate_plan(short, self.candidates, project)

    def test_changed_project_business_facts_are_not_silently_replaced_by_old_workbook(self):
        for field, value in (("budget_limit", "15000.00"), ("services", ["用户刚补充的业务范围"])):
            updated = {**self.project, field: value}
            self.project_path.write_text(json.dumps(updated, ensure_ascii=False), encoding="utf-8")
            with self.subTest(field=field), patch.object(gpt_client, "complete_json") as paid_call:
                with self.assertRaises(ValueError):
                    geo_gpt.analyze_customer(str(self.root), str(self.project_path), str(self.answers))
                paid_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
