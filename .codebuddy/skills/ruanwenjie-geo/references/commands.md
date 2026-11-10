# 数据与命令

## 对外只交三列表

业务同事只填写“问题、引用截图、答案”。每个AI平台一份文件，平台放在文件名里；其余字段内部处理。收到任意平台回传后直接完成本轮诊断报告和执行方案文件，不等齐平台、不先停在聊天判读摘要。下面的命令都是内部步骤，不向用户讲解操作流水账。

以下命令由WorkBuddy内部执行。报告生成前完整读template-generation.md，并按客户类型读取template-contract.json对应profile；report-thinking.md约束证据判断。替换“技能目录”为安装路径，“工作目录”为客户独立文件夹；使用当前环境的Python，路径加引号。先检查 `python -c "import openpyxl, reportlab, pypdf, docx"`；按环境权限使用requirements.txt安装所需依赖。

下面输出目录是示意。旧成品已存在时保留旧文件，直接选择新版本目录（例如正式输出/修订1），不要求用户清空文件或重复确认覆盖。

## 1. 客户资料与核心问题

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/client-fields.json"
```

WorkBuddy据实际业务维护project.json，参考 [虚构项目格式](project.example.json)。问题先通过工作流程中的真实需求、具体诊断用途和信息增量判断；题数由有效场景决定，不设固定数量，不照搬示例题或按分类凑行业科普问卷。自然需求与点名认知/口碑/对比在内部分类。

project主要字段：

- project_id、client_name、brand_names；可选industry、services、regions、audience、advantages、competitors、public_sources。
- questions：每项question_id、type（自然需求/品牌认知）、intent（认知/推荐/决策/对比/其他）、theme、text、priority。
- contexts：每项platform、mode、online、round。默认沿用用户约定：mode为网页端，online为是，日期为当前本轮日期；原材料有明确记录时优先保留。具体模型名不臆造，也不要求用户逐行填模式或联网。
- repeats：初轮通常1。budget_target为本次建议执行目标、budget_limit为费用上限；本业务默认目标及上限均为"20000.00"，用户明确其他预算时覆盖。不要沿用旧project的null漏掉本轮目标。只有明确“仅上限、无需接近该金额”时目标可null。执行start_date/end_date按要求周期填写；年度方案覆盖全年，未给时由WorkBuddy形成建议日期。金额用十进制字符串。
- 缺少采集日期时由内部按本轮约定记录当前日期，不捏造精确时分秒。没有新对话记录不作为缺项、不催补；已明确的历史采样条件仍保留。

这些JSON和ID不是人工采集任务。

## 2. 生成三列采集表

单个平台/context：

```text
python "技能目录/scripts/geo_data.py" prepare --project "工作目录/project.json" --out "工作目录/豆包-AI回答采集表.xlsx"
```

多个平台/context时使用输出目录，脚本按平台/模式分别生成文件：

```text
python "技能目录/scripts/geo_data.py" prepare --project "工作目录/project.json" --out-dir "工作目录/待采集"
```

工作表只有“问题、引用截图、答案”三列，问题预填，另两列空白。向同事提供三句说明：按平台分文件，逐题新对话；粘贴来源截图和完整答案；回传表格与截图附件。没有来源写“未展示”，失败在答案中注明。不要额外要求手抄URL清单或采集条件。

截图可以直接嵌入Excel，也可以在单元格填附件名/路径。长答案超出单元格容量时另存文本附件并写明位置，保留完整原件。

## 3. 导入回传结果，内部判读

按对应project和context转成内部工作底表：

```text
python "技能目录/scripts/geo_data.py" normalize --input "工作目录/豆包-AI回答采集表.xlsx" --project "工作目录/project.json" --context 1 --out "工作目录/内部判读-豆包.xlsx"
```

`import-collection`是同一命令的别名。context采用project.contexts中的1起始序号，也支持唯一平台名。平台从文件名和会话直接识别，无法确认具体名称时用“本次回传平台”继续，不为标签停下追问。

收到一个平台就立即分析和导出全部成品。用户之后另行回传其他平台时，才使用上一份内部底表作为base增量更新，不覆盖已采答案：

```text
python "技能目录/scripts/geo_data.py" normalize --base "工作目录/内部判读-豆包.xlsx" --input "工作目录/DeepSeek-AI回答采集表.xlsx" --project "工作目录/project.json" --context 2 --out "工作目录/内部判读-全部平台.xlsx"
```

每次都对当前底表运行analyze并继续导出；只展示实际回传平台。未回传平台不列0、不算缺项，也不催用户补采。

normalize按题目对应内部ID，保留原文，按问题行关联截图；同一行图片偏到相邻列也接受。图片关联和必要兼容内部完成，原件不改，不要求同事修表。个别来源无法对应时留待核验并继续其他答案与完整报告。旧版内部底表也可直接analyze，无需重填。

内部底表位于references/内部判读底表.xlsx。WorkBuddy只在此维护：

- 回答记录：品牌提及/推荐（是、否、待判）、引用展示（已展示、未展示、待核验、不适用），并保留原回答与截图证据位置。
- 引用明细：截图可见网站、标题、支持内容、核验状态与证据位置。有完整URL时才填写URL；没有URL但有截图时可保留待核验，不能伪称已查证正文。
- 缺少日期或网页条件按本轮约定内部处理；新对话未记录不构成交付缺项。不要额外向用户索取模式、联网、时间、截图修正或其他平台数据。

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/内部判读-豆包.xlsx" --out "工作目录/analysis.json"
```

analysis保留内部原文与证据，本轮指标只统计已有回传的平台，自然题和点名题分开，小样本显示“出现次数/有效数”。截图可用于来源结构诊断；正文未核验的指标保留未知，但继续完成报告和执行文件。不把来源名拼成想象的URL，不自动开展额外采样。

## 4. 按报价选媒体

```text
python "技能目录/scripts/media.py" --query "科技" --region "山西" --kind network --limit 30 --out "工作目录/media-candidates.json"
```

默认读取随包references/media-catalog.csv.gz，支持network/self/all。明确拒收GEO的资源排除；结果带真实媒体、原记录索引、市场参考价、报价日期与脱敏限制。WorkBuddy按业务适配选用并写理由，不将候选排序当AI能力排名。内置market_price用于建议媒体发布预算，内部成本仍未知。

同一主题按价格区间检索，避免候选limit只返回最低价资源。例如重点媒体可先查 `--min-price 1000 --max-price 5000`，专业/地方媒体再查 `--min-price 200 --max-price 1000`；这些是查询示例，实际区间按预算与目录调整，选用仍需检查业务、地域和可发限制。价格高低不代表权威性或AI引用能力。

用户另提供原始更新报价时，可用--input指定.xlsx并以--tier指定其原档位；没有这份文件也能完成选媒，不催用户重复上传。具体媒体、实际刊发形态、数量和参考价写入计划，不能用TBD或类型占位替代。

## 5. 计划与预算

参见 [虚构计划格式](plan.example.json)。contents记录内容ID、标题、目标问题、事实依据、排期与状态；placements记录媒体、原价来源、单价、刊发次数、对客单价和日期；fees记录其他费用。内部价与对客价分别填，未知为null。已选/待执行/已发布计入预算；候选/取消/排除不计。一个内容多站刊发只计一篇内容，刊发次数独立求和。

- `stages`：每项name、objective、deliverables、effect_target。name与每篇已选contents.stage准确对应，写实际阶段目标、刚性交付和希望观察的变化。
- `contents`补全keywords、source_layer、content_form、key_facts、observation_port、checkpoint；target_question可写真实目标问题，否则由question_ids对应project.questions.text。周次从start_date与计划日期计算，阶段的周量/篇数/次数与费用自动汇总。
- `placements`保留media_type、source_sheet、source_row、media_id、category、region、entry_type、editorial_note及报价依据，既服务实际媒体明细，也用于原格式媒体Word。可选字段按media-word-output.md，未知不猜。
- 初期集中建设与后期维护应在同一年度计划中明确日期、内容、次数和计费范围；另期未计费维护不能写成全年已经包含。

使用内置目录时，`unit_price`保留null；将所选资源的`market_reference_price`填入`client_unit_price`计算建议预算，同时保留`price_tier=市场价格`、`quotation_date`与`price_basis=市场参考价，用于建议预算，执行价格另行确认`。只有已有明确客户报价时才用该报价替换对客单价。不要把全部价格留空，也不要凭空加价或补内部成本。

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/内部判读-豆包.xlsx" --plan "工作目录/plan.json" --out "工作目录/analysis-final.json"
python "技能目录/scripts/geo_data.py" export-excel --project "工作目录/project.json" --analysis "工作目录/analysis-final.json" --plan "工作目录/plan.json" --report "工作目录/report.json" --out-dir "工作目录/正式输出"
```

WorkBuddy先依据现状写report.json，内容与内置媒体选择形成plan，再重算并输出内外Excel。客户版只展示业务分析、关键词与内容排期、实际媒体、费用汇总；内部版保留溯源。内置市场参考价应明确用于建议预算，不自动视为已确认客户报价或内部成本。缺失服务费仅说明边界，不能让整份方案都是空价。

重算后的budget含target、target_source、limit。正式导出会检查已知费用至少达到明确目标的90%且不超过上限；默认约2万元方案不得缩水成两千元。检查失败时调整真实内容/媒体配置，不篡改单价、预算目标或增加虚构补差项。

## 6. 客户PDF

由WorkBuddy按 [原模板完整生成说明](template-generation.md) 撰写结构化report.json，使用 [PDF导出说明](pdf-output.md) 生成两份PDF。report.template_profile选择platform/service，diagnosis/execution各包含summary和完整sections；章节key、层级、原表头与source取对应contract。旧版泛叙述report需重新组织，不能直接套新排版。source=report的业务矩阵逐项写清；source=plan的数量/媒体/排期/预算由脚本计算；source=diagnosis的决策路径复用原诊断。内部编号和处理过程不进入正文。

```text
python "技能目录/scripts/export_pdf.py" --analysis "工作目录/analysis-final.json" --plan "工作目录/plan.json" --report "工作目录/report.json" --output-dir "工作目录/正式输出/客户PDF"
```

## 7. 推荐媒体Word

按 [原媒体表对应规范](media-word-output.md) 使用随包Word模板生成：

```text
python "技能目录/scripts/export_media_word.py" --analysis "工作目录/analysis-final.json" --plan "工作目录/plan.json" --output "工作目录/正式输出/推荐媒体.docx"
```

两份PDF、推荐媒体Word和内外Excel实际生成并检查后才交付。聊天只给成品与简短说明，不把内部JSON或方法当成客户分析，也不再列补平台、模式或时间的待办。
