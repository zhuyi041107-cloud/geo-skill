import importlib.util
import csv
import gzip
from decimal import Decimal
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

SCRIPT = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts/media.py"
spec = importlib.util.spec_from_file_location("geo_media", SCRIPT)
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class MediaTests(unittest.TestCase):
    @unittest.skipUnless((SCRIPT.parents[5] / "软文街2026年11月10日资源报价_857a66.xlsx").exists(), "完整原报价未置于仓库同级目录")
    def test_all_builtin_six_tiers_match_original_quote(self):
        source = SCRIPT.parents[5] / "软文街2026年11月10日资源报价_857a66.xlsx"
        book = load_workbook(source, read_only=True, data_only=True)
        count = 0
        try:
            with gzip.open(media.CATALOG, "rt", encoding="utf-8", newline="") as stream:
                catalog = csv.DictReader(stream)
                self.assertEqual(catalog.fieldnames, list(media.CATALOG_FIELDS))
                for sheet in media.SHEETS.values():
                    rows = book[sheet].iter_rows(values_only=True)
                    headers = list(next(rows))
                    for line, values in enumerate(rows, 2):
                        row = dict(zip(headers, values))
                        if not row.get("媒体名称"):
                            continue
                        item = next(catalog)
                        self.assertEqual((item["source_sheet"], item["source_row"], item["media_id"]), (sheet, str(line), str(row["软文街id"])))
                        expected = {field: media.price(row.get(tier)) or "" for tier, field in media.TIER_FIELDS.items()}
                        actual = {field: item[field] for field in media.TIER_FIELDS.values()}
                        if actual != expected:
                            self.fail(f"六档原价不一致：{sheet} 第{line}行")
                        for tier in media.TIERS:
                            parsed = media.price(row.get(tier))
                            if parsed is not None:
                                self.assertEqual(Decimal(parsed), Decimal(str(row[tier]).strip().replace(",", "").lstrip("¥￥")))
                        count += 1
                self.assertIsNone(next(catalog, None))
            self.assertEqual(count, 91628)
        finally:
            book.close()

    def test_public_catalog_keeps_six_quote_tiers_and_omits_supplier_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "fiction.xlsx", Path(folder) / "catalog.csv.gz"
            book = Workbook()
            for index, name in enumerate(media.SHEETS.values()):
                sheet = book.active if index == 0 else book.create_sheet()
                sheet.title = name
                sheet.append(["媒体名称", "软文街id", *media.TIERS, "备注", "渠道类型", "渠道名称", "媒体分类", "地区", "综合门户", "入口类型"])
                sheet.append(["虚构媒体（1000-1100字）", f"FAKE-{index}", 120, 42, 51.2, 63, None, "询价", "不发GEO；联系方式默认删除；微信:fiction_wx01；电话13800000000", "独家", "虚构联系人", "招聘", "山西", "虚构门户", "栏目页"])
            book.save(source);book.close()
            audit = media.build_catalog(source, target, "2026-11-10")
            self.assertEqual(audit["records"], 2)
            with gzip.open(target, "rt", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertNotIn("channel_name", rows[0])
            self.assertNotIn("channel_type", rows[0])
            self.assertNotIn("超级代理", rows[0])
            self.assertEqual(rows[0]["super_agent_price"], "42.00")
            self.assertEqual(rows[0]["core_agent_price"], "51.20")
            self.assertEqual(rows[0]["regular_agent_price"], "")
            self.assertEqual(rows[0]["member_price"], "")
            self.assertEqual(rows[0]["media_name"], "虚构媒体（1000-1100字）")
            self.assertIn("不发GEO", rows[0]["editorial_note"])
            self.assertIn("联系方式默认删除", rows[0]["editorial_note"])
            self.assertNotIn("fiction_wx01", rows[0]["editorial_note"])
            self.assertNotIn("13800000000", rows[0]["editorial_note"])
            self.assertEqual(media.search_media(target)["stats"]["excluded_geo"], 2)

    def test_builtin_tier_selection_keeps_market_budget_and_traceable_six_prices(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "fiction.xlsx", Path(folder) / "catalog.csv.gz"
            book = Workbook()
            for index, name in enumerate(media.SHEETS.values()):
                sheet = book.active if index == 0 else book.create_sheet()
                sheet.title = name
                sheet.append(["媒体名称", "软文街id", *media.TIERS, "备注", "地区"])
                sheet.append(["虚构媒体", f"FAKE-{index}", 120, 0, 51.2, 63, None, "询价", "", "全国"])
            book.save(source); book.close()
            media.build_catalog(source, target, "2026-11-10")
            default = media.search_media(target, kind="network")["candidates"][0]
            self.assertIsNone(default["unit_price"])
            self.assertEqual(default["market_reference_price"], "120.00")
            self.assertEqual(default["tier_prices"], dict(zip(media.TIERS, ["120.00", "0.00", "51.20", "63.00", None, None])))
            self.assertIn("fiction.xlsx / 网络媒体报价 / 第2行", default["tier_price_source"])
            selected = media.search_media(target, "核心代理", kind="network", min_price="51", max_price="52")["candidates"][0]
            self.assertEqual(selected["unit_price"], "51.20")
            self.assertEqual(selected["selected_tier_price"], "51.20")
            self.assertEqual(selected["market_reference_price"], "120.00")
            unknown = media.search_media(target, "普通会员", kind="network")["candidates"][0]
            self.assertIsNone(unknown["selected_tier_price"])
            self.assertEqual(unknown["status"], "需核实")
            self.assertFalse(media.search_media(target, "普通会员", kind="network", min_price="1")["candidates"])
    def test_prices_are_not_invented(self):
        self.assertEqual(media.price("￥1,200.5"), "1200.50")
        for item in (None, "询价", "200起", "NaN", "Infinity", -1, True):
            self.assertIsNone(media.price(item))

    def test_explicit_and_conditional_editorial_limits(self):
        self.assertEqual(media.restriction("不发GEO，不发医疗"), "排除")
        self.assertEqual(media.restriction("GEO稿不接"), "排除")
        self.assertEqual(media.restriction("不发geo对比测评稿"), "需核实")
        self.assertEqual(media.restriction("GEO需提供真实案例"), "需核实")
        self.assertEqual(media.restriction("普通新闻，需要配图"), "候选")

    def test_filter_traceability_and_missing_region(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "报价.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "网络媒体报价"
            sheet.append(["媒体名称", "软文街id", "普通会员", "备注", "地区", "媒体分类"])
            sheet.append(["科技甲", "N1", 100, "不发GEO", "山西", "科技"])
            sheet.append(["科技乙", "N2", 150, "", None, "科技"])
            sheet.append(["科技丙", "N3", 120, "", "北京", "科技"])
            sheet.append(["科技丁", "N4", 80, "不发GEO对比测评", "全国", "科技"])
            book.save(path)
            book.close()
            result = media.search_media(path, "普通会员", "科技", "山西", "network", 10)
            self.assertEqual(result["stats"]["excluded_geo"], 1)
            self.assertEqual({c["media_id"] for c in result["candidates"]}, {"N2", "N4"})
            self.assertTrue(all(c["status"] == "需核实" for c in result["candidates"]))
            self.assertEqual(result["candidates"][0]["source_row"], 5)
            self.assertEqual(result["candidates"][0]["source_file"], "报价.xlsx")
            band = media.search_media(path, "普通会员", "科技", "山西", "network", 10, min_price="100", max_price="150")
            self.assertEqual([c["media_id"] for c in band["candidates"]], ["N2"])
            with self.assertRaisesRegex(ValueError, "最低价格"):
                media.search_media(path, "普通会员", min_price="150", max_price="100")

    def test_missing_header_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "报价.xlsx"
            book = Workbook()
            book.active.title = "网络媒体报价"
            book.active.append(["媒体名称"])
            book.save(path)
            book.close()
            with self.assertRaisesRegex(ValueError, "缺少字段"):
                media.search_media(path, "普通会员", kind="network")


if __name__ == "__main__":
    unittest.main()
