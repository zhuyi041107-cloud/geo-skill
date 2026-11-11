import copy
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import fitz

ROOT = Path(__file__).resolve().parents[1] / '.codebuddy/skills/ruanwenjie-geo'
sys.path.insert(0, str(ROOT / 'scripts'))
import export_pdf
import render_geo_diagnosis as renderer
import check_client_report
from geo_data import calculate_budget


class ExportPdfTests(unittest.TestCase):
    def fixture(self):
        return tuple(export_pdf.load_json(ROOT / ('references/' + name + '.example.json')) for name in ('report', 'project', 'plan'))

    def prepare(self, report, project, plan):
        return export_pdf.prepare_document('execution', report, project, plan)

    def test_two_fixed_pdfs_show_three_roles_both_quotes_and_no_internal_data(self):
        report, project, plan = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / '正式输出'
            result = export_pdf.export_reports(report, output, project=project, plan=plan, png_scale=.2)
            for kind, count in [('diagnosis', 8), ('execution', 9)]:
                with fitz.open(result[kind]['pdf']) as doc:
                    self.assertEqual(len(doc), count)
                    self.assertTrue(all(p.rect == fitz.Rect(0, 0, 1200, 675) for p in doc))
                    text = ''.join(p.get_text() for p in doc)
                    self.assertIn('知桥协同', text)
                    for secret in ('C001', 'Q001', 'unit_price', 'media_id', 'DEMO-ZHIQIAO'):
                        self.assertNotIn(secret, text)
                    self.assertEqual(check_client_report.check([(1, text)]), [])
                    if kind == 'execution':
                        for value in ('20,400.00', '28,800.00', '27,600.00', '36,000.00', '权威媒体', '行业媒体', '自媒体'):
                            self.assertIn(value, text)
                review = Path(result[kind]['review_dir'])
                self.assertEqual(len(list(review.glob(kind + '_page_*.png'))), count)
                audit = json.loads(Path(result[kind]['audit']).read_text(encoding='utf-8'))
                self.assertTrue(all(Path(p).is_file() for p in audit['rendered_pages']))
            self.assertEqual(sorted(p.name for p in output.iterdir()), sorted(export_pdf.FILES.values()))

    def test_old_quote_arithmetic_and_stage_allocations_are_exact(self):
        report, project, plan = self.fixture()
        config = self.prepare(report, project, plan)
        self.assertEqual([c['total'] for c in config['pages'][8]['items']], ['¥20,400.00', '¥28,800.00'])
        self.assertEqual([c['quantity'] for c in config['pages'][4]['items']], ['24次', '36次', '12次'])
        self.assertEqual([c['counts'] for c in config['pages'][5]['items']], ['18篇 / 18次发布', '20篇 / 20次发布', '18篇 / 18次发布', '16篇 / 16次发布'])
        self.assertEqual([c['amount'] for c in config['pages'][5]['items']], ['普通¥5,100.00 / 高¥7,200.00', '普通¥5,750.00 / 高¥8,100.00', '普通¥5,100.00 / 高¥7,200.00', '普通¥4,450.00 / 高¥6,300.00'])
        for role, card in zip(export_pdf.ROLES, config['pages'][4]['items']):
            self.assertEqual(card['category'], role)
            self.assertIn('普通：', card['resources'])
            self.assertIn('高权重：', card['resources'])
        self.assertEqual(config['pages'][6]['headers'], ['工作事项', '软文街负责', '贵司配合'])
        self.assertIn('不含该项实际执行', config['pages'][6]['rows'][-1][1])
        self.assertIn('稿件撰写另收费', config['pages'][8]['services'])
        self.assertIn('媒体＋写作总额', config['pages'][8]['writing'])
        self.assertIn('第4、8、12、16周', config['pages'][7]['subtitle'])

    def test_both_real_resource_configurations_and_identical_per_article_role_counts_are_required(self):
        report, project, plan = self.fixture()
        plan['quote_options'] = []
        with self.assertRaisesRegex(ValueError, '两套真实'):
            self.prepare(report, project, plan)
        report, project, plan = self.fixture()
        alternative = plan['quote_options'][0]['placements']
        # Keep total publications equal while changing one article's role.
        alternative[0]['strategy_role'] = '行业媒体'
        alternative[0]['client_unit_price'] = '300.00'
        with self.assertRaisesRegex(ValueError, '每篇各策略类'):
            self.prepare(report, project, plan)
        report, project, plan = self.fixture()
        for normal, higher in zip(plan['placements'], plan['quote_options'][0]['placements']):
            higher.update(media_id=normal['media_id'], media_name=normal['media_name'], source_sheet=normal['source_sheet'])
        with self.assertRaisesRegex(ValueError, '不能只更改价格'):
            self.prepare(report, project, plan)

    def test_strategy_roles_require_explicit_evidence_not_sheet_or_price(self):
        report, project, plan = self.fixture()
        plan['placements'][0]['strategy_role'] = '网络媒体'
        with self.assertRaisesRegex(ValueError, 'strategy_role'):
            self.prepare(report, project, plan)
        report, project, plan = self.fixture()
        plan['placements'][0]['strategy_basis'] = ''
        with self.assertRaisesRegex(ValueError, '角色依据'):
            self.prepare(report, project, plan)

    def test_missing_category_keeps_truthful_zero_card_without_inventing_resources(self):
        report, project, plan = self.fixture()
        for records in (plan['placements'], plan['quote_options'][0]['placements']):
            for p in records:
                if p['strategy_role'] == '自媒体':
                    p['strategy_role'] = '行业媒体'
                    p['strategy_basis'] = '测试配置：已核对其专业内容角色；资源归档字段保持原样。'
        config = self.prepare(report, project, plan)
        empty = config['pages'][4]['items'][2]
        self.assertEqual(empty['quantity'], '0次')
        self.assertIn('本期未配置', empty['resources'])
        self.assertEqual(empty['amount'], '普通¥0.00 / 高¥0.00')

    def test_reference_market_prices_remain_separate_from_customer_rates(self):
        report, project, plan = self.fixture()
        before = [(p['market_price'], copy.deepcopy(p['tier_prices'])) for p in plan['placements']]
        self.prepare(report, project, plan)
        self.assertEqual(before, [(p['market_price'], p['tier_prices']) for p in plan['placements']])
        self.assertTrue(all(p['unit_price'] is None for p in plan['placements']))
        plan['placements'][0]['unit_price'] = '451.00'
        with self.assertRaisesRegex(ValueError, '低于已明确采购成本'):
            self.prepare(report, project, plan)

    def test_customer_rates_currency_and_explicit_hard_ceiling_are_checked(self):
        report, project, plan = self.fixture()
        project['currency'] = 'USD'
        with self.assertRaisesRegex(ValueError, '人民币'):
            self.prepare(report, project, plan)
        project['currency'] = 'CNY'
        plan['placements'][0]['client_unit_price'] = '449.00'
        with self.assertRaisesRegex(ValueError, '约定客户单价'):
            self.prepare(report, project, plan)
        report, project, plan = self.fixture()
        project['budget_limit'] = '28000.00'
        with self.assertRaisesRegex(ValueError, '超出预算上限'):
            self.prepare(report, project, plan)

    def test_intended_budget_does_not_cap_either_actual_quote(self):
        report, project, plan = self.fixture()
        project['budget_target'] = '10000.00'
        project['budget_limit'] = None
        config = self.prepare(report, project, plan)
        self.assertEqual([c['total'] for c in config['pages'][8]['items']], ['¥20,400.00', '¥28,800.00'])

    def test_explicit_ceiling_includes_selected_writing_but_not_client_provided_writing(self):
        report, project, plan = self.fixture()
        project['budget_limit'] = '30000.00'
        with self.assertRaisesRegex(ValueError, '高权重方案媒体与写作总额¥36,000.00超出预算上限¥30,000.00'):
            self.prepare(report, project, plan)
        project['budget_limit'] = '36000.00'
        config = self.prepare(report, project, plan)
        self.assertIn('高权重¥36,000.00', config['pages'][8]['writing'])
        project['budget_limit'] = '30000.00'
        plan['service_scope'].update(writing_mode='client_provided', manual_writing=None)
        config = self.prepare(report, project, plan)
        self.assertEqual(config['pages'][8]['items'][1]['total'], '¥28,800.00')
        self.assertIn('贵司提供定稿', config['pages'][8]['writing'])

    def test_media_fee_floor_uses_real_publications_and_is_checked_for_both_tiers(self):
        _, project, plan = self.fixture()
        for quote_index, rate, quantity in ((0, '200.00', 60), (1, '300.00', 40)):
            chosen = copy.deepcopy(plan)
            item = copy.deepcopy(plan['placements'][0])
            item.update(strategy_role='行业媒体', client_unit_price=rate, quantity=quantity)
            chosen['placements'] = [item]
            budget, _, _ = export_pdf.public_accounting(project, chosen, quote_index)
            self.assertEqual(budget['client']['total'], '12000.00')
            item['quantity'] -= 1
            with self.subTest(quote_index=quote_index), self.assertRaisesRegex(ValueError, '至少12000'):
                export_pdf.public_accounting(project, chosen, quote_index)
        chosen = copy.deepcopy(plan)
        chosen['placements'] = chosen['placements'][:2]
        for item, quantity in zip(chosen['placements'], (29, 30)):
            item.update(strategy_role='行业媒体', client_unit_price='200.00', quantity=quantity)
        budget = calculate_budget(project, chosen)
        self.assertEqual(Decimal(budget['client']['total']) + 100 * budget['content_count'], Decimal('12000'))
        with self.assertRaisesRegex(ValueError, '不得用写作费'):
            export_pdf.public_accounting(project, chosen)

    def test_writing_is_separate_and_old_free_writing_mode_is_rejected(self):
        report, project, plan = self.fixture()
        config = self.prepare(report, project, plan)
        self.assertIn('72篇共¥7,200.00', config['pages'][8]['writing'])
        self.assertIn('普通¥27,600.00；高权重¥36,000.00', config['pages'][8]['writing'])
        self.assertNotIn('AI起草', config['pages'][8]['services'])
        self.assertNotIn('AI起草', config['pages'][8]['subtitle'])
        plan['service_scope']['writing_mode'] = 'ai_assisted'
        with self.assertRaisesRegex(ValueError, '免费写作模式已停用'):
            self.prepare(report, project, plan)
        plan['service_scope']['writing_mode'] = 'separate'
        plan['service_scope']['work_items'][0]['provider'] = '提供选题、AI起草及人工简单修改。'
        with self.assertRaisesRegex(ValueError, '写作服务单列收费'):
            self.prepare(report, project, plan)

    def test_service_scope_is_required_and_both_public_pages_share_it(self):
        report, project, plan = self.fixture()
        del plan['service_scope']
        with self.assertRaisesRegex(ValueError, 'service_scope'):
            self.prepare(report, project, plan)
        report, project, plan = self.fixture()
        plan['service_scope']['work_items'][0]['included'] = False
        with self.assertRaisesRegex(ValueError, '已含服务'):
            self.prepare(report, project, plan)
        report, project, plan = self.fixture()
        del plan['service_scope']['review_schedule']
        with self.assertRaisesRegex(ValueError, '具体节点'):
            self.prepare(report, project, plan)

    def test_customer_provided_writing_has_no_ghostwriting_or_manual_upsell(self):
        report, project, plan = self.fixture()
        scope = plan['service_scope']
        scope.update(writing_mode='client_provided', manual_writing=None)
        scope['work_items'][0]['provider'] = '提供选题大纲与素材结构，协助发布准备。'
        scope['work_items'][0]['client'] = '贵司负责稿件撰写、专业审核、定稿及公开授权。'
        report['execution']['pages'][8]['subtitle'] = 'AI起草及人工简单修改已含。'
        config = self.prepare(report, project, plan)
        self.assertIn('贵司供稿', config['pages'][8]['services'])
        self.assertNotIn('7,200', config['pages'][8]['writing'])
        self.assertNotIn('AI起草', config['pages'][8]['services'])
        self.assertNotIn('AI起草', config['pages'][8]['subtitle'])
        self.assertIn('贵司供稿', config['pages'][8]['subtitle'])
        scope['manual_writing'] = {'unit_price': '100.00', 'original_unit_price': '200.00'}
        with self.assertRaisesRegex(ValueError, '不承接人工撰写'):
            self.prepare(report, project, plan)

    def test_extra_active_fees_are_rejected_before_fixed_quote_rendering(self):
        report, project, plan = self.fixture()
        fee = {'fee_id': 'F001', 'description': '额外改站', 'amount': None,
            'client_amount': '100.00', 'status': '已选', 'scheduled_date': '2026-11-20',
            'stage': plan['stages'][0]['name']}
        for target in (plan, plan['quote_options'][0]):
            target['fees'] = [copy.deepcopy(fee)]
            with self.subTest(target='main' if target is plan else 'higher'), self.assertRaisesRegex(ValueError, '固定双档不接受额外执行收费fees'):
                self.prepare(report, project, plan)
            target['fees'][0]['status'] = '候选'
        config = self.prepare(report, project, plan)
        self.assertTrue(all(len(card['media'].splitlines()) == 3 for card in config['pages'][8]['items']))

    def test_extra_publication_does_not_increase_independent_writing_fee(self):
        report, project, plan = self.fixture()
        for records in (plan['placements'], plan['quote_options'][0]['placements']):
            records[0]['quantity'] = '2'
        config = self.prepare(report, project, plan)
        self.assertIn('72篇共¥7,200.00', config['pages'][8]['writing'])
        self.assertIn('73次发布', config['pages'][8]['items'][0]['scale'])

    def test_small_real_scope_is_not_forced_to_seventy_two_but_has_minimum_media_fee(self):
        report, project, plan = self.fixture()
        plan['contents'] = plan['contents'][:8]
        plan['placements'] = plan['placements'][:8]
        plan['quote_options'][0]['placements'] = plan['quote_options'][0]['placements'][:8]
        plan['stages'] = plan['stages'][:1]
        names = list(dict.fromkeys(c['content_group'] for c in plan['contents']))
        report['execution']['pages'][3]['groups'] = [g for g in report['execution']['pages'][3]['groups'] if g['name'] in names]
        report['execution']['pages'][5]['items'] = report['execution']['pages'][5]['items'][:1]
        with self.assertRaisesRegex(ValueError, '至少12000'):
            self.prepare(report, project, plan)
        for records in (plan['placements'], plan['quote_options'][0]['placements']):
            for item in records:
                item['quantity'] = 4
        config = self.prepare(report, project, plan)
        self.assertIn('8篇', config['pages'][8]['items'][0]['scale'])
        self.assertEqual(config['pages'][8]['items'][0]['total'], '¥12,400.00')
        self.assertEqual(config['pages'][8]['items'][1]['total'], '¥16,800.00')
        self.assertIn('8篇共¥800.00', config['pages'][8]['writing'])

    def test_stale_analysis_and_incomplete_actual_prices_are_rejected(self):
        report, project, plan = self.fixture()
        analysis = {'project': project, 'budget': calculate_budget(project, plan)}
        plan['placements'][0]['quantity'] = 2
        with self.assertRaisesRegex(ValueError, '不一致'):
            export_pdf.prepare_document('execution', report, project, plan, analysis)
        report, project, plan = self.fixture()
        plan['placements'][0]['client_unit_price'] = None
        with self.assertRaisesRegex(ValueError, '尚未明确'):
            self.prepare(report, project, plan)

    def test_report_cannot_override_computed_numbers_or_work_scope(self):
        for location, key, value in [(4, 'quantity', '999次'), (5, 'period', '永远'), (8, 'total', '¥1.00')]:
            report, project, plan = self.fixture()
            report['execution']['pages'][location]['items'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.prepare(report, project, plan)
        report, project, plan = self.fixture()
        report['execution']['pages'][6]['rows'] = [['虚构', '承诺', '全部包含']]
        with self.assertRaises(ValueError):
            self.prepare(report, project, plan)

    def test_diagnosis_remains_independent_but_layout_and_language_are_fixed(self):
        report, _, _ = self.fixture()
        report.pop('execution')
        config = export_pdf.prepare_document('diagnosis', report)
        self.assertEqual(set(config), {'customer', 'purpose', 'pages'})
        self.assertEqual(len(config['pages']), 8)
        report['diagnosis']['pages'][1]['items'][0]['body'] = '避免同义标题重复计篇。'
        self.assertTrue(renderer.validate_report(report))

    def test_overflow_does_not_publish_partial_batch_and_existing_output_is_preserved(self):
        report, project, plan = self.fixture()
        report['execution']['pages'][1]['items'][0]['body'] = '完整事实不能截断' * 100
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'new'
            with self.assertRaisesRegex(ValueError, 'overflow'):
                export_pdf.export_reports(report, out, project=project, plan=plan, png_scale=.1)
            self.assertFalse(out.exists())
        report, _, _ = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / export_pdf.FILES['diagnosis'];out.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                export_pdf.export_reports(report, folder, kinds=('diagnosis',))
            self.assertEqual(out.read_bytes(), b'keep')

    def test_private_review_paths_do_not_add_customer_attachments_or_allow_mixing(self):
        report, project, plan = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / '客户'
            with self.assertRaisesRegex(ValueError, '内部工作目录'):
                export_pdf.export_reports(report, out, project=project, plan=plan, review_root=out/'previews')
            result = export_pdf.export_reports(report, out, kinds=('diagnosis',), png_scale=.1, review_root=out/'.work'/'pdf-review')
            self.assertEqual([p.name for p in out.iterdir() if p.is_file()], [export_pdf.FILES['diagnosis']])
            self.assertTrue(Path(result['diagnosis']['audit']).is_file())

    def test_modified_assets_are_rejected(self):
        with patch.object(export_pdf.hashlib, 'sha256') as digest:
            digest.return_value.hexdigest.return_value = 'changed'
            with self.assertRaisesRegex(ValueError, '资产已被改动'):
                export_pdf.verify_assets()


if __name__ == '__main__':
    unittest.main()
