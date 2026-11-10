# 数据与命令

## 对外只交三列表

业务同事只填写“问题、引用截图、答案”。每个AI平台一份文件，平台放在文件名里；其余编号、模式、轮次、证据关联和判读均由WorkBuddy内部处理。不要把内部判读底表交给用户填写。

以下命令由WorkBuddy执行。替换“技能目录”为实际安装路径，“工作目录”为客户独立文件夹；使用当前环境的Python命令，路径加引号。先检查 `python -c "import openpyxl, pptx"`；需要安装依赖时按环境权限使用本包requirements.txt。

## 1. 客户资料与核心问题

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/client-fields.json"
```

WorkBuddy据实际业务维护project.json，参考 [虚构项目格式](project.example.json)。问题先通过工作流程中的真实需求、具体诊断用途和信息增量判断；题数由有效场景决定，不设固定数量，不照搬示例题或按分类凑行业科普问卷。自然需求与点名认知/口碑/对比在内部分类。

project主要字段：

- project_id、client_name、brand_names；可选industry、services、regions、audience、advantages、competitors、public_sources。
- questions：每项question_id、type（自然需求/品牌认知）、intent（认知/推荐/决策/对比/其他）、theme、text、priority。
- contexts：每项platform、mode、online（是/否/未知）、round。用户只选平台即可，其余未知使用“未记录/未知”，不要替用户假设联网或模型。
- repeats：初轮通常1。budget_limit与执行start_date/end_date未知时为null；金额以十进制字符串保存。
- 有确切采集时间或新对话确认时，可在normalize阶段填写；不知道则保留未知，不作为交付采集表的前置条件。

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

`import-collection`是同一命令的别名。context采用project.contexts中的1起始序号；脚本也支持唯一平台名时，以实际CLI帮助为准。文件名已经能确定平台就直接匹配；无法确定只补问一次。

汇入其他平台时，使用上一份内部底表作为base，生成新的合并底表，不覆盖已采答案：

```text
python "技能目录/scripts/geo_data.py" normalize --base "工作目录/内部判读-豆包.xlsx" --input "工作目录/DeepSeek-AI回答采集表.xlsx" --project "工作目录/project.json" --context 2 --out "工作目录/内部判读-全部平台.xlsx"
```

最后对合并底表运行analyze，平台分别统计并进入同一套交付文件。

normalize按题目对应内部ID，保留原文，提取嵌入截图并记录行关联；截图附件内容不会凭文件名推断。原始三列表不覆盖，生成内部判读底表仅供WorkBuddy使用。旧版包含项目配置/问题清单/回答记录/引用明细的采集结果仍可直接analyze，无需让同事重填。

内部底表位于references/内部判读底表.xlsx。WorkBuddy只在此维护：

- 回答记录：品牌提及/推荐（是、否、待判）、引用展示（已展示、未展示、待核验、不适用），并保留原回答与截图证据位置。
- 引用明细：截图可见网站、标题、支持内容、核验状态与证据位置。有完整URL时才填写URL；没有URL但有截图时可保留待核验，不能伪称已查证正文。
- 时间或新对话状态未知，记录未知；已知未使用新对话才列为可比条件异常。用户不需要补填这些字段。

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/内部判读-豆包.xlsx" --out "工作目录/analysis.json"
```

重复ID、问题无法对应、无证据的孤立引用等按错误处理，不静默丢数据。analysis保留project、groups、counts与证据。未知条件的样本可做本轮描述性观察；明确不符条件单列。自然题和点名题分别统计，小样本优先显示“出现次数/有效数”。来源未核验时引用指标保持未知，不把截图来源名拼成想象的URL。

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

输出内外两份Excel。内部结果保留原价及档位；客户结果只用明确的对客价。缺价时总额未知，known_subtotal显示已知小计，missing_count显示缺项数；季度按实际执行日期归属。修改计划后重算再导出。

## 6. 客户PPT

由WorkBuddy按证据维护report.json叙述，使用 [PPT导出说明](ppt-output.md) 生成两份PPT。统计与预算读取analysis，不在叙述中另填数字。截图支持的观察与网页正文已核验的事实分开标明；没有证据不写全网结论或效果保证。

客户输出是生成时快照，输入变化后导出新版本。文件保留明确的待采集/待报价/待核验状态；交付前检查所有页、金额和证据关联。
