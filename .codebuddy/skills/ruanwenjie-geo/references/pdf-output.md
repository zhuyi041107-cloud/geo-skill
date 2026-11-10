# 客户PDF交付

客户交付为两份业务PDF：`GEO诊断报告.pdf`、`品牌传播与GEO执行方案.pdf`。由 `scripts/export_pdf.py` 直接排版生成，不经过PPT，不沿用方法页或采样教程。

WorkBuddy负责依据本轮客户材料、回答与截图形成判断和方案。导出脚本负责排版、同源数字与预算检查，不代替业务分析。不要把示例中的虚构品牌、业务判断、媒体或金额直接用于真实客户。

## 叙述字段

推荐使用嵌套结构，参考 `references/report.example.json`。各章节采用 `[{"title":"业务判断标题","detail":"连续的情况说明与分析","evidence_ref":["内部证据索引"]}]`，摘要也可直接使用字符串。`detail`应说明本轮现状、原因或判断、业务影响与执行意义，而不是一句短标签。

| 诊断章节 | 应写的业务内容 |
| --- | --- |
| `diagnosis.summary` | 首屏核心判断、主要业务缺口与优先方向 |
| `diagnosis.brand_status` | 品牌已知情况、需求推荐表现及其业务意义 |
| `diagnosis.demand_entries` | 用户需求入口、品牌出现位置与未被承接的决策问题 |
| `diagnosis.competitors` | 本轮候选主体与用户选择逻辑，按实际证据分析 |
| `diagnosis.fact_consistency` | 品牌、主体、服务、资质、案例等事实的一致性 |
| `diagnosis.source_structure` | 本轮信息来源的结构、作用与未核实事实 |
| `diagnosis.key_findings` | 主要问题、成因、业务影响与优先级 |
| `diagnosis.priorities` | 适合该客户的优先结论与落地重点 |

| 执行章节 | 应写的业务内容 |
| --- | --- |
| `execution.summary` | 整体执行逻辑与投入重点 |
| `execution.objectives` | 品牌传播目标与GEO目标 |
| `execution.keywords` | 关键词或问题簇及业务用途 |
| `execution.content_strategy` | 内容方向、文章分工、需要承载的真实事实 |
| `execution.media_rationale` | 具体媒体组合的内容适配、受众与配置理由 |
| `execution.quarterly` | 各自然季度的目标、工作与调整安排 |
| `execution.expected_deliverables` | 预期交付、业务观察与合理效果方向 |
| `execution.client_actions` | 客户与执行方的业务协作重点 |

兼容旧顶层字段：`summary/scenarios/competitors/facts/sources/findings/priorities` 对应诊断；`objectives/keywords/content_strategy/media_rationale/quarterly/deliverables/targets/prerequisites` 对应执行。旧字段中的方法说明和操作教程不进入客户正文。新写作优先使用嵌套章节。

## 数字与实际资源

- 提及和推荐表现读取 `analysis.groups` 的已判计数，范围仅为本轮回传平台。客户报告只保留一行本轮范围，不列未回传平台，也不要求补其他平台。
- 实际选题、具体媒体、刊发次数、日期与季度费用来自 `plan.json` 和同源 `analysis.budget`。修改计划或报价后先重算分析文件，导出时会再次比对预算。
- 执行稿须有业务目标、已选内容和具体媒体名称。不能把“行业类媒体（待报价）”等占位写成已选资源。用资源目录中的实际媒体筛选结果生成组合。
- 对客费用读取 `client_unit_price`，不读取内部采购单价或报价档位。该字段既可采用明确的对客报价，也可采用资源目录市场参考价形成建议预算；后者必须在 `price_basis` 中标明依据，并将资源报价日期写入 `quotation_date`，不能称为已确认售价。PDF逐项原样列示价格依据与报价日期，缺字段不编造。
- 未提供年度预算时，可以形成按已选资源测算的建议媒体投放包；执行价格以当次确认条件为准。不编造稿件、官网建设等未列服务费用。
- 未明确的事实短标为未核验。缺价事实如实保留，但不要用一页空预算或许多“待采”代替方案。已经可以从本轮材料判断的情况，应直接说明并分析。

`evidence_ref`用于内部溯源，不打印进PDF。不要在 `title/detail` 中放问题编号、内容编号、媒体编号、源码路径或处理步骤。客户正文出现内部编号、路径、模板token或诊断教程时，脚本会拒绝导出，需由WorkBuddy改成业务语言。

## 导出与版式

在客户工作目录执行，将“技能目录”替换为安装路径：

```bash
python "技能目录/scripts/export_pdf.py" --analysis analysis.json --plan plan.json --report report.json --output-dir outputs/customer-pdf
```

默认同时生成两份PDF，可用 `--kind diagnosis` 或 `--kind execution` 单独生成。输入应来自同一项目；同名输出已存在时拒绝覆盖，使用新目录保留版本。

两份通用版式示例位于 `templates/GEO诊断报告版式示例.pdf`、`templates/品牌传播与GEO执行方案版式示例.pdf`，全部为虚构资料，由同一导出代码生成。版式采用A4纵向蓝色报告体，首屏直接给业务判断，正文与表格自然分页，不单独留大空白封面，也不硬凑固定页数。

中文字体随skill分发，覆盖源字体支持的CJK基本区、扩展A、兼容字及常用拉丁、标点、全角等字符；不是按示例客户文字裁剪的字体。许可证与来源说明在 `assets/fonts/`。消费端仅需 `reportlab` 及原有预算脚本依赖，不需要安装系统字体、fontTools、PPT软件或Codex运行时。

导出后检查所有页：叙述是否连贯且有依据，媒体与金额是否一致，表格是否跨页续表，文字是否完整，页码是否连续，是否遗留内部编号或空模板。文本提取、包结构或程序退出成功都不能替代逐页渲染检查。
