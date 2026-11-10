import copy
from io import BytesIO
import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1] / '.codebuddy/skills/ruanwenjie-geo'
sys.path.insert(0, str(ROOT / 'scripts'))
import export_pdf
from geo_data import calculate_budget


class ExportPdfTests(unittest.TestCase):
    def fixture(self, profile='platform'):
        project = {'project_id': 'PDF-TEST', 'client_name': '测试企业（虚构）', 'brand_names': ['测试品牌'], 'industry': '企业知识服务', 'services': ['知识管理'], 'currency': 'CNY', 'budget_limit': '1000.00',
                   'start_date': '2027-01-01', 'end_date': '2027-01-31', 'questions': [{'question_id': 'Q001', 'text': '企业知识库怎样验收？'}]}
        plan = {'stages': [{'name': '基础建设', 'objective': '说明服务适用边界', 'deliverables': '事实页及媒体稿完成', 'effect_target': '观察业务描述与事实是否一致'}],
                'contents': [{'content_id': 'C001', 'title': '企业知识库实施验收清单', 'stage': '基础建设', 'scheduled_date': '2027-01-15', 'status': '已选',
                              'source_layer': '基础事实', 'content_form': '专业说明', 'platform': '演示平台A', 'observation_port': '网页端', 'question_ids': ['Q001'],
                              'key_facts': '以服务范围与验收清单为边界，不承诺自动解决全部问题', 'checkpoint': '第4周观察'}],
                'placements': [{'placement_id': 'P001', 'content_id': 'C001', 'media_id': 'M001', 'media_name': '示例技术观察网（虚构）', 'media_type': '技术媒体', 'status': '已选', 'unit_price': '37.00',
                                'client_unit_price': '480.00', 'quantity': 2, 'scheduled_date': '2027-01-15', 'price_tier': '内部成本档位', 'price_basis': '市场参考价', 'quotation_date': '2026-10-28'}], 'fees': []}
        analysis = {'schema_version': 1, 'project': project, 'sampled_contexts': [{'platform': '演示平台A'}], 'report_scope': {'report_date': '2026-11-10'}, 'budget': calculate_budget(project, plan)}
        report = {'template_profile': profile}
        for kind in ('diagnosis', 'execution'):
            doc = {'summary': '品牌可以被识别，客户选择所需的责任与服务条件仍需具体化。', 'sections': [], 'fields': {}}
            for spec in export_pdf.template_contract(profile, kind):
                if spec['source'] == 'diagnosis': continue
                section = {'key': spec['key'], 'title': spec['title'], 'paragraphs': [{'title': '', 'detail': '客户需要核对服务责任、权限边界与可公开事实。'}], 'tables': []}
                if profile == 'platform' and kind == 'execution' and spec['key'] == 'budget':
                    section['quote_card'] = {'name': '建议媒体投放方案', 'focus': '解释服务责任', 'suitability': '需要确认上线与维护分工的团队'}
                for definition in spec['tables']:
                    if definition['source'] == 'plan': continue
                    ident = definition['id']; rows = [['本客户具体事实' for _ in definition['columns']]]
                    if ident == 'decision_path': rows = [[name, '企业知识库怎样验收？', '条件待具体化', '影响初筛判断'] for name in ['产生需求','建立品牌意向','评估合作细节','比较替代方案']]
                    if ident == 'response_layers': rows = [[name, '企业知识库怎样验收？', '服务责任需要公开说明', '待具体化', '需要核对交付边界'] for name in ['认知层','推荐层','决策层','定义层']]
                    if ident == 'recognition': rows = [['品牌识别','可以','可说明业务'],['业务表述','可以','可识别服务范围'],['品类推荐','暂未进入','候选理由不足']]
                    if ident == 'scene_matrix': rows = [['平台初筛','未出现','已出现']]
                    if ident == 'scene_details': rows = [['平台初筛','企业知识库怎样验收？','未出现','已出现','需要补充服务责任与可公开证据']]
                    if ident == 'source_layers': rows = [['客户自有来源','有','待核实','待核实']]
                    if ident == 'actions': rows[0][1] = '澄清服务责任'
                    if ident == 'proposed_tags': rows[0][0] = '可核验的知识服务'
                    section['tables'].append({'id': ident, 'columns': definition['columns'], 'rows': rows})
                doc['sections'].append(section)
            report[kind] = doc
        report['diagnosis']['priority_cards'] = [[name,'高','以已有事实支撑客户选择'] for name in ['责任说明','权限核验','出处展示','维护边界']]
        items = ['澄清服务责任'] + (['可核验的知识服务'] if profile == 'platform' else [])
        plan['logic_links'] = [{'diagnosis_item': item,'basis':'客户服务范围与内容缺口','choice_reason':'按责任判断适配','content_ids':['C001'],'media_role':'技术媒体解释服务边界','stage':'基础建设','check_date':'2027-01-20'} for item in items]
        for kind in ('diagnosis','execution'):
            context = export_pdf.template_context(kind, analysis, plan, report)
            soup = BeautifulSoup((ROOT / f'templates/{profile}-{kind}.html').read_text(encoding='utf-8'),'html.parser')
            for node in soup.select('[data-slot]'):
                if node['data-slot'] not in context['slots']:
                    report[kind]['fields'][node['data-slot']] = '适用条件与执行责任需要按事实说明'
            for node in soup.select('[data-paragraphs][data-required]'):
                report[kind].setdefault('blocks',{})[node['data-paragraphs']] = [{'title':'','detail':'仅按已确认的服务事实和费用范围执行。'}]
        return analysis, plan, report

    def html_text(self, kind, analysis, plan, report):
        soup = BeautifulSoup(export_pdf.build_html(kind, analysis, plan, report),'html.parser')
        return soup, soup.get_text(' ',strip=True)

    def test_fixed_dom_all_profiles_and_data_privacy(self):
        for profile in ('platform','service'):
            analysis, plan, report = self.fixture(profile)
            for kind in ('diagnosis','execution'):
                soup, text = self.html_text(kind, analysis, plan, report)
                self.assertIn('测试品牌',text)
                self.assertFalse(soup.find('script'))
                self.assertFalse(soup.find('template'))
                for value in ('C001','Q001','P001','内部成本档位','¥37.00','{{cell','normalize'):
                    self.assertNotIn(value,text)
                self.assertIn('Microsoft YaHei',soup.style.get_text())
                self.assertIn('700',soup.style.get_text())
                if kind == 'execution': self.assertIn('企业知识库实施验收清单',text)

    def test_original_shapes_are_fixed_not_uniform_tables(self):
        a,p,r = self.fixture('service');soup,_ = self.html_text('diagnosis',a,p,r)
        card = soup.select_one('[data-table="dimensions"] .dimension-card')
        self.assertEqual(len(card.select('tr')),4)
        a,p,r = self.fixture('platform');soup,_ = self.html_text('execution',a,p,r)
        self.assertEqual(len(soup.select('[data-table="quote_cards"] > *')),1)
        for ident in ('target_scenes','platform_scenes','differentiation'):
            self.assertEqual(len(soup.select_one(f'[data-table="{ident}"] tr').select('td')),2)
        self.assertFalse(soup.select('[data-table="selected_media"], [data-table="quarterly_budget"]'))

    def test_long_status_payloads_are_rejected_not_silently_truncated(self):
        for ident,index,payload in [('scene_matrix',1,'平台甲、平台乙、平台丙'),('source_layers',1,'已有官网和六篇文章，但引用关系仍不明确')]:
            a,p,r = self.fixture()
            matrix = next(t for s in r['diagnosis']['sections'] for t in s['tables'] if t['id']==ident)
            matrix['rows'][0][index] = payload
            with self.assertRaisesRegex(ValueError,'状态格'): export_pdf.build_html('diagnosis',a,p,r)

    def test_data_cannot_inject_markup_or_override_amounts(self):
        a,p,r = self.fixture();r['diagnosis']['summary'] = '客户文字 <script>window.location="https://example.com"</script> 仍是纯文字。'
        soup,text = self.html_text('diagnosis',a,p,r)
        self.assertIsNone(soup.find('script'));self.assertIn('<script>',text)
        r['execution']['fields']['budget_total'] = '¥2.00'
        with self.assertRaisesRegex(ValueError,'不能覆盖'): export_pdf.build_html('execution',a,p,r)

    def test_derived_schedule_totals_and_required_text_cannot_be_overwritten_or_empty(self):
        a,p,r = self.fixture()
        r['execution']['fields']['schedule_total'] = '合计999篇999次'
        with self.assertRaisesRegex(ValueError,'不能覆盖'): export_pdf.build_html('execution',a,p,r)
        del r['execution']['fields']['schedule_total']
        r['execution']['fields']['journey_subtitle'] = ''
        with self.assertRaisesRegex(ValueError,'必填文字位不能为空'): export_pdf.build_html('execution',a,p,r)
        r['execution']['fields']['journey_subtitle'] = '从事实条件走向客户选择'
        r['execution']['blocks']['maintenance_redlines'] = []
        with self.assertRaisesRegex(ValueError,'只有标题的空段'): export_pdf.build_html('execution',a,p,r)

    def test_other_charged_fees_are_visible_and_quote_card_has_no_duplicate_currency(self):
        a,p,r = self.fixture()
        p['fees'] = [{'fee_id':'F001','category':'撰稿','description':'独立撰稿服务','amount':'20','client_amount':'40','stage':'基础建设','status':'已选'}]
        a['budget'] = calculate_budget(a['project'],p)
        soup,text = self.html_text('execution',a,p,r)
        self.assertIn('独立撰稿服务',text)
        self.assertIn('¥40.00',text)
        self.assertEqual(soup.select_one('[data-table="quote_cards"] tr').select('td')[1].get_text(),'1,000')

    def test_template_tamper_and_existing_output_fail_before_browser(self):
        a,p,r = self.fixture()
        with patch.object(export_pdf.hashlib,'sha256') as digest:
            digest.return_value.hexdigest.return_value = 'changed'
            with self.assertRaisesRegex(ValueError,'模板已被改动'): export_pdf.build_html('diagnosis',a,p,r)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'existing.pdf';path.write_bytes(b'user original')
            with patch.object(export_pdf,'print_html') as printer:
                with self.assertRaises(FileExistsError): export_pdf.export_pdf('diagnosis',a,p,r,path)
                printer.assert_not_called()
            self.assertEqual(path.read_bytes(),b'user original')

    @unittest.skipUnless(sys.platform == 'win32' and export_pdf.find_browser(), '需要本机Chromium和原微软雅黑')
    def test_browser_prints_four_fixed_templates_with_real_bold_and_pages(self):
        for profile in ('platform','service'):
            a,p,r = self.fixture(profile)
            for kind in ('diagnosis','execution'):
                reader=PdfReader(BytesIO(export_pdf.build_pdf(kind,a,p,r)))
                self.assertIn('Skia',reader.metadata.get('/Producer',''))
                self.assertGreaterEqual(len(reader.pages),3)
                body=''.join(page.extract_text() for page in reader.pages)
                self.assertIn('测试品牌',body)
                self.assertNotIn('{{',body)
                self.assertTrue(all(page.extract_text().strip() for page in reader.pages))

    def test_required_section_matrix_and_plan_columns_cannot_silently_disappear(self):
        for profile in ('platform', 'service'):
            analysis, plan, report = self.fixture(profile)
            incomplete = copy.deepcopy(report)
            incomplete['diagnosis']['sections'].pop()
            with self.assertRaisesRegex(ValueError, '缺少必需章节'):
                export_pdf.build_html('diagnosis', analysis, plan, incomplete)
            incomplete = copy.deepcopy(report)
            incomplete['diagnosis']['sections'][0]['tables'][0]['rows'] = []
            with self.assertRaisesRegex(ValueError, '不能为空'):
                export_pdf.build_html('diagnosis', analysis, plan, incomplete)
            incomplete = copy.deepcopy(plan)
            del incomplete['contents'][0]['observation_port']
            analysis['budget'] = calculate_budget(analysis['project'], incomplete)
            with self.assertRaisesRegex(ValueError, 'observation_port'):
                export_pdf.build_html('execution', analysis, incomplete, report)

    def test_reject_stale_budget_small_default_package_and_internal_prose(self):
        analysis, plan, report = self.fixture()
        changed = copy.deepcopy(plan); changed['placements'][0]['client_unit_price'] = '999.00'
        with self.assertRaisesRegex(ValueError, '预算不一致'):
            export_pdf.build_html('execution', analysis, changed, report)
        analysis['project']['budget_limit'] = None
        analysis['budget'] = calculate_budget(analysis['project'], plan)
        with self.assertRaisesRegex(ValueError, '90%'):
            export_pdf.build_html('execution', analysis, plan, report)
        analysis, plan, report = self.fixture()
        report['diagnosis']['sections'][0]['paragraphs'][0]['detail'] = '请参见Q001以及本机处理目录。'
        with self.assertRaisesRegex(ValueError, '内部编号'):
            export_pdf.build_html('diagnosis', analysis, plan, report)
        for section in report['execution']['sections']:
            if section['key'] == 'rollout':
                section['tables'] = [{'id': 'stage_plan', 'rows': [['手改数量']]}]
        with self.assertRaisesRegex(ValueError, '不可手填'):
            export_pdf.build_html('execution', analysis, plan, report)

    def test_annual_plan_requires_actual_content_and_placements_in_every_quarter(self):
        analysis, plan, report = self.fixture()
        analysis['project']['end_date'] = '2027-12-31'
        analysis['budget'] = calculate_budget(analysis['project'], plan)
        with self.assertRaisesRegex(ValueError, '年度计划.*2027Q2'):
            export_pdf.build_html('execution', analysis, plan, report)

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
                    export_pdf.build_html('diagnosis', analysis, plan, report)
        analysis, plan, report = self.fixture()
        report['diagnosis']['sections'][1]['tables'][0]['rows'][0][1] = examples[0]
        with self.assertRaisesRegex(ValueError, '改成品牌具体情况'):
            export_pdf.build_html('diagnosis', analysis, plan, report)

    def test_logic_links_reject_missing_fabricated_and_mismatched_references(self):
        analysis, plan, report = self.fixture()
        missing = copy.deepcopy(plan); missing['logic_links'].pop()
        with self.assertRaisesRegex(ValueError, '缺少 logic_links 映射'):
            export_pdf.build_html('execution', analysis, missing, report)
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

    def test_logic_links_allow_unpaid_client_action_and_never_render_internal_mapping(self):
        analysis, plan, report = self.fixture()
        _, baseline = self.html_text('execution', analysis, plan, report)
        for link in plan['logic_links']:
            link.update(content_ids=[], client_action='客户官网负责人于首周更新责任与收费页面', basis='内部核对依据不应印在报告',
                        choice_reason='内部选择理由映射', media_role='客户自有页面，无付费刊发', check_date='2027-01-05')
        _, text = self.html_text('execution', analysis, plan, report)
        self.assertEqual(text, baseline)
        self.assertNotIn('内部核对依据不应印在报告', text)
        del plan['logic_links']
        self.html_text('diagnosis', analysis, plan, report)
        with self.assertRaisesRegex(ValueError, '须有 plan.logic_links'):
            export_pdf.build_html('execution', analysis, plan, report)

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

if __name__ == "__main__":
    unittest.main()
