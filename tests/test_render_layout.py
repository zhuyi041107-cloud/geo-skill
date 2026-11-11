import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

import fitz

ROOT=Path(__file__).resolve().parents[1]/'.codebuddy/skills/ruanwenjie-geo'
sys.path.insert(0,str(ROOT/'scripts'))
import render_geo_diagnosis as renderer


def customer_report():
    return json.loads((ROOT/'references/report.example.json').read_text(encoding='utf-8'))


def rendered_report():
    report=customer_report();pages=report['execution']['pages']
    counts=[4,8,16,16,12,8,8]
    pages[3].update(headers=['内容方向','篇数','重点介绍','主要作用'],
        rows=[[g['name'],f'{count}篇',g['detail'],g['role']] for g,count in zip(pages[3]['groups'],counts)],
        note='72篇独立稿件，覆盖本期重点场景。')
    for item,quantity in zip(pages[4]['items'],[24,36,12]):
        item.update(resources='普通：知桥资讯；高：协同观察',quantity=f'{quantity}次',amount='普通¥1,200.00 / 高¥1,800.00')
    for item in pages[5]['items']:
        item.update(period='2027-01-01 - 2027-01-28',counts='18篇 / 18次刊发',
            media_counts='权威6次 / 行业9次 / 自媒体3次',amount='普通¥5,100.00 / 高¥7,200.00')
    pages[6].update(headers=['工作事项','软文街负责','贵司配合'],rows=[
        ['内容与媒体','规划选题与发布，整理链接清单。','提供已有资料并审核事实。'],
        ['范围与责任','整理服务边界及实施内容。','确认公开范围与客户授权。'],
        ['阶段复核','分别观察认知与选择理由。','核对新增材料与业务变化。']])
    for item in pages[8]['items']:
        item.update(total='¥20,400.00',scale='媒体发布费｜72篇 / 72次发布',
            media='权威媒体24次×¥450=¥10,800\n行业媒体36次×¥200=¥7,200\n自媒体12次×¥200=¥2,400')
    pages[8].update(services='含内容策划、媒体发布、链接汇总与阶段复核；AI起草及人工简单修改已含。',
        writing='AI起草及人工简单修改已含；人工撰写原价200元/篇，打包100元/篇，72篇共7,200元。\n全量人工撰写合计：普通权重27,600元；高权重36,000元。')
    return report


class FixedLayoutTests(unittest.TestCase):
    def assert_rendered_color(self,page,fragment,color):
        spans=[span for block in page.get_text('dict')['blocks'] if 'lines' in block
               for line in block['lines'] for span in line['spans']
               if fragment in span['text'] and 150<=span['bbox'][1]<575]
        self.assertTrue(spans,fragment)
        expected=int(color,16)
        self.assertTrue(all(span['color']==expected for span in spans),(fragment,[hex(s['color']) for s in spans]))
        image=page.get_pixmap(clip=fitz.Rect(spans[0]['bbox']))
        rgb=(expected>>16,(expected>>8)&255,expected&255);samples=image.samples
        self.assertTrue(any(all(abs(samples[i+k]-rgb[k])<=2 for k in range(3))
                            for i in range(0,len(samples),image.n)),fragment)

    def test_author_contract_is_fixed_per_page_and_rejects_computed_fields(self):
        source=customer_report()
        self.assertEqual(renderer.validate_report(source),[])
        for kind,index,layout in [('diagnosis',4,'cards3'),('diagnosis',6,'summary4'),('execution',2,'steps4'),('execution',7,'cards3')]:
            bad=copy.deepcopy(source);bad[kind]['pages'][index]['layout']=layout
            self.assertTrue(renderer.validate_report(bad))
        for index,key,value in [(3,'rows',[['a','b','c','d']]),(6,'rows',[['a','b','c']]),(8,'writing','自填金额')]:
            bad=copy.deepcopy(source);bad['execution']['pages'][index][key]=value
            self.assertTrue(any('不可手填' in error for error in renderer.validate_report(bad)))

    def test_rendered_boundary_requires_computed_data_and_rejects_internal_records(self):
        report=rendered_report()
        self.assertEqual(renderer.validate_report(report,rendered=True),[])
        report['execution']['pages'][4]['items'][0].pop('resources')
        self.assertTrue(renderer.validate_report(report,rendered=True))
        report=customer_report();report['diagnosis']['pages'][4]['rows'][0][2]='内部Q001原答'
        self.assertTrue(renderer.validate_report(report))

    def test_real_pdf_uses_each_background_page_once_and_retains_source_text_sizes(self):
        report=rendered_report()
        with tempfile.TemporaryDirectory() as folder:
            for kind,count in [('diagnosis',8),('execution',9)]:
                config={'customer':report['customer'],'purpose':report['purpose'],'pages':report[kind]['pages']}
                result=renderer.render(config,Path(folder),kind,png_scale=.1)
                audit=json.loads(Path(result['audit']).read_text(encoding='utf-8'))
                self.assertEqual(audit['background_pages'],list(range(1,count+1)))
                with fitz.open(result['pdf']) as doc:
                    self.assertEqual(len(doc),count)
                    self.assertTrue(all(p.rect==fitz.Rect(0,0,1200,675) for p in doc))
                    if kind=='execution':
                        self.assertIn('72次发布',doc[8].get_text())
                        self.assertIn('人工撰写',doc[8].get_text())
                        pages=report[kind]['pages']
                        self.assert_rendered_color(doc[1],pages[1]['items'][1]['heading'][:6],'4d67ff')
                        for i,item in enumerate(pages[2]['items']):
                            self.assert_rendered_color(doc[2],f'{i+1:02d} '+item['title'][:4],'4d67ff' if i%2 else '009875')
                        for col,color in enumerate(['009875','16323d','647a83','647a83']):
                            self.assert_rendered_color(doc[3],pages[3]['rows'][0][col][:6],color)
                        for index in [6,7]:
                            for col,color in enumerate(['009875','16323d','647a83']):
                                self.assert_rendered_color(doc[index],pages[index]['rows'][0][col][:6],color)
                        self.assert_rendered_color(doc[5],'18篇 / 18次刊发','4d67ff')
                        self.assert_rendered_color(doc[5],'权威6次','4d67ff')
                    else:
                        pages=report[kind]['pages']
                        for index in [3,6]:
                            self.assert_rendered_color(doc[index],pages[index]['rows'][0][2][:6],'6a7c82')
                        for item,color in zip(pages[7]['items'],['009875','386882','9a682c','009875']):
                            self.assert_rendered_color(doc[7],item['title'][:6],color)
                fonts={block['font'] for block in audit['blocks']}
                self.assertTrue(({66,31,27,18,17} if kind=='diagnosis' else {55,31,24,38,40,17,16}).issubset(fonts))

    def test_overflow_refuses_pdf_instead_of_shrinking_or_hiding_content(self):
        report=rendered_report();report['execution']['pages'][2]['items'][0]['body']='完整业务事实'*100
        config={'customer':report['customer'],'purpose':report['purpose'],'pages':report['execution']['pages']}
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'overflow'):
                renderer.render(config,Path(folder),'execution',png_scale=.1)
            self.assertFalse((Path(folder)/'品牌传播与GEO执行方案.pdf').exists())


if __name__=='__main__':unittest.main()
