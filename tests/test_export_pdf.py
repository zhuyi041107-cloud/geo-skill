import copy
from io import BytesIO
import sys
from pathlib import Path
import unittest

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1] / '.codebuddy/skills/ruanwenjie-geo'
sys.path.insert(0, str(ROOT / 'scripts'))
import export_pdf
from geo_data import calculate_budget


class ExportPdfTests(unittest.TestCase):
    def fixture(self, profile='platform'):
        actual = {'platform': '演示平台A', 'mode': '网页端', 'online': '是', 'round': 1}
        project = {'project_id': 'PDF-TEST', 'client_name': '测试企业（虚构）', 'brand_names': ['测试品牌'], 'currency': 'CNY', 'budget_limit': '1000.00',
                   'start_date': '2027-01-01', 'end_date': '2027-01-31', 'contexts': [actual, {'platform': '未回传平台B'}],
                   'questions': [{'question_id': 'Q001', 'text': '企业知识库怎样验收？'}]}
        plan = {'stages': [{'name': '基础建设', 'objective': '说明服务适用边界', 'deliverables': '事实页及媒体稿完成', 'effect_target': '观察业务描述与事实是否一致'}],
                'contents': [{'content_id': 'C001', 'title': '企业知识库实施验收清单', 'stage': '基础建设', 'scheduled_date': '2027-01-15', 'status': '已选',
                              'source_layer': '基础事实', 'content_form': '专业说明', 'platform': '演示平台A', 'observation_port': '网页端', 'question_ids': ['Q001'],
                              'key_facts': '以演示服务范围与验收清单为边界，不承诺自动解决全部问题', 'checkpoint': '第4周观察'}],
                'placements': [{'placement_id': 'P001', 'content_id': 'C001', 'media_id': 'M001', 'media_name': '示例技术观察网（虚构）', 'media_type': '技术媒体', 'status': '已选', 'unit_price': '37.00',
                                'client_unit_price': '480.00', 'quantity': 2, 'scheduled_date': '2027-01-15', 'price_tier': '内部成本档位', 'price_basis': '市场参考价', 'quotation_date': '2026-10-28'}], 'fees': []}
        analysis = {'schema_version': 1, 'project': project, 'sampled_contexts': [actual], 'report_scope': {'platforms': [actual['platform']], 'report_date': '2026-11-10'},
                    'counts': {'completed': 2, 'valid': 2}, 'groups': [{**actual, 'valid': 2, 'completed': 2}], 'budget': calculate_budget(project, plan)}
        entry = {'title': '业务选择缺口', 'detail': '本轮品牌可以被识别，但交付范围与维护责任未进入选择理由。应以真实服务边界和可公开案例承接客户需求，降低初筛的信息不确定性。',
                 'evidence_ref': ['EV-internal-001', 'Q001', r'C:\private\source.json']}
        report = {'template_profile': profile}
        for kind in ('diagnosis', 'execution'):
            doc = {'summary': '虚构测试资料：品牌识别已有基础，客户决策信息需围绕适用条件与服务责任展开。', 'sections': []}
            for spec in export_pdf.template_contract(profile, kind):
                if spec['source'] == 'diagnosis':
                    continue
                section = {'key': spec['key'], 'title': spec['title'], 'paragraphs': [copy.deepcopy(entry)], 'tables': []}
                for definition in spec['tables']:
                    if definition['source'] != 'plan':
                        section['tables'].append({'id': definition['id'], 'columns': definition['columns'], 'rows': [['演示业务说明' for _ in definition['columns']]]})
                doc['sections'].append(section)
            report[kind] = doc
        return analysis, plan, report

    def pdf_text(self, kind, analysis, plan, report):
        reader = PdfReader(BytesIO(export_pdf.build_pdf(kind, analysis, plan, report)))
        return reader, ''.join(p.extract_text() for p in reader.pages)

    def test_both_profiles_preserve_required_matrices_numbers_and_privacy(self):
        for profile in ('platform', 'service'):
            analysis, plan, report = self.fixture(profile)
            for kind in ('diagnosis', 'execution'):
                reader, text = self.pdf_text(kind, analysis, plan, report)
                self.assertIn('测试品牌', text)
                self.assertNotIn('未回传平台B', text)
                for private in ('Q001', 'C001', 'P001', 'EV-internal', 'private', 'normalize', '采样范围与方法', '内部成本档位', '¥37.00'):
                    self.assertNotIn(private, text)
                for spec in export_pdf.template_contract(profile, kind):
                    self.assertIn(spec['title'].replace(' ', ''), text.replace('\n', '').replace(' ', ''))
                if kind == 'execution':
                    self.assertIn('¥960.00', text)
                    self.assertIn('2026-10-28', text)
                    self.assertIn('市场参考价', text)
                    self.assertIn('2次刊发', text.replace('\n', ''))
                    self.assertEqual(text.count('报价口径'), 1)
                    self.assertIn('观察端口' if profile == 'platform' else '拟发标题', text)
                embedded = []
                for page in reader.pages:
                    for item in page['/Resources']['/Font'].values():
                        descriptor = item.get_object().get('/FontDescriptor')
                        if descriptor:
                            embedded.append('/FontFile2' in descriptor.get_object())
                self.assertIn(True, embedded)
                self.assertTrue(all(len(p.extract_text()) > 50 for p in reader.pages))

    def test_required_section_matrix_and_plan_columns_cannot_silently_disappear(self):
        for profile in ('platform', 'service'):
            analysis, plan, report = self.fixture(profile)
            incomplete = copy.deepcopy(report)
            incomplete['diagnosis']['sections'].pop()
            with self.assertRaisesRegex(ValueError, '缺少必需章节'):
                export_pdf.build_pdf('diagnosis', analysis, plan, incomplete)
            incomplete = copy.deepcopy(report)
            incomplete['diagnosis']['sections'][0]['tables'][0]['rows'] = []
            with self.assertRaisesRegex(ValueError, '不能为空'):
                export_pdf.build_pdf('diagnosis', analysis, plan, incomplete)
            incomplete = copy.deepcopy(plan)
            del incomplete['contents'][0]['observation_port']
            analysis['budget'] = calculate_budget(analysis['project'], incomplete)
            with self.assertRaisesRegex(ValueError, 'observation_port'):
                export_pdf.build_pdf('execution', analysis, incomplete, report)

    def test_reject_stale_budget_small_default_package_and_internal_prose(self):
        analysis, plan, report = self.fixture()
        changed = copy.deepcopy(plan); changed['placements'][0]['client_unit_price'] = '999.00'
        with self.assertRaisesRegex(ValueError, '预算不一致'):
            export_pdf.build_pdf('execution', analysis, changed, report)
        analysis['project']['budget_limit'] = None
        analysis['budget'] = calculate_budget(analysis['project'], plan)
        with self.assertRaisesRegex(ValueError, '90%'):
            export_pdf.build_pdf('execution', analysis, plan, report)
        analysis, plan, report = self.fixture()
        report['diagnosis']['sections'][0]['paragraphs'][0]['detail'] = '请参见Q001以及本机处理目录。'
        with self.assertRaisesRegex(ValueError, '内部编号'):
            export_pdf.build_pdf('diagnosis', analysis, plan, report)
        for section in report['execution']['sections']:
            if section['key'] == 'rollout':
                section['tables'] = [{'id': 'stage_plan', 'rows': [['手改数量']]}]
        with self.assertRaisesRegex(ValueError, '不可手填'):
            export_pdf.build_pdf('execution', analysis, plan, report)

    def test_long_paragraph_and_complete_schedule_survive_page_splits(self):
        analysis, plan, report = self.fixture()
        report['diagnosis']['sections'][-1]['paragraphs'][0]['detail'] = '服务边界应由真实交付事实支撑，避免用笼统功能代替客户的选择理由。' * 200 + '末尾核验内容仍完整。'
        reader, text = self.pdf_text('diagnosis', analysis, plan, report)
        self.assertIn('末尾核验内容仍完整', text)
        for i in range(2, 22):
            c = copy.deepcopy(plan['contents'][0]); c.update(content_id=f'C{i:03d}', title=f'完整保留的第{i}篇专题')
            p = copy.deepcopy(plan['placements'][0]); p.update(placement_id=f'P{i:03d}', content_id=c['content_id'])
            plan['contents'].append(c); plan['placements'].append(p)
        analysis['project']['budget_limit'] = '30000.00'
        analysis['budget'] = calculate_budget(analysis['project'], plan)
        reader, text = self.pdf_text('execution', analysis, plan, report)
        self.assertIn('完整保留的第21篇专题', text.replace('\n', ''))
        self.assertGreater(text.count('拟发标题'), 1)
        self.assertTrue(all(len(p.extract_text()) > 50 for p in reader.pages))

    def test_decimal_integer_quantity_and_service_media_remain_same_source(self):
        analysis, plan, report = self.fixture('service')
        plan['placements'][0]['quantity'] = '2.0'
        analysis['budget'] = calculate_budget(analysis['project'], plan)
        _, text = self.pdf_text('execution', analysis, plan, report)
        self.assertIn('¥960.00', text)
        schedule = export_pdf.automatic_rows('article_schedule', analysis, plan)
        self.assertEqual(schedule[0][2], '示例技术观察网（虚构）')
        rows = export_pdf.automatic_rows('content_volume', analysis, plan)
        self.assertEqual(rows[0][1:3], ['1', '2'])
        self.assertIn('企业知识库怎样验收', rows[0][-1])
        self.assertNotIn("['", rows[0][-1])

    def test_annual_plan_requires_actual_content_and_placements_in_every_quarter(self):
        analysis, plan, report = self.fixture()
        analysis['project']['end_date'] = '2027-12-31'
        analysis['budget'] = calculate_budget(analysis['project'], plan)
        with self.assertRaisesRegex(ValueError, '年度计划.*2027Q2'):
            export_pdf.build_pdf('execution', analysis, plan, report)

    def test_service_dimension_table_has_exactly_five_visible_columns(self):
        export_pdf.register_fonts()
        columns = next(s for s in export_pdf.template_contract('service', 'diagnosis') if s['key'] == 'business_dimensions')['tables'][0]['columns']
        matrix = export_pdf.table(columns, [['业务具体说明'] * len(columns)], None, export_pdf.styles(), table_id='dimensions')
        self.assertEqual(len(matrix._argW), 5)
        self.assertAlmostEqual(sum(matrix._argW), export_pdf.WIDTH)
        with self.assertRaisesRegex(ValueError, '列宽、表头'):
            export_pdf.table(columns, [['说明'] * 5], [100] * 6, export_pdf.styles())
        for table_id, columns in [('actions', ['序号', '执行方向', '优先级', '详细说明']), ('risks', ['编号', '类型', '描述'])]:
            matrix = export_pdf.table(columns, [['本案业务说明'] * len(columns)], None, export_pdf.styles(), table_id=table_id)
            self.assertGreater(matrix._argW[-1], export_pdf.WIDTH / 2)
            self.assertLess(matrix._argW[0], export_pdf.WIDTH / 10)


if __name__ == '__main__':
    unittest.main()
