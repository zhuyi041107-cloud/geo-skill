# 数据与本地执行命令

WorkBuddy直接完成问题设计、原答判读、品牌分析、分类方案、客户成稿和另轮自审。本地脚本只处理表格、统计、费用和模板填充，不调用模型或联网服务；无需MCP、API密钥或GPT终审。

替换“技能目录”和“工作目录”为实际路径，保留路径引号。Python须为3.10或更新版；只安装基础依赖：

```text
python -m pip install -r "技能目录/requirements.txt"
```

客户资料、原答、内部JSON和核算放客户工作目录，不写入技能目录。原件及旧成品不覆盖，重做使用新的版本目录和文件名。JSON为UTF-8。

## 1. 读取资料与生成采集表

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/.work/client-fields.json"
python "技能目录/scripts/geo_data.py" prepare --project "工作目录/.work/project.json" --out "工作目录/豆包-AI回答采集表.xlsx"
```

WorkBuddy按[project.example.json](project.example.json)填写本案project，问题按[问题生成流程](workflow.md)筛选，三列表只含问题、引用截图和答案。`budget_target`只记录意向预算；只有明确不能超过时设`budget_limit`。未确定的项目起止日期不冒称已确认。按平台可用`--out-dir`生成多份表，收到任一平台即可继续，不强制补采。

## 2. 导入、读取原答与截图

```text
python "技能目录/scripts/geo_data.py" normalize --input "工作目录/豆包-AI回答采集表.xlsx" --project "工作目录/.work/project.json" --context 1 --out "工作目录/.work/内部原答-豆包.xlsx"
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部原答-豆包.xlsx" --out "工作目录/.work/analysis-raw.json"
```

可用`--base`合并另一平台。图片偏到相邻列按问题行处理，原件保留。读取analysis-raw中的完整`samples`与`citations`，实际打开`回答证据路径`、`证据路径`和`project.unlocated_screenshots`所指的截图；不能只看统计或截断后的摘要。长回答按表中附件路径读取完整文本。没有完整URL仍可分析可见站点、标题和来源结构，不强制补模式、时间或其他平台。

## 3. WorkBuddy直接判读并保存副本

按每条已完成且有完整回答的`sample_id`，WorkBuddy判读品牌提及、明确推荐和具体理由，写入`.work/judgments.json`。提及不等于推荐，点名介绍不等于自然候选；知识建议题没出现品牌不自动算推荐失败。结构为列表，每项恰好四字段：

```json
[
  {
    "sample_id": "从analysis-raw逐项复制实际ID",
    "mention": "是",
    "recommendation": "否",
    "reason": "原答介绍品牌服务，没有将其列为可选择的机构。"
  }
]
```

`mention`和`recommendation`只允许“是／否”，推荐必须同时提及；理由对应原答，覆盖所有成功回答且不重复、不加虚构ID。运行本地命令写入新副本，再计算已判统计：

```text
python "技能目录/scripts/geo_data.py" judge --input "工作目录/.work/内部原答-豆包.xlsx" --judgments "工作目录/.work/judgments.json" --out "工作目录/.work/内部判读-豆包.xlsx"
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部判读-豆包.xlsx" --out "工作目录/.work/analysis-judged.json"
```

judge只写入已给判读，不调用模型；随包的gpt_evidence.py仅是复用的本地读写与校验模块。未判记录不能冒充已判结果。来源无URL不妨碍业务分析，不能据此编造已核验引用率。

## 4. 分类计划与预算

读[报告分析思路](report-thinking.md)及[证据与规划](evidence-and-planning.md)，WorkBuddy按[plan-category.example.json](plan-category.example.json)的结构填写本案`.work/plan.json`。示例的业务、篇数、阶段和日期均须按本案重写，不能整份照抄。本版不检索具体媒体，不生成媒体推荐表。

`plan_mode=category_only`；每项placement包含内容ID、传播类别、用途依据、计划刊次、日期与客户单价，不包含媒体名、媒体ID、来源或采购价。三类为权威媒体、行业媒体、自媒体；两档同内容、类别和刊次，具体媒体与实际权益差异待确认。

主plan为普通档，高权重在`quote_options`，两档类别报价分别为450／200／200元和600／300／300元每次。每档计划媒体费最低12,000元，写作另收费，默认原价200元／篇、打包100元／独立稿；客户供稿不收写作费。基本服务和客户分工来自`service_scope`。明确硬预算约束适用于媒体与写作总额，意向预算不自动转为上限。最终导出会核算数量、费用和一致性，报错时修正实际计划，不改校验器绕过。

计划完成后，用同一plan生成含预算的最终分析，再用于PDF导出：

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部判读-豆包.xlsx" --plan "工作目录/.work/plan.json" --out "工作目录/.work/analysis-final.json"
```

## 5. 填充固定模板

完整阅读[逐页生成说明](template-generation.md)与[PDF契约](pdf-output.md)，按[客户配置示例](report.example.json)及[schema](customer-report.schema.json)填写本案`.work/report.json`。report只含客户可见内容；不照搬示例客户文字，不手填自动核算字段。导出内部草稿：

```text
python "技能目录/scripts/export_pdf.py" --analysis "工作目录/.work/analysis-final.json" --plan "工作目录/.work/plan.json" --report "工作目录/.work/report.json" --output-dir "工作目录/.work/草稿-v1/客户PDF"
python "技能目录/scripts/check_client_report.py" "工作目录/.work/草稿-v1/客户PDF/GEO诊断报告.pdf"
python "技能目录/scripts/check_client_report.py" "工作目录/.work/草稿-v1/客户PDF/品牌传播与GEO执行方案.pdf"
```

若改动plan，先用同一plan重新analyze生成新的analysis，再导出，不能混用旧预算。保留原背景、坐标、字号和1200×675页面；文字溢出时精简表述，不缩字、截断、增页或改模板。两档价格、三类数量及双方分工由同源plan注入。已有同名PDF会拒绝覆盖；修改后用草稿-v2等新目录。

## 6. 另轮自审与交付

读取导出结果的`audit`及`review_dir`，另轮按生成说明核事实、分析、三类用途、数量、费用与分工；实际逐页查看诊断8张、执行9张PNG，对照随包两份版式示例PDF。文字检查清零不代替语义与页面检查，不能声称外部GPT已审。

修正后重导并复查变动页、关联汇总和费用页；通过后只把两份已审PDF复制到新的正式输出目录，核复制前后文件一致。JSON、判读、截图、PNG、审计及核算留.work。不生成客户Excel、PPT或推荐表，不要求用户补URL、模式、联网和其他平台才交付。
