import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest

import fitz

ROOT = Path(__file__).resolve().parents[1] / '.codebuddy/skills/ruanwenjie-geo'
sys.path.insert(0, str(ROOT / 'scripts'))
import brand_plan
import export_pdf


def fixture():
    plan = {
        'evidence': [
            {'id': 'E1', 'summary': '需求推荐围绕同业方案展开', 'source': '豆包采集记录'},
            {'id': 'E2', 'summary': '客户材料列明项目协作流程', 'source': '客户素材表'},
        ],
        'findings': [
            {'id': 'F1', 'observation': '自然需求中品牌尚未进入候选',
             'analysis': '公开内容对选型条件和适用场景说明不足',
             'business_impact': '目标采购方难以将品牌与实际需求关联',
             'priority': 'high', 'evidence_ids': ['E1']},
            {'id': 'F2', 'observation': '项目协作流程有现成业务基础',
             'analysis': '可将过程事实整理为可检索的案例内容',
             'business_impact': '帮助客户比较交付与协作方式',
             'priority': 'medium', 'evidence_ids': ['E2']},
        ],
        'actions': [
            {'id': 'A1', 'finding_ids': ['F1', 'F2'], 'task': '形成材料选型与案例内容',
             'content': '从项目要求、选型判断和协作过程展开', 'keywords': ['材料选型', '项目协作'],
             'media_role': '行业媒体', 'stage': '首批', 'owner': '软文街策划，客户审核',
             'deliverable': '四篇选型与案例稿件及刊发链接', 'review': '关注需求候选与选择理由变化'},
            {'id': 'A2', 'finding_ids': ['F2'], 'task': '统一官方流程说明',
             'content': '由客户核实并更新项目协作流程', 'keywords': [],
             'media_role': '官方信息', 'stage': '与首批并行', 'owner': '客户负责实际更新',
             'deliverable': '核准后的流程说明', 'review': '核对主体和服务口径'},
        ],
        'service_scope': [
            {'id': 'S1', 'task': '内容策划与阶段复核', 'provider': '确定选题和阶段调整方向',
             'client': '提供事实材料并审核', 'action_ids': ['A1']},
            {'id': 'S2', 'task': '行业媒体发布', 'provider': '按约定组织刊发并汇总链接',
             'client': '确认定稿与授权', 'action_ids': ['A1']},
            {'id': 'S3', 'task': '正文撰写', 'provider': '按约定撰写四篇正文',
             'client': '进行专业审核', 'action_ids': ['A1']},
            {'id': 'S4', 'task': '官方信息更新', 'provider': '整理需统一的信息',
             'client': '核实并操作官方页面', 'action_ids': ['A2']},
        ],
        'pricing': {
            'instructions': '用户要求只出一档，发布整包1800元，写作每篇123.45元共四篇，策划复核已含，官网由客户更新，含税。',
            'currency': 'CNY', 'tax_note': '含税', 'budget_target': '20000.00',
            'options': [{'name': '首批方案', 'items': [
                {'name': '策划与复核', 'category': 'service', 'billing': 'included', 'covers': ['S1']},
                {'name': '行业媒体发布', 'category': 'media', 'billing': 'package', 'covers': ['S2'], 'amount': '1800.00'},
                {'name': '正文撰写', 'category': 'writing', 'billing': 'unit', 'covers': ['S3'],
                 'quantity': 4, 'unit': '篇', 'unit_price': '123.45'},
                {'name': '客户更新官网', 'category': 'service', 'billing': 'client_provided', 'covers': ['S4']},
            ]}],
        },
    }
    report = {
        'schema_version': '3.0',
        'customer': {'brand': '澄光研材', 'company': '澄光研材服务有限公司', 'date': '2026-11-14', 'observed_platforms': ['豆包']},
        'theme': {'primary': '#224F6B', 'accent': '#BD985F', 'background': '#F7FAFC', 'text': '#172633', 'cover_style': 'technical'},
        'purpose': '让材料选型需求连接真实项目证据',
        'diagnosis': {'pages': [
            {'layout': 'cover', 'title': '品牌认知与需求机会', 'headline': '以项目事实说明选择理由'},
            {'layout': 'insights', 'title': '当前认知与业务机会', 'source': 'findings'},
        ]},
        'execution': {'pages': [
            {'layout': 'cover', 'title': '品牌传播与执行方案', 'headline': '以选型和案例内容承接采购判断'},
            {'layout': 'cards', 'title': '关键诊断与执行重点', 'source': 'findings', 'ids': ['F1']},
            {'layout': 'table', 'title': '诊断对应执行安排', 'source': 'action-map'},
            {'layout': 'table', 'title': '双方分工与配合', 'source': 'service-scope'},
            {'layout': 'quotes', 'title': '费用与包含范围', 'source': 'quotes'},
        ]},
    }
    return report, plan


class BrandPlanTests(unittest.TestCase):
    def test_actual_user_prices_single_option_and_no_legacy_floor(self):
        _, plan = fixture()
        priced = brand_plan.calculate_pricing(plan)
        self.assertEqual(len(priced['options']), 1)
        self.assertEqual(priced['options'][0]['total'], Decimal('2293.80'))
        self.assertEqual(priced['options'][0]['media_total'], Decimal('1800.00'))
        self.assertIsNone(priced['limit'])
        self.assertIsNone(priced['options'][0]['remaining'])

    def test_unquoted_is_unknown_not_zero_and_budget_does_not_create_price(self):
        report, plan = fixture()
        plan['pricing']['options'][0]['items'][1] = {'name': '媒体发布待报价', 'category': 'media', 'billing': 'unquoted', 'covers': ['S2']}
        option = brand_plan.calculate_pricing(plan)['options'][0]
        self.assertIsNone(option['total'])
        self.assertEqual(option['known_subtotal'], Decimal('493.80'))
        self.assertIsNone(option['media_total'])
        config = brand_plan.prepare_document('execution', report, plan=plan)
        price_page = config['pages'][-1]
        self.assertIn(['首批方案', '方案总价', '含税', '待确认'], price_page['rows'])
        self.assertNotIn('20,000.00', str(price_page['rows']))

    def test_package_price_and_scope_do_not_duplicate_writing(self):
        _, plan = fixture()
        option = plan['pricing']['options'][0]
        option['items'] = [
            {'name': '整包方案', 'category': 'package', 'billing': 'package', 'covers': ['S1', 'S2', 'S3'], 'amount': '6666.66'},
            {'name': '客户更新', 'category': 'service', 'billing': 'client_provided', 'covers': ['S4']},
        ]
        self.assertEqual(brand_plan.calculate_pricing(plan)['options'][0]['total'], Decimal('6666.66'))
        self.assertIsNone(brand_plan.calculate_pricing(plan)['options'][0]['media_total'])
        option['items'].append({'name': '额外写作', 'category': 'writing', 'billing': 'unit', 'covers': ['S3'], 'quantity': 4, 'unit': '篇', 'unit_price': '100'})
        with self.assertRaisesRegex(ValueError, '重复计价'):
            brand_plan.calculate_pricing(plan)

    def test_hard_budget_and_explicit_user_minimums_only(self):
        _, plan = fixture()
        plan['pricing']['budget_target'] = '100.00'
        self.assertEqual(brand_plan.calculate_pricing(plan)['options'][0]['total'], Decimal('2293.80'))
        plan['pricing']['budget_limit'] = '2000'
        with self.assertRaisesRegex(ValueError, '预算上限'):
            brand_plan.calculate_pricing(plan)
        plan['pricing']['budget_limit'] = '3000'
        with self.assertRaisesRegex(ValueError, '预算口径冲突'):
            brand_plan.calculate_pricing(plan, {'budget_limit': '4000'})
        self.assertEqual(brand_plan.calculate_pricing(plan, {'budget_limit': '3000'})['options'][0]['remaining'], Decimal('706.20'))
        plan['pricing']['minimum_total'] = '2500'
        with self.assertRaisesRegex(ValueError, '最低总价'):
            brand_plan.calculate_pricing(plan)
        del plan['pricing']['minimum_total']
        plan['pricing']['minimum_media_total'] = '1900'
        with self.assertRaisesRegex(ValueError, '最低媒体费'):
            brand_plan.calculate_pricing(plan)

    def test_one_or_multiple_options_follow_explicit_count(self):
        _, plan = fixture()
        option = plan['pricing']['options'][0]
        other = copy.deepcopy(option)
        other['name'] = '扩展方案'
        other['items'][1]['amount'] = '4000'
        plan['pricing']['options'].append(other)
        plan['pricing']['required_option_count'] = 2
        self.assertEqual([o['total'] for o in brand_plan.calculate_pricing(plan)['options']], [Decimal('2293.80'), Decimal('4493.80')])
        report, _ = fixture()
        scopes = next(page for page in brand_plan.prepare_document('execution', report, plan=plan)['pages'] if page['title'] == '双方分工与配合')
        self.assertEqual(scopes['rows'][0][3], '各档：已含')
        plan['pricing']['required_option_count'] = 3
        with self.assertRaisesRegex(ValueError, '档数'):
            brand_plan.calculate_pricing(plan)

    def test_matching_two_or_three_options_compare_actual_prices_side_by_side(self):
        report, plan = fixture()
        second = copy.deepcopy(plan['pricing']['options'][0])
        second['name'] = '扩展方案'
        second['items'][1]['amount'] = '4000.00'
        second['items'][2].update(quantity=8, unit_price='250.00')
        second['items'].reverse()
        plan['pricing']['options'].append(second)
        plan['pricing']['budget_limit'] = '10000.00'
        quote = brand_plan.prepare_document('execution', report, plan=plan)['pages'][-1]
        self.assertEqual(quote['headers'], ['项目与范围', '首批方案', '扩展方案'])
        self.assertEqual(len(quote['rows']), 6)
        writing = next(row for row in quote['rows'] if row[0].startswith('正文撰写'))
        self.assertEqual(writing[1:], ['4篇 × ¥123.45 = ¥493.80', '8篇 × ¥250.00 = ¥2,000.00'])
        self.assertIn(['方案总价（含税）', '¥2,293.80', '¥6,000.00'], quote['rows'])
        self.assertIn(['明确预算上限／余额', '¥10,000.00\n余额：¥7,706.20', '¥10,000.00\n余额：¥4,000.00'], quote['rows'])
        self.assertEqual(sum(row[1:] == ['已含', '已含'] for row in quote['rows']), 1)
        self.assertEqual(sum(row[1:] == ['客户提供', '客户提供'] for row in quote['rows']), 1)
        third = copy.deepcopy(second); third['name'] = '第三方案'
        plan['pricing']['options'].append(third)
        quote = brand_plan.prepare_document('execution', report, plan=plan)['pages'][-1]
        self.assertEqual(len(quote['headers']), 4)
        self.assertEqual(len(quote['rows']), 6)

    def test_comparison_keeps_unknown_amounts_and_falls_back_for_different_scopes(self):
        report, plan = fixture()
        plan['pricing']['options'][0]['items'][1] = {'name': '媒体发布待报价', 'category': 'media', 'billing': 'unquoted', 'covers': ['S2']}
        second = copy.deepcopy(plan['pricing']['options'][0]); second['name'] = '另一方案'
        plan['pricing']['options'].append(second)
        quote = brand_plan.prepare_document('execution', report, plan=plan)['pages'][-1]
        self.assertEqual(quote['headers'], ['项目与范围', '首批方案', '另一方案'])
        self.assertIn(['已明确费用小计', '¥493.80', '¥493.80'], quote['rows'])
        self.assertIn(['方案总价（含税）', '待确认', '待确认'], quote['rows'])
        for change in ('name', 'note', 'category', 'billing', 'covers', 'four_options'):
            report, plan = fixture()
            second = copy.deepcopy(plan['pricing']['options'][0]); second['name'] = '另一方案'
            if change == 'name': second['items'][1]['name'] = '不同的媒体服务'
            elif change == 'note': second['items'][1]['note'] = '附有不同约定'
            elif change == 'category': second['items'][1]['category'] = 'service'
            elif change == 'billing': second['items'][1] = {'name': '行业媒体发布', 'category': 'media', 'billing': 'unquoted', 'covers': ['S2']}
            elif change == 'covers':
                second['items'][0]['covers'], second['items'][1]['covers'] = second['items'][1]['covers'], second['items'][0]['covers']
            plan['pricing']['options'].append(second)
            if change == 'four_options':
                for name in ('第三方案', '第四方案'):
                    other = copy.deepcopy(second); other['name'] = name; plan['pricing']['options'].append(other)
            quote = brand_plan.prepare_document('execution', report, plan=plan)['pages'][-1]
            with self.subTest(change=change):
                self.assertEqual(quote['headers'], ['方案', '项目与范围', '计价口径', '金额'])

    def test_prices_quantities_and_supplied_totals_are_validated(self):
        for value in ['-1', 'NaN', 'Infinity', None, True, 'not a number']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                brand_plan.amount(value)
        for value in [0, -1, 1.5, '2', True]:
            _, plan = fixture()
            plan['pricing']['options'][0]['items'][2]['quantity'] = value
            with self.subTest(quantity=value), self.assertRaises(ValueError):
                brand_plan.calculate_pricing(plan)
        _, plan = fixture()
        plan['pricing']['options'][0]['items'][2]['amount'] = '1'
        with self.assertRaisesRegex(ValueError, '合计字段'):
            brand_plan.calculate_pricing(plan)
        _, plan = fixture()
        plan['pricing']['options'][0]['total'] = '1'
        with self.assertRaisesRegex(ValueError, '明细核算'):
            brand_plan.calculate_pricing(plan)

    def test_evidence_links_dangling_actions_and_deferred_reasons(self):
        for mutation in ('no_evidence', 'unknown_evidence', 'unknown_finding', 'uncovered_finding', 'deferred'):
            _, plan = fixture()
            if mutation == 'no_evidence': del plan['findings'][0]['evidence_ids']
            elif mutation == 'unknown_evidence': plan['findings'][0]['evidence_ids'] = ['E9']
            elif mutation == 'unknown_finding': plan['actions'][0]['finding_ids'] = ['F9']
            elif mutation == 'uncovered_finding':
                plan['actions'] = plan['actions'][1:]
            else: plan['actions'][0]['status'] = 'deferred'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                brand_plan.validate_links(plan)
        _, plan = fixture()
        plan['actions'][0].update(status='deferred', defer_reason='客户项目材料确认后开展')
        brand_plan.validate_links(plan)

    def test_service_scope_coverage_and_duplicate_identities(self):
        _, plan = fixture()
        for scope in plan['service_scope']:
            scope['action_ids'] = ['A1']
        with self.assertRaisesRegex(ValueError, '未说明负责方与费用范围'):
            brand_plan.calculate_pricing(plan)
        _, plan = fixture()
        plan['pricing']['options'][0]['items'].pop()
        with self.assertRaisesRegex(ValueError, '未说明服务'):
            brand_plan.calculate_pricing(plan)
        _, plan = fixture()
        plan['service_scope'][1]['action_ids'] = ['A9']
        with self.assertRaisesRegex(ValueError, '不存在'):
            brand_plan.calculate_pricing(plan)
        _, plan = fixture()
        extra = copy.deepcopy(plan['service_scope'][0]); extra['id'] = 'S9'; plan['service_scope'].append(extra)
        with self.assertRaisesRegex(ValueError, '重复收费身份'):
            brand_plan.calculate_pricing(plan)

    def test_client_modules_show_findings_actions_scope_and_computed_prices(self):
        report, plan = fixture()
        diagnosis = brand_plan.prepare_document('diagnosis', report, plan=plan)
        execution = brand_plan.prepare_document('execution', report, plan=plan)
        all_text = json.dumps(execution, ensure_ascii=False)
        self.assertIn('自然需求中品牌尚未进入候选', all_text)
        self.assertIn('形成材料选型与案例内容', all_text)
        self.assertIn('¥2,293.80', all_text)
        for internal in ['E1', 'F1', 'A1', 'S1', '采集记录', 'source', 'evidence_ids']:
            self.assertNotIn(internal, all_text)
        self.assertEqual(len(diagnosis['pages'][1]['items']), 2)
        self.assertEqual(len(execution['pages'][1]['items']), 1)
        self.assertEqual(len(execution['pages'][2]['rows']), 2)

    def test_internal_validation_without_client_visible_links_is_rejected(self):
        for removed in ['findings', 'action-map', 'service-scope', 'quotes']:
            report, plan = fixture()
            report['execution']['pages'] = [p for p in report['execution']['pages'] if p.get('source') != removed]
            with self.subTest(removed=removed), self.assertRaises(ValueError):
                brand_plan.prepare_document('execution', report, plan=plan)
        report, plan = fixture()
        report['diagnosis']['pages'][1]['ids'] = ['F1']
        with self.assertRaisesRegex(ValueError, '关键诊断'):
            brand_plan.prepare_document('diagnosis', report, plan=plan)
        report, plan = fixture()
        report['execution']['pages'][2]['ids'] = ['A1']
        with self.assertRaisesRegex(ValueError, '完整呈现'):
            brand_plan.prepare_document('execution', report, plan=plan)

    def test_report_cannot_supply_different_price_rows_or_hide_scope(self):
        report, plan = fixture()
        report['execution']['pages'][-1]['rows'] = [['私填报价', '1']]
        with self.assertRaises(ValueError):
            brand_plan.prepare_document('execution', report, plan=plan)
        report, plan = fixture()
        report['execution']['pages'][-1]['ids'] = ['首批方案']
        with self.assertRaisesRegex(ValueError, '完整呈现'):
            brand_plan.prepare_document('execution', report, plan=plan)
        report, plan = fixture()
        report['execution']['pages'].insert(1, {'layout': 'table', 'title': '额外费用', 'headers': ['项目', '金额'], 'rows': [['另填总价', '1元']]})
        with self.assertRaisesRegex(ValueError, '不能自由手填'):
            brand_plan.prepare_document('execution', report, plan=plan)

    def test_export_new_mode_atomic_files_actual_page_count_and_no_legacy_prices(self):
        report, plan = fixture()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / '正式输出'
            result = export_pdf.export_reports(report, output, plan=plan, png_scale=.15)
            for kind in ('diagnosis', 'execution'):
                with fitz.open(result[kind]['pdf']) as doc:
                    self.assertEqual(len(doc), result[kind]['pages'])
                    text = ''.join(page.get_text() for page in doc)
                    self.assertIn('澄光研材', text)
                    self.assertNotIn('普通权重方案', text)
                    self.assertNotIn('12,000', text)
                    self.assertNotIn('F1', text)
                    if kind == 'execution':
                        self.assertIn('2,293.80', text)
                        self.assertIn('形成材料选型与案例内容', text)
                audit = json.loads(Path(result[kind]['audit']).read_text(encoding='utf-8'))
                self.assertEqual(len(audit['rendered_pages']), result[kind]['pages'])
            self.assertEqual(sorted(p.name for p in output.iterdir()), sorted(export_pdf.FILES.values()))
            with self.assertRaises(FileExistsError):
                export_pdf.export_reports(report, output, plan=plan, png_scale=.15)
        report, plan = fixture()
        plan['actions'][0]['finding_ids'] = ['missing']
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / '正式输出'
            with self.assertRaises(ValueError):
                export_pdf.export_reports(report, output, plan=plan, png_scale=.15)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
