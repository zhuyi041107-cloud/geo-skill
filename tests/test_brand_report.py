import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import fitz

ROOT = Path(__file__).resolve().parents[1] / '.codebuddy/skills/ruanwenjie-geo'
sys.path.insert(0, str(ROOT / 'scripts'))
import render_brand_report as renderer


def config():
    return {
        'customer': {'brand': '澄金珠宝', 'company': '澄金珠宝设计有限公司', 'date': '2026-11-14', 'observed_platforms': ['豆包']},
        'theme': {'primary': '#8C1635', 'accent': '#B6976C', 'background': '#FAF7F1', 'text': '#29242A', 'cover_style': 'editorial'},
        'purpose': '以工艺事实建立高端日常珠宝的选择理由。',
        'pages': [
            {'layout': 'cover', 'title': '品牌认知与内容建设', 'headline': '让工艺与佩戴场景形成清晰关联'},
            {'layout': 'insights', 'title': '从品牌介绍走向场景选择', 'items': [
                {'heading': '品牌定位仍偏宽泛', 'body': '品牌介绍能够被理解，具体工艺与日常佩戴选择理由仍不充分。',
                 'impact': '读者需要更清晰的工艺比较条件。', 'action': '补充有出处的工艺和使用场景说明。'}]},
        ],
    }


def report(document):
    return {'schema_version': '3.0', 'customer': document['customer'], 'theme': document['theme'],
            'purpose': document['purpose'], 'diagnosis': {'pages': document['pages']}}


class BrandReportTests(unittest.TestCase):
    def test_document_counts_and_titles_are_not_locked(self):
        document = config()
        for count in [1, 3, 11]:
            document['pages'] = [{'layout': 'text', 'title': f'业务判断{index}', 'paragraphs': ['不同场景需要不同的选择依据。']} for index in range(count)]
            self.assertEqual(renderer.validate(document), [])

    def test_source_template_is_not_renderable_until_prepared(self):
        document = config()
        document['pages'][1] = {'layout': 'insights', 'title': '品牌认知', 'source': 'findings', 'ids': ['F-1']}
        self.assertEqual(renderer.validate_report(report(document)), [])
        self.assertTrue(renderer.validate(document))
        document['pages'][1]['items'] = [{'heading': '自由添加', 'body': '不能覆盖计划。'}]
        self.assertTrue(renderer.validate_report(report(document)))

    def test_unknown_layout_bad_table_and_unreadable_theme_rejected(self):
        document = config()
        document['pages'][1] = {'layout': 'unknown', 'title': '业务分析'}
        self.assertTrue(renderer.validate(document))
        document['pages'][1] = {'layout': 'table', 'title': '工作安排', 'headers': ['事项', '作用'], 'rows': [['缺列']]}
        self.assertTrue(renderer.validate(document))
        document = config(); document['theme']['text'] = document['theme']['background']
        self.assertTrue(renderer.validate(document))

    def test_internal_process_copy_is_rejected_but_brand_colors_are_allowed(self):
        document = config()
        document['pages'][1]['items'][0]['body'] = '按照原模板填写客户内容。'
        self.assertTrue(renderer.validate(document))
        document = config(); document['theme']['primary'] = '#F5D67A'
        self.assertEqual(renderer.validate(document), [])

    def test_actual_pdf_bounds_and_distinct_brand_styles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            first = renderer.render(config(), path / 'jewelry', png_scale=.2)
            industrial = config()
            industrial['customer'].update(brand='锐感工业', company='锐感工业技术有限公司')
            industrial['theme'] = {'primary': '#12578C', 'accent': '#D86B32', 'background': '#F3F7FA', 'text': '#17314A', 'cover_style': 'technical'}
            second = renderer.render(industrial, path / 'industrial', png_scale=.2)
            with fitz.open(first['pdf']) as a, fitz.open(second['pdf']) as b:
                self.assertEqual(len(a), 2)
                self.assertEqual(a[0].rect, fitz.Rect(0, 0, 1200, 675))
                self.assertIn('澄金珠宝设计有限公司', ''.join(a[0].get_text().split()))
                self.assertNotEqual(a[0].get_pixmap().pixel(1, 1), b[0].get_pixmap().pixel(1, 1))
            for result in [first, second]:
                audit = json.loads(Path(result['audit']).read_text(encoding='utf-8'))
                self.assertTrue(audit['bounds_ok'])
                self.assertEqual(audit['page_count'], len(result['rendered_pages']))
                self.assertTrue(audit['blocks'])

    def test_long_table_repeats_headers_without_losing_rows(self):
        document = config()
        document['pages'] = [{'layout': 'table', 'title': '持续内容任务', 'headers': ['任务', '材料与业务用途'],
                              'rows': [[f'任务{index:03d}', '工艺、使用场景与售后条件需要清晰说明。' * 3] for index in range(85)]}]
        with tempfile.TemporaryDirectory() as directory:
            result = renderer.render(document, directory, png_scale=.1)
            with fitz.open(result['pdf']) as pdf:
                self.assertGreater(len(pdf), 1)
                full = ''.join(page.get_text() for page in pdf)
                for index in range(85): self.assertIn(f'任务{index:03d}', full)
                for page in pdf: self.assertIn('材料与业务用途', ''.join(page.get_text().split()))

    def test_long_card_and_single_table_row_split_without_truncation(self):
        document = config()
        document['pages'] = [
            {'layout': 'insights', 'title': '工艺证据', 'items': [
                {'heading': '工艺与佩戴条件', 'body': '不同工艺需要结合佩戴场景解释，材料说明应便于读者理解。' * 130 + '保留长卡片结尾。'}]},
            {'layout': 'table', 'title': '专业内容', 'headers': ['方向', '完整说明'],
             'rows': [['技术选型', '参数与实际应用条件需要逐项对应，不能只罗列型号。' * 100 + '保留长表格结尾。']]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = renderer.render(document, directory, png_scale=.1)
            with fitz.open(result['pdf']) as pdf:
                text = ''.join(''.join(page.get_text().split()) for page in pdf)
                self.assertGreater(len(pdf), 2)
                self.assertIn('保留长卡片结尾。', text)
                self.assertIn('保留长表格结尾。', text)

    def test_jewelry_case_keeps_ordinary_card_and_action_row_whole(self):
        # Reproduces customer A: a third insight used to leave only its action
        # on a new page, while the action table repeated headers mid-page.
        document = config()
        insight = {'heading': '求婚定制场景仍被现货选择占据',
                   'body': '回答偏向现货品牌，说明当前可见信息没有充分解释设计咨询、看样与定制决策的关系。交期、改款和价格须由客户确认后再写。',
                   'impact': '有个性表达需求的消费者，可能在了解咨询与看样服务之前就转向现货选择。',
                   'action': '把求婚与看样需求接到服务路径'}
        items = [
            {'heading': '能被点名介绍，尚未进入高端金饰自然候选',
             'body': '品牌名称与手工金饰已有基本关联，但需求推荐仍由同行占据。现有表达尚未提供足够清楚的选购理由，不能据此断言全网缺席。',
             'impact': '未认识品牌的消费者，难以从品类需求进入设计咨询或预约看样。',
             'action': '以真实作品解释选购理由；把求婚与看样需求接到服务路径；建立清楚的品牌与服务事实表达'},
            {'heading': '手工工艺与服务的区别还没有说透',
             'body': '手工金饰是客户提供的业务方向，尚不能等同于已证明的工艺领先。材质、工序、佩戴体验及售后边界，需要具体作品和核准条款支撑。',
             'impact': '消费者知道品牌做什么，却缺少比较溢价、工艺与服务时可使用的依据。',
             'action': '统一品牌事实与服务边界；以真实作品解释选购理由'}, insight]
        rows = [
            ['手工工艺与服务的区别还没有说透；可见来源以自有内容为主，独立工艺案例不足',
             '统一品牌事实与服务边界\n整理主体、作品授权、材质工序及咨询看样说明；售后条款核准后使用，不写未证实荣誉。\n关键词：瑾澜金艺、手工金饰、预约看样',
             '官网作为事实入口，三类媒体采用统一口径\n启动第1周', '软文街梳理，客户确认并更新官网\n交付：一份事实与服务清单', '每项工艺及服务说法均有客户确认；无非遗或获奖暗示。'],
            ['能被点名介绍，尚未进入高端金饰自然候选；手工工艺与服务的区别还没有说透；可见来源以自有内容为主，独立工艺案例不足',
             '以真实作品解释选购理由\n6篇：选购判断2篇、授权作品工艺2篇、已核服务问答2篇；用可展示事实说明差异。\n关键词：手工金饰怎么选、金饰工艺比较',
             '行业媒体6次，承接工艺与选购判断\n第2—6周分批刊发', '软文街策划写作及发布，客户专业审核\n交付：6篇原创稿、6次行业媒体发布', '作品可追溯；不把手工等同于保值、质量第一或投资回报。'],
            ['能被点名介绍，尚未进入高端金饰自然候选；求婚定制场景仍被现货选择占据',
             '把求婚与看样需求接到服务路径\n4篇：求婚设计咨询2篇、预约看样与沟通准备2篇；交期价格只采用核准信息。\n关键词：求婚金饰设计咨询、金饰预约看样',
             '自媒体4次，解释场景与咨询路径\n第2—6周与工艺内容配合', '软文街策划写作及发布，客户审核服务条件\n交付：4篇原创稿、4次自媒体发布', '区分现货和咨询服务；不承诺尚未确认的定制交期或退款政策。'],
            ['能被点名介绍，尚未进入高端金饰自然候选；可见来源以自有内容为主，独立工艺案例不足',
             '建立清楚的品牌与服务事实表达\n2篇品牌及设计服务稿；汇总全部刊发链接，季度末对照需求推荐与选择理由变化。\n关键词：瑾澜金艺设计咨询、瑾澜珠宝有限公司',
             '权威媒体2次，说明主体与业务事实\n第2周与第5周；季度末复盘', '软文街写作发布及复盘，客户审核与配合\n交付：2篇原创稿、2次权威媒体发布；12条链接汇总、1次季度复盘', '商业刊发不表述为官方推荐；复盘关注自然候选、具体理由与引用变化。'],
        ]
        document['pages'] = [
            {'layout': 'insights', 'title': '本季度要解决的三个业务问题', 'items': items},
            {'layout': 'table', 'title': '诊断对应执行安排', 'lead': '事实先统一；选购、场景与品牌内容分工协作。',
             'headers': ['对应诊断', '执行动作与内容', '媒体与阶段', '分工与交付', '复核重点'], 'rows': rows},
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = renderer.render(document, directory, png_scale=.1)
            with fitz.open(result['pdf']) as pdf:
                texts = [''.join(page.get_text().split()) for page in pdf]
            self.assertTrue(any(all(''.join(value.split()) in text for value in insight.values()) for text in texts))
            for row in rows:
                self.assertTrue(any(all(''.join(cell.split()) in text for cell in row) for text in texts))
            self.assertTrue(all(text.count('对应诊断') <= 1 for text in texts))

    def test_quote_container_displays_upstream_amounts_without_defaults(self):
        document = config()
        document['pages'] = [{'layout': 'quotes', 'title': '本次费用', 'headers': ['服务', '金额'],
                              'rows': [['客户指定服务范围', '¥8,600.00'], ['写作', '客户提供定稿，不收费']]}]
        with tempfile.TemporaryDirectory() as directory:
            result = renderer.render(document, directory, png_scale=.1)
            with fitz.open(result['pdf']) as pdf:
                text = ''.join(page.get_text() for page in pdf)
                self.assertIn('8,600.00', text)
                self.assertNotIn('12,000', text)

    def test_output_and_logo_paths_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = renderer.render(config(), root / 'original', png_scale=.1)
            raw = Path(result['pdf']).read_bytes()
            with self.assertRaises(FileExistsError): renderer.render(config(), root / 'original', png_scale=.1)
            self.assertEqual(Path(result['pdf']).read_bytes(), raw)
            with self.assertRaises(ValueError): renderer.render(config(), root / 'badname', pdf_name='../outside.pdf')
            for value in ['../escape.png', 'https://example.com/logo.png']:
                document = copy.deepcopy(config()); document['theme']['logo'] = value
                with self.assertRaises(ValueError): renderer.render(document, root / 'badlogo', asset_root=root)
            self.assertFalse((root / 'badlogo').exists())


if __name__ == '__main__':
    unittest.main()
