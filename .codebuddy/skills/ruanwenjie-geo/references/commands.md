# 数据与本地执行命令

WorkBuddy直接完成问题设计、原答判读、品牌分析、执行计划、客户成稿和另轮自审。本地脚本处理表格、统计、关联校验、费用核算与PDF渲染；全流程无需MCP、API密钥或GEO云端工具。

替换“技能目录”和“工作目录”为实际路径，保留路径引号。Python须为3.10或更新版：

```text
python -m pip install -r "技能目录/requirements.txt"
```

客户资料、原答、内部JSON与核算放客户工作目录，JSON为UTF-8。原件及旧成品保留；修改后使用新的版本目录。以下1—3步继续使用三列人工采集流程，4—6步使用品牌版schema3.0。

## 1. 读取资料与生成三列采集表

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/.work/client-fields.json"
python "技能目录/scripts/geo_data.py" prepare --project "工作目录/.work/project.json" --out "工作目录/豆包-AI回答采集表.xlsx"
```

WorkBuddy按[project.example.json](project.example.json)填写本案project，按[问题生成流程](workflow.md)选择真正影响客户业务选择的问题。采集表只含问题、引用截图和答案，用户在AI网页端手工收集。`budget_target`只记录意向预算；明确不能超过时才填写`budget_limit`。按平台可用`--out-dir`生成多份表，收到任一平台即可继续。

## 2. 导入并读取完整原答与截图

```text
python "技能目录/scripts/geo_data.py" normalize --input "工作目录/豆包-AI回答采集表.xlsx" --project "工作目录/.work/project.json" --context 1 --out "工作目录/.work/内部原答-豆包.xlsx"
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部原答-豆包.xlsx" --out "工作目录/.work/analysis-raw.json"
```

可用`--base`合并另一平台。图片偏到相邻列按问题行处理，原件保留。读取analysis-raw的完整`samples/citations`，实际打开`回答证据路径`、`证据路径`和`project.unlocated_screenshots`所指截图；长回答按附件路径读取完整文本。没有完整URL仍可分析可见站点、标题与来源结构，不强制补模式、时间或其他平台。

## 3. WorkBuddy判读并保存副本

按每条成功且有完整回答的`sample_id`判读品牌提及、明确推荐和理由，写入`.work/judgments.json`。提及不等于推荐，点名介绍不等于自然候选；知识建议题未出现品牌不自动算推荐失败。列表每项恰好四字段：

```json
[
  {
    "sample_id": "从analysis-raw复制实际ID",
    "mention": "是",
    "recommendation": "否",
    "reason": "原答介绍品牌服务，没有将其列为可选择的机构。"
  }
]
```

`mention/recommendation`只允许“是／否”，推荐须同时提及。覆盖全部成功回答，不重复、不新增虚构ID；理由对应原答。写入新副本，再计算已判统计：

```text
python "技能目录/scripts/geo_data.py" judge --input "工作目录/.work/内部原答-豆包.xlsx" --judgments "工作目录/.work/judgments.json" --out "工作目录/.work/内部判读-豆包.xlsx"
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部判读-豆包.xlsx" --out "工作目录/.work/analysis-judged.json"
```

judge只写入已给判读，不调用模型；随包`gpt_evidence.py`仅用于本地读写与校验。未判结果不计作已判，来源无URL不编造已核验引用率。新流程中analyze只用于统计，**不将新品牌plan传入旧`--plan`参数**，也不从其旧预算字段生成报价。

## 4. 建立诊断—动作—分工—报价计划

完整读[分析思路](strategy-playbook.md)、[证据与规划](evidence-and-planning.md)及[PDF契约](pdf-output.md)。按[品牌计划示例](brand-plan.example.json)在`.work/plan.json`填写本案的`evidence/findings/actions/service_scope/pricing`。示例仅为虚构结构验证，重写客户事实、证据、优先级、稿量、阶段和价格。

每项诊断有证据、业务影响和对应动作；执行工作有负责方、客户配合、交付物及复核方向。媒体按权威媒体、行业媒体、自媒体说明各自用途，客户官方更新与配合另列实际任务。有证据才设竞品、冲突或舆情模块；与本案无关的模块省略。

`pricing.instructions`记录本次报价指令；单档或多档、明确单价×数量或整包价、税费、服务已含与另计、供稿与写作均按本次约定。`budget_target`作意向参考，`budget_limit`才是硬上限；两处内部project/pricing上限须按最新指令一致。缺价使用`unquoted`，不能用零元或意向预算冒充报价。旧版固定两档、媒体最低费及写作单价不自动带入新方案。

本地导出时按Decimal核算并校验重复收费、未说明范围、无效数量和硬上限。整包已含的工作与另收费工作使用清晰、不重叠的scope；分项合计与客户页报价同源。校验报错时修正实际计划，不绕过校验。

## 5. 按客户品牌组织模块并导出

读[版式生成说明](template-generation.md)，按[品牌报告示例](brand-report.example.json)及[3.0 schema](brand-report.schema.json)填写`.work/report.json`。选择本品牌主题和章节，不设固定页数。必须的源模块、可用layout与字段见[PDF契约](pdf-output.md#4-必须从计划注入的源模块)：诊断呈现全部发现；执行呈现高优先级发现、全部动作、分工与已核报价。

```text
python "技能目录/scripts/export_pdf.py" --plan "工作目录/.work/plan.json" --report "工作目录/.work/report.json" --output-dir "工作目录/.work/草稿-v1/客户PDF"
python "技能目录/scripts/check_client_report.py" "工作目录/.work/草稿-v1/客户PDF/GEO诊断报告.pdf"
python "技能目录/scripts/check_client_report.py" "工作目录/.work/草稿-v1/客户PDF/品牌传播与GEO执行方案.pdf"
```

入口默认生成两PDF，也可用`--kind diagnosis`或`--kind execution`单独导出。品牌诊断需要有证据的plan，执行需要完整plan；无需先带新plan运行analyze。可按需加`--project "工作目录/.work/project.json"`，或`--analysis "工作目录/.work/analysis-judged.json"`交叉核项目；同时传两者时其project内容须一致。新报价始终来自`plan.pricing`，不继承旧analysis预算。

`source=findings/action-map/service-scope/quotes`从plan注入客户内容，内部ID被移除。`findings/action-map`可用`ids`拆分指定条目，报价与分工完整显示。自由模块用来解释业务情况、分析与策略，费用与计费数量放pricing，由quotes源模块输出。

导出会自动分页并返回实际页数、`audit`和`review_dir`；同名PDF拒绝覆盖。内容修正后用草稿-v2等新目录。客户PDF目录只放`GEO诊断报告.pdf`、`品牌传播与GEO执行方案.pdf`，预览与审计留内部目录。

## 6. 另轮全页自审与交付

读取导出结果中两个audit的全部`rendered_pages`，实际逐张打开全部PNG，不按旧固定页数抽查。确认品牌主题合适、字可读、标题有层次、表格续页完整、无截字遮挡；再逐项核证据与分析、诊断动作对应、三类媒体用途、执行范围、分工、供稿、各档价格及合计。客户正文只写情况、分析与安排，不出现采集、制作或工具过程话术。

文本检查清零后仍完成语义和视觉自审。修正后重新导出，查看全部新画面及关联汇总；通过后仅把两份已审PDF复制到新的正式输出目录，并核复制前后文件一致。判读表、内部JSON、截图、预览、审计及核算留`.work`。不生成额外客户Excel或PPT，不要求补其他平台才交付；也不声称已做外部模型审核或WorkBuddy安装实测。