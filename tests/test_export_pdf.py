import copy
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
        report = export_pdf.load_json(ROOT/'references/report.example.json')
        project = export_pdf.load_json(ROOT/'references/project.example.json')
        plan = export_pdf.load_json(ROOT/'references/plan.example.json')
        return report, project, plan

    def test_two_python_only_pdfs_have_expected_pages_text_and_no_internal_data(self):
        report, project, plan = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'正式输出'
            result = export_pdf.export_reports(report,output,project=project,plan=plan,png_scale=.2)
            for kind,count in [('diagnosis',8),('execution',9)]:
                with fitz.open(result[kind]['pdf']) as doc:
                    self.assertEqual(len(doc),count)
                    self.assertTrue(all(p.rect == fitz.Rect(0,0,1200,675) for p in doc))
                    text = ''.join(p.get_text() for p in doc)
                    self.assertIn('知桥协同',text)
                    self.assertIn('演示平台',text)
                    for secret in ('C001','Q001','unit_price','内部采购','media_id','DEMO-ZHIQIAO'):
                        self.assertNotIn(secret,text)
                    self.assertEqual(check_client_report.check([(1,text)]),[])
                    if kind=='execution':
                        self.assertIn('19,100.00',text)
                        self.assertIn('26篇独立稿件',text)
                        self.assertNotIn('方案二',text)
                review = Path(result[kind]['review_dir'])
                self.assertEqual(len(list(review.glob(kind+'_page_*.png'))),count)
                audit = json.loads(Path(result[kind]['audit']).read_text(encoding='utf-8'))
                self.assertTrue(all(Path(p).is_file() for p in audit['rendered_pages']))
            self.assertEqual(sorted(p.name for p in output.iterdir()),sorted(export_pdf.FILES.values()))

    def test_review_output_cannot_be_mixed_into_customer_directory(self):
        report, project, plan = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)/'正式输出'
            with self.assertRaisesRegex(ValueError,'内部工作目录'):
                export_pdf.export_reports(report,out,project=project,plan=plan,review_root=out/'previews')
            self.assertFalse(out.exists())

    def test_private_work_folder_inside_client_directory_is_supported(self):
        report, project, plan = self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)/'客户文件'
            result = export_pdf.export_reports(report,out,project=project,plan=plan,
                kinds=('diagnosis',),png_scale=.1,review_root=out/'.work'/'pdf-review')
            self.assertEqual([p.name for p in out.iterdir() if p.is_file()],[export_pdf.FILES['diagnosis']])
            self.assertTrue(Path(result['diagnosis']['audit']).is_file())

    def test_diagnosis_is_independent_of_internal_project_and_plan(self):
        report, _, _ = self.fixture()
        report.pop('execution')
        config=export_pdf.prepare_document('diagnosis',report)
        self.assertEqual(len(config['pages']),8)
        self.assertEqual(set(config),{'customer','purpose','pages'})

    def test_diagnosis_cannot_replace_its_fixed_page_layout(self):
        report, _, _ = self.fixture()
        report['diagnosis']['pages'][2] = copy.deepcopy(report['diagnosis']['pages'][3])
        report['diagnosis']['pages'][2]['title'] = renderer.DIAGNOSIS_TITLES[2]
        with self.assertRaisesRegex(ValueError,'layout must be cards3'):
            export_pdf.prepare_document('diagnosis',report)

    def test_page_count_order_and_nested_types_are_checked(self):
        report, _, _ = self.fixture()
        for change in ('count','title','nested','extra','placeholder'):
            bad=copy.deepcopy(report)
            if change=='count':bad['diagnosis']['pages'].pop()
            elif change=='title':bad['execution']['pages'][2]['title']='错误标题'
            elif change=='nested':bad['diagnosis']['pages'][1]['banner']='bad'
            elif change=='extra':bad['diagnosis']['pages'][1]['raw_answers']=['private']
            else:bad['diagnosis']['pages'][1]['items'][0]['body']='{{待填写}}'
            with self.subTest(change=change),self.assertRaises(ValueError):
                export_pdf.prepare_document('diagnosis',bad)

    def test_report_cannot_override_computed_accounting(self):
        report,project,plan=self.fixture()
        for location,key,value in [(4,'rows',[['x','y','z','w']]),(5,'counts','999篇'),(8,'total','¥1.00')]:
            bad=copy.deepcopy(report)
            page=bad['execution']['pages'][location]
            target=page if location==4 else page['items'][0]
            target[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'不可'):
                export_pdf.prepare_document('execution',bad,project,plan)

    def test_stale_or_incomplete_prices_and_false_second_quote_are_rejected(self):
        report,project,plan=self.fixture()
        analysis={'project':project,'budget':calculate_budget(project,plan)}
        changed=copy.deepcopy(plan);changed['placements'][0]['client_unit_price']='999'
        with self.assertRaisesRegex(ValueError,'不一致'):
            export_pdf.prepare_document('execution',report,project,changed,analysis)
        missing=copy.deepcopy(plan);missing['placements'][0]['client_unit_price']=None
        with self.assertRaisesRegex(ValueError,'尚未明确'):
            export_pdf.prepare_document('execution',report,project,missing)
        report['execution']['pages'][8]['items'].append(copy.deepcopy(report['execution']['pages'][8]['items'][0]))
        with self.assertRaisesRegex(ValueError,'不可补造'):
            export_pdf.prepare_document('execution',report,project,plan)

    def test_real_alternative_uses_its_client_prices_and_same_content_scope(self):
        report,project,plan=self.fixture()
        option={'name':'备选媒体配置','placements':copy.deepcopy(plan['placements']),'fees':[]}
        option['placements'][0]['client_unit_price']=str(Decimal(option['placements'][0]['client_unit_price'])+100)
        plan['quote_options']=[option]
        card=copy.deepcopy(report['execution']['pages'][8]['items'][0]);card['name']=option['name']
        report['execution']['pages'][8]['items'].append(card)
        config=export_pdf.prepare_document('execution',report,project,plan)
        self.assertEqual(config['pages'][8]['items'][1]['total'],'¥19,200.00')
        self.assertNotEqual(config['pages'][8]['items'][0]['total'],config['pages'][8]['items'][1]['total'])
        option['placements']=option['placements'][:-1]
        with self.assertRaisesRegex(ValueError,'相同独立稿件'):
            export_pdf.prepare_document('execution',report,project,plan)

    def test_four_quarters_string_quantities_and_stage_totals_use_actual_plan(self):
        report,project,plan=self.fixture()
        project.update(start_date='2027-01-01',end_date='2027-12-31')
        plan['stages']=[{'name':f'2027Q{i}'} for i in range(1,5)]
        for i,content in enumerate(plan['contents']):
            quarter=i%4+1
            content.update(stage=f'2027Q{quarter}',scheduled_date=f'2027-{(quarter-1)*3+1:02d}-10')
            placement=plan['placements'][i]
            placement.update(scheduled_date=content['scheduled_date'],quantity=str(placement['quantity']))
        report['execution']['pages'][5]['items']=[{'title':f'2027Q{i}','work':'按实际场景安排内容。','cooperation':'确认事实与公开范围。'} for i in range(1,5)]
        config=export_pdf.prepare_document('execution',report,project,plan)
        stages=config['pages'][5]['items']
        self.assertEqual(len(stages),4)
        self.assertTrue(stages[0]['period'].startswith('2027-01-10'))
        self.assertEqual(sum(Decimal(s['amount'].replace('¥','').replace(',','')) for s in stages),Decimal('19100'))
        with tempfile.TemporaryDirectory() as folder:
            result=renderer.render(config,Path(folder),'execution',png_scale=.1)
            with fitz.open(result['pdf']) as doc:
                self.assertIn('2027Q4',doc[5].get_text())

    def test_eight_content_five_media_group_quote_preserves_all_actual_prices(self):
        report,project,plan=self.fixture()
        plan['contents']=plan['contents'][:8]
        plan['placements']=plan['placements'][:8]
        stage=plan['stages'][0]['name']
        plan['stages']=plan['stages'][:1]
        groups=[g['name'] for g in report['execution']['pages'][3]['groups']]
        categories=['科技资讯定位与迁移','科技资讯定位与迁移','北京企业资讯','北京企业资讯','科技资讯验收说明','自媒体场景图文','自媒体场景图文','企业管理资讯']
        prices=['3000','2500','2200','2000','2000','2800','2500','1600']
        for i,(content,placement) in enumerate(zip(plan['contents'],plan['placements'])):
            content.update(content_group=groups[i//2],stage=stage)
            placement.update(media_type=categories[i],client_unit_price=prices[i],quantity='1')
        report['execution']['pages'][5]['items']=report['execution']['pages'][5]['items'][:1]
        config=export_pdf.prepare_document('execution',report,project,plan)
        self.assertEqual(config['pages'][8]['items'][0]['total'],'¥18,600.00')
        with tempfile.TemporaryDirectory() as folder:
            result=renderer.render(config,Path(folder),'execution',png_scale=.1)
            with fitz.open(result['pdf']) as doc:
                text=doc[8].get_text()
                self.assertIn('18,600.00',text)
                for category in set(categories):self.assertIn(category,''.join(text.split()))

    def test_overflow_is_an_error_and_does_not_publish_partial_batch(self):
        report,project,plan=self.fixture()
        report['execution']['pages'][1]['items'][0]['body']='完整事实不能截断'*100
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'new'
            with self.assertRaisesRegex(ValueError,'overflow'):
                export_pdf.export_reports(report,out,project=project,plan=plan,png_scale=.1)
            self.assertFalse(out.exists())

    def test_existing_outputs_and_asset_changes_are_rejected(self):
        report,_,_=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/export_pdf.FILES['diagnosis'];out.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                export_pdf.export_reports(report,folder,kinds=('diagnosis',))
            self.assertEqual(out.read_bytes(),b'keep')
        with patch.object(export_pdf.hashlib,'sha256') as digest:
            digest.return_value.hexdigest.return_value='changed'
            with self.assertRaisesRegex(ValueError,'资产已被改动'):
                export_pdf.verify_assets()

    def test_business_api_terms_are_allowed_but_research_language_is_rejected(self):
        report,_,_=self.fixture()
        report['diagnosis']['pages'][1]['items'][0]['body']='产品提供 API 接口支持知识库集成。'
        self.assertEqual(renderer.validate_report(report),[])
        report['diagnosis']['pages'][1]['items'][0]['body']='Web端未提及该品牌'
        self.assertTrue(renderer.validate_report(report))


if __name__=='__main__':unittest.main()
