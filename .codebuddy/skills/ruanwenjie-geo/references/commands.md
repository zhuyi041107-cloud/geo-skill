# 数据与命令

## 对外只交三列表

业务同事只填写“问题、引用截图、答案”。每个AI平台一份文件，平台放在文件名里；其余字段内部处理。收到任意平台回传后直接完成本轮诊断报告和执行方案文件，不等齐平台、不先停在聊天判读摘要。下面的命令都是内部步骤，不向用户讲解操作流水账。

以下命令由WorkBuddy执行。替换“技能目录”为实际安装路径，“工作目录”为客户独立文件夹；使用当前环境的Python命令，路径加引号。先检查 `python -c "import openpyxl, pptx"`；需要安装依赖时按环境权限使用本包requirements.txt。

## 1. 客户资料与核心问题

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/client-fields.json"
```

WorkBuddy据实际业务维护project.json，参考 [虚构项目格式](project.example.json)。问题先通过工作流程中的真实需求、具体诊断用途和信息增量判断；题数由有效场景决定，不设固定数量，不照搬示例题或按分类凑行业科普问卷。自然需求与点名认知/口碑/对比在内部分类。

project主要字段：

- project_id、client_name、brand_names；可选industry、services、regions、audience、advantages、competitors、public_sources。
- questions：每项question_id、type（自然需求/品牌认知）、intent（认知/推荐/决策/对比/其他）、theme、text、priority。
- contexts：每项platform、mode、online、round。默认沿用用户约定：mode为网页端，online为是，日期为当前本轮日期；原材料有明确记录时优先保留。具体模型名不臆造，也不要求用户逐行填模式或联网。
- repeats：初轮通常1。budget_limit与执行start_date/end_date未知时为null；金额以十进制字符串保存。
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
python "技能目录/scripts/media.py" --input "工作目录/最新媒体报价.xlsx" --tier "普通会员" --query "科技" --region "山西" --kind network --limit 30 --out "工作目录/media-candidates.json"
```

支持network/self/all。明确拒收GEO的资源排除；内容形态限制和未知属性标需核实。结果附软文街id、文件、sheet、行号、原价及备注。候选不是已选媒体，也不是AI引用能力排名。

## 5. 计划与预算

参见 [虚构计划格式](plan.example.json)。contents记录内容ID、标题、目标问题、事实依据、排期与状态；placements记录媒体、原价来源、单价、刊发次数、对客单价和日期；fees记录其他费用。内部价与对客价分别填，未知为null。已选/待执行/已发布计入预算；候选/取消/排除不计。一个内容多站刊发只计一篇内容，刊发次数独立求和。

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/内部判读-豆包.xlsx" --plan "工作目录/plan.json" --out "工作目录/analysis-final.json"
python "技能目录/scripts/geo_data.py" export-excel --project "工作目录/project.json" --analysis "工作目录/analysis-final.json" --plan "工作目录/plan.json" --out-dir "工作目录/正式输出"
```

输出内外两份Excel并继续导出PPT，不以聊天摘要结束。优先使用会话已有报价与预算；缺价项写在文件中，仍给出内容、媒体组合和排期。客户结果只用明确的对客价；缺价时总额未知，known_subtotal显示已知小计，missing_count显示缺项数。修改计划后重算再导出。

## 6. 客户PPT

由WorkBuddy按证据维护report.json叙述，使用 [PPT导出说明](ppt-output.md) 生成两份PPT。统计与预算读取analysis，不在叙述中另填数字。截图支持的观察与网页正文已核验的事实分开标明；没有证据不写全网结论或效果保证。

两份PPT与内外两份Excel实际生成并检查后才交付。聊天只给成品文件链接及简短说明，具体不确定事实留在文件中；不展示导入/锚点/内部JSON过程，不再列补平台、模式或时间的待办。
