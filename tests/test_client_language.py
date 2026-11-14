import sys
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / '.codebuddy/skills/ruanwenjie-geo/scripts'
sys.path.insert(0, str(SCRIPTS))
import check_client_report


class ClientLanguageTests(unittest.TestCase):
    def test_production_instructions_are_not_client_analysis(self):
        examples = [
            '现有印象与实际回答一致。',
            '目标标签只写事实能支持的部分。',
            '避免同义标题重复计篇。',
            '稿数由本期执行计划汇总。',
            '不额外补造报价档位。',
            '按照原模板填写客户内容。',
            '这些数据留在内部底稿。',
            '本报告的制作过程包含采集与整理。',
        ]
        for value in examples:
            with self.subTest(value=value):
                self.assertTrue(check_client_report.check([(2, value)]))

    def test_business_analysis_and_scope_remain_allowed(self):
        examples = [
            '豆包将品牌描述为轻量答疑，专业匹配与服务过程尚未形成清晰优势。',
            '贵司负责确认合同条款，软文街负责内容策划、发布与阶段复核。',
            '普通权重方案包括内容策划、AI起草与人工简单修改、媒体发布和阶段复核。',
            '产品支持API接口集成，适用于已有知识库的团队。',
            '人工撰写按独立稿数计费，同稿增加刊发不增加写稿费。',
            '用可核对的首饰制作过程说明工艺细节。',
        ]
        for value in examples:
            with self.subTest(value=value):
                self.assertEqual(check_client_report.check([(4, value)]), [])

    def test_extracted_chinese_spacing_does_not_hide_process_language(self):
        self.assertTrue(check_client_report.check([(3, '目 标 标 签 只 写 事 实 能 支 持 的 部 分。')]))


if __name__ == '__main__':
    unittest.main()
