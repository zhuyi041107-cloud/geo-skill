import copy
from io import BytesIO
import sys
from pathlib import Path
import unittest

from pypdf import PdfReader

SCRIPT_DIR = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import export_pdf
from geo_data import calculate_budget


class ExportPdfTests(unittest.TestCase):
    def fixture(self):
        actual = {"platform": "演示平台A", "mode": "网页端", "online": "是", "round": 1}
        project = {"project_id": "PDF-TEST", "client_name": "测试企业（虚构）", "brand_names": ["测试品牌"], "currency": "CNY", "budget_limit": None,
                   "contexts": [actual, {"platform": "未回传平台B"}]}
        plan = {"contents": [{"content_id": "C001", "title": "企业知识库实施指南", "stage": "需求选择", "scheduled_date": "2027-01-15", "status": "已选"}],
                "placements": [{"placement_id": "P001", "content_id": "C001", "media_id": "M001", "media_name": "示例技术观察网（虚构）", "status": "已选", "unit_price": "37.00", "client_unit_price": "480.00", "quantity": 2, "scheduled_date": "2027-01-15", "price_tier": "内部成本档位", "price_basis": "市场参考价", "quotation_date": "2026-10-28"}], "fees": []}
        analysis = {"schema_version": 1, "project": project, "sampled_contexts": [actual], "report_scope": {"platforms": [actual["platform"]], "report_date": "2026-11-10"},
                    "counts": {"completed": 2, "valid": 2}, "groups": [{**actual, "question_type": "自然需求", "intent": "推荐", "valid": 2, "completed": 2, "mention_yes": 1, "mention_no": 1, "recommendation_yes": 1, "recommendation_no": 1}],
                    "budget": calculate_budget(project, plan)}
        entry = {"title": "业务选择缺口", "detail": "本轮品牌可以被识别，但交付范围与维护责任没有清楚进入选择理由。应以真实服务边界和可公开案例承接客户需求，减少初筛时的信息不确定性。", "evidence_ref": ["EV-internal-001", "Q001", r"C:\private\source.json"]}
        report = {"diagnosis": {"summary": "本报告使用虚构测试数据，只检查业务正文、同源数字和可读的中文排版。品牌已被识别，需求入口仍需要内容承接。", "brand_status": [entry], "demand_entries": [entry], "key_findings": [entry], "priorities": [entry]},
                  "execution": {"objectives": [entry], "keywords": [entry], "media_rationale": [entry], "quarterly": [entry], "expected_deliverables": [entry]}}
        return analysis, plan, report

    def test_customer_text_numbers_and_embedded_chinese_font(self):
        analysis, plan, report = self.fixture()
        for kind in ("diagnosis", "execution"):
            reader = PdfReader(BytesIO(export_pdf.build_pdf(kind, analysis, plan, report)))
            text = "".join(p.extract_text() for p in reader.pages)
            self.assertIn("测试品牌", text)
            self.assertNotIn("未回传平台B", text)
            for private in ("Q001", "C001", "P001", "EV-internal", "private", "normalize", "采样范围与方法", "内部成本档位", "¥37.00"):
                self.assertNotIn(private, text)
            if kind == "execution":
                self.assertIn("¥960.00", text)
                self.assertIn("建议媒体投放包", text)
                self.assertIn("市场参考价", text)
                self.assertIn("2026-10-28", text)
                self.assertEqual(text.count("自然季度"), 1)
                self.assertNotIn("其他服务费用", text)
            embedded = []
            for page in reader.pages:
                for item in page["/Resources"]["/Font"].values():
                    font = item.get_object()
                    descriptor = font.get("/FontDescriptor")
                    if descriptor:
                        embedded.append("/FontFile2" in descriptor.get_object())
            self.assertIn(True, embedded)
            self.assertTrue(all(len(p.extract_text()) > 30 for p in reader.pages))

    def test_long_narrative_and_media_table_survive_page_splits(self):
        analysis, plan, report = self.fixture()
        report["diagnosis"]["key_findings"] = [{"title": "长文分析", "detail": "业务边界应由真实交付事实支撑，避免用笼统功能代替客户的选择理由。" * 220 + "末尾核验内容仍然完整。"}]
        diagnosis = PdfReader(BytesIO(export_pdf.build_pdf("diagnosis", analysis, plan, report)))
        self.assertGreater(len(diagnosis.pages), 2)
        self.assertIn("末尾核验内容仍然完整", "".join(p.extract_text() for p in diagnosis.pages))
        for i in range(2, 33):
            content = copy.deepcopy(plan["contents"][0]); content["content_id"] = f"C{i:03d}"; content["title"] = f"企业交付与服务边界专题第{i}篇"
            placement = copy.deepcopy(plan["placements"][0]); placement.update(placement_id=f"P{i:03d}", content_id=content["content_id"])
            plan["contents"].append(content); plan["placements"].append(placement)
        analysis["budget"] = calculate_budget(analysis["project"], plan)
        execution = PdfReader(BytesIO(export_pdf.build_pdf("execution", analysis, plan, report)))
        full_text = "".join(p.extract_text() for p in execution.pages)
        self.assertGreaterEqual(full_text.count("媒体名称"), 2)
        self.assertIn("企业交付与服务边界专题第32篇", full_text.replace("\n", ""))

    def test_reject_stale_budget_placeholder_media_and_internal_prose(self):
        analysis, plan, report = self.fixture()
        changed = copy.deepcopy(plan); changed["placements"][0]["client_unit_price"] = "999.00"
        with self.assertRaisesRegex(ValueError, "预算不一致"):
            export_pdf.build_pdf("execution", analysis, changed, report)
        changed = copy.deepcopy(plan); changed["placements"][0]["media_name"] = "行业类媒体（待报价）"
        analysis["budget"] = calculate_budget(analysis["project"], changed)
        with self.assertRaisesRegex(ValueError, "具体媒体"):
            export_pdf.build_pdf("execution", analysis, changed, report)
        report["diagnosis"]["key_findings"][0]["detail"] = "请参见Q001以及本机处理目录。"
        with self.assertRaisesRegex(ValueError, "内部编号"):
            export_pdf.build_pdf("diagnosis", analysis, plan, report)


if __name__ == "__main__":
    unittest.main()
