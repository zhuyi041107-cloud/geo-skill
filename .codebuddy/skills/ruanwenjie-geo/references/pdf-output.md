# 固定模板PDF填写规范

两个PDF均为1200×675横版：诊断固定8页、执行固定9页，保留用户认可旧版的背景、表格、卡片、标题与字号。`scripts/export_pdf.py`是本地渲染入口，共享渲染器只填固定文字区；ReportLab绘制文字层，PyMuPDF合成背景和预览。WorkBuddy直接分析、成稿与逐页自审；全流程无需MCP、API密钥、浏览器渲染或GEO云端工具。

## 客户配置与内部计划

先完整读[逐页生成说明](template-generation.md)，再参考[客户示例](report.example.json)和[schema](customer-report.schema.json)填写：

```json
{
  "schema_version": "2.0",
  "customer": {
    "brand": "客户品牌",
    "company": "客户运营主体",
    "date": "2026-11-11",
    "observed_platforms": ["豆包"]
  },
  "purpose": "本案业务目标",
  "diagnosis": {"pages": []},
  "execution": {"pages": []}
}
```

这是根结构，空pages不能导出。实际页标题、顺序、layout和字段按当前schema与示例，不从旧0.8客户JSON直接复用不同布局。`observed_platforms`只列实际有回答的平台；已知平台用图标，其他平台用文字，不能保留未调查平台标识。

report只存客户可见稿；内部原答、截图、来源链、条件、ID、核算与logic_links保留.work。客户稿不手填computed数据，也不用额外字段夹带内部资料。

## 固定layout与作者填写范围

| 诊断页 | layout | 作者填写职责 |
| --- | --- | --- |
| 1 | cover | 品牌业务、总体判断及封面文字 |
| 2 | cards3 | 实际品牌印象、业务选择表现及主要影响 |
| 3 | comparison3 | 相关同行与自身三卡比较，label／heading／body／footer |
| 4 | table3 | 已有基础／贵司提供的服务信息／内容使用建议，三列表 |
| 5 | table4 | 对比项／当前状态／具体差异／调整建议，四列表 |
| 6 | scenes4 | 重点商业场景及首批、随后、暂缓理由 |
| 7 | customer-items3 | headers与rows，工作事项／软文街负责／贵司配合 |
| 8 | summary4 | 四项title／body，起步、首阶段、后续、持续复核 |

| 执行页 | layout | 作者填写与自动内容 |
| --- | --- | --- |
| 1 | cover | 目标、核心选择理由、本期执行重点 |
| 2 | cards3 | 当前印象／同行差异／目标认知 |
| 3 | steps4-grid | 四步2×2，体现选择差距到内容发布及调整 |
| 4 | content-plan | 与contents.content_group同名groups的name／detail／role；稿数自动 |
| 5 | media-cards3 | 三items固定category为权威媒体／行业媒体／自媒体，作者role／focus；resources／quantity／amount自动 |
| 6 | stages3 | 1至4实际阶段，作者工作和客户配合；日期、稿数、三类刊次和两档金额自动 |
| 7 | customer-items3 | headers／rows从plan.service_scope.work_items注入，report不手填 |
| 8 | review-table | 三列表的复核方向／观察重点／后续调整，明确实际复核节点 |
| 9 | quotes | 两items固定name为普通权重方案／高权重方案，作者只写tag；total／scale／media自动，页级writing／services自动 |

所有表头、行数和必填文字以当前schema为准。自动字段也必须经过客户语言检查；出现制作规则时改成对应客户事项，不把内部说明缩小藏进页底。

## 分类汇总，不指定具体媒体

`placements.strategy_role`为权威媒体、行业媒体、自媒体三类，`strategy_basis`说明该类别的传播用途，不填写具体媒体、账号、栏目或来源。媒体页自动显示三类计划刊次和两档小计，并提示具体媒体待确认；两档实际资源与权益差异尚未确定，不能表述为已选定或保证效果。无推荐Excel。

## 同源数量、服务和两档费用

project、contents、stages、主placements、quote_options及service_scope是核算来源，作者只写业务解释。主plan为普通档，quote_options严格一项高权重分类报价，内容、独立稿数和每稿刊次相同。每档媒体费按计划刊次核算且最低12,000元，不虚加补差，写作另收费。固定客户单价、写作费和预算边界统一见[费用规则](evidence-and-planning.md#普通与高权重两档客户报价)。

入口向内容组注入稿数，向三类媒体卡注入计划刊次和金额，向阶段注入日期、三类数量和两档费用。第9页同时给两档三类媒体费用、媒体费已含服务、独立写作费和含写作总价；客户JSON不得手填另一套合计或收费scope覆盖同源数据。

执行7从service_scope.work_items生成双方表，执行9按included项列基本服务；这些基础工作只含选题、大纲与素材方向等约定服务，不含执行文章的AI起草、正文撰稿或人工修改。service_scope.writing_mode=separate为默认写作单独收费分支，从manual_writing按原价200元／篇、打包100元／独立稿核写作费；client_provided时显示客户供稿且不收写作费。旧ai_assisted免费含起草模式不再适用。review_schedule明确复核节点。任务正文和服务范围有矛盾时先修计划，不用“另议”掩盖已承诺工作。

budget_target为意向预算，不自动成为硬上限；客户明确不能超过时才设budget_limit。无明确硬上限按完整任务核两档，每档实际媒体费均须达到12,000元。任一档超硬上限时重新配置实际范围，不改固定单价或藏写作费；最低媒体费与硬上限无法同时满足时明确说明冲突，不导出不合规报价。72稿与24／36／12是公式验算例，不是通用篇数或固定媒体比例。

## 生成和成品检查

Python 3.10或更新版本，按requirements.txt安装openpyxl、ReportLab、PyMuPDF。字体、背景、图标随包；无需Node、Chrome、Edge或Codex私有运行时。

```text
python "技能目录/scripts/export_pdf.py" --analysis "客户目录/.work/analysis-final.json" --plan "客户目录/.work/plan.json" --report "客户目录/.work/report.json" --output-dir "客户目录/正式输出/客户PDF"
```

`--report`、`--output-dir`必填；默认`--kind both`，另可选diagnosis或execution。诊断可独立生成；执行需要plan，项目取`--project`或analysis.project。提供analysis时预算须和当前计划一致，实际参数用`--help`核对。

客户PDF目录只新增两PDF。PNG与审计自动放report同级pdf-review（通常在.work），结果返回review_dir和audit；直接使用技能示例时放输出父目录.work，不写回技能。同名成果拒绝覆盖，使用新版本目录。

背景与schema由assets/report-assets-manifest.json按字节数及SHA256封版。客户生成只改数据，溢出时精简重复表达，不换模板、不截字、不缩字号或自动增页。导出后逐页看17张实际画面，核固定标题、表格、三类卡、分工、双档费用和中文；再核全部数量和服务范围，文本提取不能替代视觉。

公开仓库只放清除客户文字的背景、配套资源和虚构示例，真实客户PDF、截图、回答和本地审计不上传。修改skill以虚构资料验证，不重做客户旧报告。本地渲染、迁移安装和WorkBuddy界面实测分别记录。
