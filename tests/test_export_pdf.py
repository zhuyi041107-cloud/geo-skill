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
        entry = {'title': '业务选择缺口', 'detail': '品牌可以被识别，但交付范围与维护责任未进入选择理由。应以真实服务边界和可公开案例承接客户需求，降低初筛的信息不确定性。',
                 'evidence_ref': ['EV-internal-001', 'Q001', r'C:\private\source.json']}
        report = {'template_profile': profile}
        for kind in ('diagnosis', 'execution'):
            doc = {'summary': '品牌识别已有基础，客户决策信息需围绕适用条件与服务责任展开。', 'sections': []}
            for spec in export_pdf.template_contract(profile, kind):
                if spec['source'] == 'diagnosis':
                    continue
                section = {'key': spec['key'], 'title': spec['title'], 'paragraphs': [copy.deepcopy(entry)], 'tables': []}
                if profile == 'platform' and kind == 'execution' and spec['key'] == 'budget':
                    section['quote_card'] = {'name': '建议媒体投放方案', 'focus': '优先解释服务责任', 'suitability': '适用需要核对上线与维护分工的团队'}
                for definition in spec['tables']:
                    if definition['source'] != 'plan':
                        section['tables'].append({'id': definition['id'], 'columns': definition['columns'], 'rows': [['演示业务说明' for _ in definition['columns']]]})
                doc['sections'].append(section)
            report[kind] = doc
        sources = []
        for section in report['diagnosis']['sections']:
            for matrix in section['tables']:
                if section['key'] == 'priority_actions' and matrix['id'] == 'actions':
                    matrix['rows'][0][1] = '澄清服务责任'
                    sources.append('澄清服务责任')
                elif section['key'] == 'competitive_tags' and matrix['id'] == 'proposed_tags':
                    matrix['rows'][0][0] = '可核验的知识服务'
                    sources.append('可核验的知识服务')
        plan['logic_links'] = [{'diagnosis_item': item, 'basis': '客户服务范围与现有内容缺口', 'choice_reason': '按服务责任判断是否适配', 'content_ids': ['C001'],
                                'media_role': '技术媒体解释可核验的服务边界', 'stage': '基础建设', 'check_date': '2027-01-20'} for item in sources]
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
                    self.assertIn('演示平台A端口' if profile == 'platform' else '拟发标题', text.replace('\n', ''))
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
        self.assertEqual(schedule[0][2], '技术媒体')
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

    def test_report_header_does_not_inject_collection_scope_or_example_notice(self):
        analysis, plan, report = self.fixture()
        analysis['report_scope']['platforms'] = ['仅作内部采集范围的平台']
        analysis['counts']['completed'] = 987654
        report['_example_notice'] = '本轮采样说明和虚构声明只供内部使用，不能渲染。'
        for kind in ('diagnosis', 'execution'):
            _, text = self.pdf_text(kind, analysis, plan, report)
            self.assertIn('报告日期：2026-11-10', text)
            for private_meta in ('本轮观察', '条回答', '987654', '仅作内部采集范围的平台', '采样说明和虚构声明'):
                self.assertNotIn(private_meta, text)

    def test_collection_and_authoring_meta_prose_is_rejected_instead_of_silently_deleted(self):
        examples = [
            '本轮以豆包网页端联网的十条回答为观察基础。品牌已经被识别。',
            '本报告基于12份问答样本进行诊断。',
            '观察范围：豆包与其他平台。',
            '样本数量有限，暂不判断推荐表现。',
            '本轮仅覆盖豆包，其他平台尚未回传。',
            '按问题意图分别统计，分母只用已判样本。',
            '这份清单不会成为下一轮人工采样任务。',
            '用同一批问题与网页端条件重新采集并统计。',
            '信源矩阵按原模板的四类承载角色整理。',
            '这些题用于展示怎样把问句变成业务判断。',
            '把两个客群合成一个提及率会掩盖真正的问题。',
            '通用核验题本来就不该强求点名品牌。',
        ]
        for value in examples:
            with self.subTest(value=value):
                analysis, plan, report = self.fixture()
                report['diagnosis']['summary'] = value
                with self.assertRaisesRegex(ValueError, '改成品牌具体情况'):
                    export_pdf.build_pdf('diagnosis', analysis, plan, report)
        analysis, plan, report = self.fixture()
        report['diagnosis']['sections'][1]['tables'][0]['rows'][0][1] = examples[0]
        with self.assertRaisesRegex(ValueError, '改成品牌具体情况'):
            export_pdf.build_pdf('diagnosis', analysis, plan, report)

    def test_local_business_uncertainty_and_risks_remain_in_customer_body(self):
        analysis, plan, report = self.fixture()
        finding = '品牌运营主体存在两种说法，许可证与收费规则尚未核验。官网未列明维护责任，可能增加企业采购沟通成本；应先核对主体关系与合同范围。'
        report['diagnosis']['summary'] = finding
        _, text = self.pdf_text('diagnosis', analysis, plan, report)
        self.assertIn('许可证与收费规则尚未核验', text.replace('\n', ''))
        self.assertIn('增加企业采购沟通成本', text.replace('\n', ''))
        self.assertEqual(export_pdf.customer_text('网页端'), '网页端')
        self.assertEqual(export_pdf.customer_text('本轮未出现品牌，官网价格尚未确认。'), '本轮未出现品牌，官网价格尚未确认。')

    def test_logic_links_reject_missing_fabricated_and_mismatched_references(self):
        analysis, plan, report = self.fixture()
        missing = copy.deepcopy(plan); missing['logic_links'].pop()
        with self.assertRaisesRegex(ValueError, '缺少 logic_links 映射'):
            export_pdf.build_pdf('execution', analysis, missing, report)
        fabricated = copy.deepcopy(plan); fabricated['logic_links'][0]['diagnosis_item'] = '诊断没有提出的任务'
        with self.assertRaisesRegex(ValueError, '不在实际诊断'):
            export_pdf.validate_logic_links(fabricated, report)
        invalid = copy.deepcopy(plan); invalid['logic_links'][0]['content_ids'] = ['C999']
        with self.assertRaisesRegex(ValueError, '不存在或未选用的内容'):
            export_pdf.validate_logic_links(invalid, report)
        mismatch = copy.deepcopy(plan)
        mismatch['stages'].append({'name': '后续维护'})
        mismatch['logic_links'][0]['stage'] = '后续维护'
        with self.assertRaisesRegex(ValueError, '不属于声明阶段'):
            export_pdf.validate_logic_links(mismatch, report)

    def test_logic_links_require_active_publication_and_check_after_latest_schedule(self):
        _, plan, report = self.fixture()
        no_placement = copy.deepcopy(plan)
        no_placement['placements'][0]['status'] = '取消'
        with self.assertRaisesRegex(ValueError, '没有有效 placement'):
            export_pdf.validate_logic_links(no_placement, report)
        early = copy.deepcopy(plan)
        early['logic_links'][0]['check_date'] = '2027-01-14'
        with self.assertRaisesRegex(ValueError, '早于内容'):
            export_pdf.validate_logic_links(early, report)
        after_content_before_publication = copy.deepcopy(plan)
        after_content_before_publication['placements'][0]['scheduled_date'] = '2027-01-25'
        with self.assertRaisesRegex(ValueError, '刊发计划日期'):
            export_pdf.validate_logic_links(after_content_before_publication, report)

    def test_logic_links_allow_unpaid_client_action_and_never_render_internal_mapping(self):
        analysis, plan, report = self.fixture()
        _, baseline = self.pdf_text('execution', analysis, plan, report)
        for link in plan['logic_links']:
            link.update(content_ids=[], client_action='客户官网负责人于首周更新责任与收费页面', basis='内部核对依据不应印在报告',
                        choice_reason='内部选择理由映射', media_role='客户自有页面，无付费刊发', check_date='2027-01-05')
        _, text = self.pdf_text('execution', analysis, plan, report)
        self.assertEqual(text, baseline)
        self.assertNotIn('内部核对依据不应印在报告', text)
        del plan['logic_links']
        self.pdf_text('diagnosis', analysis, plan, report)
        with self.assertRaisesRegex(ValueError, '须有 plan.logic_links'):
            export_pdf.build_pdf('execution', analysis, plan, report)

    def test_platform_restores_quote_card_and_two_column_scene_blocks(self):
        analysis, plan, report = self.fixture()
        for section in report['execution']['sections']:
            section['paragraphs'] = []
        _, text = self.pdf_text('execution', analysis, plan, report)
        self.assertIn('¥960.00', text)
        self.assertIn('建议媒体投放方案', text)
        self.assertIn('演示平台A端口', text.replace('\n', ''))
        self.assertNotIn('承载选题', text)
        self.assertNotIn('阶段合计', text)
        self.assertNotIn('自然季度', text)
        scenes = next(s for s in export_pdf.template_contract('platform', 'execution') if s['key'] == 'target_scenes')
        self.assertEqual(len(scenes['tables']), 3)
        self.assertTrue(all(len(t['columns']) == 2 and t['headerless'] for t in scenes['tables']))
        budget = next(s for s in report['execution']['sections'] if s['key'] == 'budget')
        del budget['quote_card']['focus']
        with self.assertRaisesRegex(ValueError, 'quote_card'):
            export_pdf.build_pdf('execution', analysis, plan, report)

    def test_original_column_proportions_and_headerless_rows(self):
        export_pdf.register_fonts()
        st = export_pdf.styles()
        source = export_pdf.table(['信源层级', '覆盖状态', '覆盖质量', '引用'], [['客户自有来源', '有', '中', '部分']], None, st, 'source_layers')
        self.assertAlmostEqual(source._argW[0] / export_pdf.WIDTH, .5022)
        note = export_pdf.table(['事项', '边界'], [['权限核验', '按角色核对']], None, st, 'fact_boundaries')
        self.assertLess(note._argW[0] / export_pdf.WIDTH, .12)
        scene = export_pdf.table(['场景', '问句'], [['平台初筛', '如何选择知识平台']], None, st, 'target_scenes', headerless=True)
        self.assertEqual(len(scene._cellvalues), 1)
        self.assertEqual(scene.repeatRows, 0)
        self.assertEqual(scene._cellvalues[0][0].getPlainText(), '平台初筛')

    def test_stage_weekly_rate_is_compact_and_includes_idle_weeks(self):
        analysis, plan, _ = self.fixture()
        self.assertEqual(export_pdf.automatic_rows('stage_plan', analysis, plan)[0][3], '每周1篇')
        content = copy.deepcopy(plan['contents'][0])
        content.update(content_id='C002', scheduled_date='2027-01-29')
        placement = copy.deepcopy(plan['placements'][0])
        placement.update(placement_id='P002', content_id='C002', scheduled_date='2027-01-29')
        plan['contents'].append(content)
        plan['placements'].append(placement)
        self.assertEqual(export_pdf.automatic_rows('stage_plan', analysis, plan)[0][3], '每周0-1篇')


if __name__ == '__main__':
    unittest.main()
