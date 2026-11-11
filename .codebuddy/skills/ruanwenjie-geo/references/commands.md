# 数据与命令

问题由WorkBuddy根据客户资料生成，同事到AI网页端提问并回传三列表。回答后的GPT分析、分类方案、成稿和终审按[本地MCP执行](local-mcp.md)调用。本页命令用于资料导入及维护验证；不自动采集、监测或购买媒体。

替换“技能目录”和“工作目录”为实际路径，保留路径引号。Python须为3.10或更新版；安装依赖：

```text
python -m pip install -r "技能目录/requirements-mcp.txt"
```

客户资料、原答、内部JSON和核算放客户工作目录，不写入技能目录。原件及旧成品不覆盖。

## 1. 读取资料与生成采集表

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/.work/client-fields.json"
python "技能目录/scripts/geo_data.py" prepare --project "工作目录/.work/project.json" --out "工作目录/豆包-AI回答采集表.xlsx"
```

project结构参考[project.example.json](project.example.json)。问题按[问题生成流程](workflow.md)筛选，三列表只含问题、引用截图和答案。`budget_target`只记录意向预算；只有明确不能超过时设`budget_limit`。未确定的项目起止日期不冒称已确认。按平台使用`--out-dir`生成多份表。

## 2. 导入和内部判读

```text
python "技能目录/scripts/geo_data.py" normalize --input "工作目录/豆包-AI回答采集表.xlsx" --project "工作目录/.work/project.json" --context 1 --out "工作目录/.work/内部判读-豆包.xlsx"
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部判读-豆包.xlsx" --out "工作目录/.work/analysis.json"
```

可用`--base`合并另一平台回答。图片偏到相邻列按问题行处理，原件保留；收到任意平台即可分析，不强制补URL、模式或其他平台。本地MCP根据完整原答与截图生成内部GPT判读副本。

## 3. 分类计划与预算

本版不检索具体媒体，也不生成媒体推荐表；调用`geo_create_plan(run_dir)`按实际客户需求生成内容、阶段、三类传播角色与计划刊次。虚构结构参考[plan-category.example.json](plan-category.example.json)：`plan_mode=category_only`；每项placement包含内容ID、传播类别、用途依据、计划刊次、日期与客户单价，不包含媒体名、媒体ID、来源或采购价。两档同内容、类别和刊次，具体媒体与实际权益差异待确认。

主plan为普通档，高权重在`quote_options`，两档类别报价分别为450／200／200元和600／300／300元每次。每档计划媒体费最低12,000元，写作另收费；基本服务和客户分工从`service_scope`同源计算。明确的硬预算约束适用于媒体与写作总额，意向预算不自动转为上限。

## 4. 固定背景填充两份PDF

直接脚本仅供维护者在内部目录排查模板；客户任务使用geo_write_reports、geo_review_deliverables和geo_publish，不绕过终审。完整阅读[逐页生成说明](template-generation.md)与[PDF契约](pdf-output.md)，参考[客户配置示例](report.example.json)及[schema](customer-report.schema.json)。

```text
python "技能目录/scripts/export_pdf.py" --project "技能目录/references/project.example.json" --plan "技能目录/references/plan-category.example.json" --report "技能目录/references/report.example.json" --output-dir "工作目录/.work/维护草稿/客户PDF"
```

保留原背景、坐标、字号和1200×675页面；文字溢出时精简表述，不缩字、截断、增页或改模板。两档价格、三类数量及双方分工从同源plan注入。终审逐页核8页诊断与9页执行，审核通过且文件未变时geo_publish才交付两份PDF，内部JSON、判读与核算留.work。
