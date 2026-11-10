import importlib.util
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

SCRIPT = Path(__file__).resolve().parents[1] / ".codebuddy/skills/ruanwenjie-geo/scripts/media.py"
spec = importlib.util.spec_from_file_location("geo_media", SCRIPT)
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class MediaTests(unittest.TestCase):
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
