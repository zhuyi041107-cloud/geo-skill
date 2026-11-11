# 数据与命令

本 skill 只使用本地 Python、随包模板与媒体目录。问题由 WorkBuddy 根据客户资料生成；同事到 AI 网页端提问并回传三列表。GEO 云端工具、自动问答采集、付费查询与监测服务不属于本流程。

替换下面的“技能目录”为安装路径、“工作目录”为客户文件夹。路径始终加引号；使用当前环境可用的 Python 3.10 或更新版本。客户资料、原答、内部 JSON 与核算放客户目录，不写回技能目录。

先检查依赖：

```text
python -c "import openpyxl, docx, fitz, reportlab"
python -m pip install -r "技能目录/requirements.txt"
```

仅缺依赖时运行安装命令。PDF 使用随包字体、空白背景和图标，无需浏览器、Node 或 GEO 连接器。既有成品保留；输出同名文件被拒绝时直接选择新的修订目录。

## 1. 读取客户资料与生成问题

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/.work/client-fields.json"
```

WorkBuddy 据资料维护 `.work/project.json`，结构参考 [project.example.json](project.example.json)。提取品牌、运营主体、服务、客群、地域、优势、竞品和推广目标。问题按 [问题生成流程](workflow.md) 筛选：每题影响具体业务判断，相近问法合并，不按数量或分类凑题。

内部字段：

- `project_id`、`client_name`、`brand_names`；可补 `industry`、`services`、`regions`、`audience`、`advantages`、`competitors`、`public_sources`。
- `questions` 每项含 `question_id`、`type`（自然需求/品牌认知）、`intent`（认知/推荐/决策/对比/其他）、`theme`、`text`、`priority`。
- `contexts` 每项含 `platform`、`mode`、`online`、`round`。沿用用户约定：网页端、联网、本轮日期；有明确历史记录则保留。模式、时间、模型名不转成同事必填项；不编造时分秒。
- `budget_target`、`budget_limit` 未另给要求时均为 `"20000.00"`；`currency` 为 `CNY`。金额用十进制字符串。明确只给上限、允许少花时目标可为 null。
- `start_date`、`end_date` 写建议执行期；年度安排区分已计费建设与后续维护，不能把未报价的全年服务写成已含。
- `repeats` 初轮通常为 1。内部 ID、分类和日期由 WorkBuddy 维护。

## 2. 交付三列采集表

```text
python "技能目录/scripts/geo_data.py" prepare --project "工作目录/.work/project.json" --out "工作目录/豆包-AI回答采集表.xlsx"
```

多个平台使用 `--out-dir "工作目录/待采集"` 替代 `--out`，按平台分别生成。人工表只有“问题、引用截图、答案”：问题预填，同事填写截图与完整回答，平台写文件名。截图可嵌入单元格，或写附件路径；长答案可另存文本并注明位置。无来源填“未展示”。不另要求手抄 URL 或填写模式、联网与时间。

问题表交付后等待回传，WorkBuddy 不自动到各 AI 平台执行提问。

## 3. 导入已有回答并内部判读

```text
python "技能目录/scripts/geo_data.py" normalize --input "工作目录/豆包-AI回答采集表.xlsx" --project "工作目录/.work/project.json" --context 1 --out "工作目录/.work/内部判读-豆包.xlsx"
```

`context` 为 `project.contexts` 的 1 起始序号或唯一平台名。平台从文件名和会话识别，不明确时用“本次回传平台”继续。图片偏到相邻列按问题行兼容处理，原件保持不变。

收到任意一个平台就完成本轮全部成品。已判读资料直接复用，不要求补平台或重采。后来回传其他平台时，可用 `--base "工作目录/.work/内部判读-豆包.xlsx"` 增量合并。未回传平台不列 0、不算缺项。

内部底表使用 `references/内部判读底表.xlsx`。WorkBuddy 判读品牌提及、推荐及可见引用；来源记录网站、标题、支持内容和证据位置。有 URL 才填 URL，截图没有 URL 仍可分析可见来源结构，具体正文支持性保持待核验。

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部判读-豆包.xlsx" --out "工作目录/.work/analysis.json"
```

内部统计区分自然需求和点名认知。客户稿使用情况与影响表述；具体主体、资质、收费或案例未确认，在对应事实旁简短说明，不追加采集过程或通用样本免责声明。

## 4. 按随包报价广泛选媒

```text
python "技能目录/scripts/media.py" --query "科技" --region "山西" --kind network --limit 0 --out "工作目录/.work/media-network-candidates.json"
python "技能目录/scripts/media.py" --query "职场" --region "山西" --kind self --limit 0 --out "工作目录/.work/media-self-candidates.json"
```

默认读取 `references/media-catalog.csv.gz`。业务、受众、地域、题材分别检索，检查 `truncated=false`，筛选并去重全部相关结果；不能只读默认前 30 条。明确拒发排除，条件资源保留限制。推荐数量与资源标价总额不受执行预算限制。

用户有更新报价时可用 `--input` 指定 XLSX，`--tier` 选其原档位；没有更新文件也可使用随包目录完成。六档价格保留原值，不推导采购价、折扣或成本。

## 5. 形成内部执行计划与核算

参考 [plan.example.json](plan.example.json)。先从诊断事实形成业务场景和品牌选择理由，再确定内容组、信源分工、阶段交付和费用。

- `stages` 写 `name`、`objective`、`deliverables`、`effect_target`。
- `contents` 为核算用内容任务，含 `content_id`、`title`、`question_ids`、`content_group`、`stage`、`scheduled_date`、`status`；`content_group` 使用具体业务方向名称，供内容规划页匹配同名组并自动计篇。可补关键词、事实依据、内容形式、信源角色与检查日。售前报告汇总方向、篇数和阶段，不把内部逐篇任务表完整打印给客户。
- `placements` 只放实际执行子集，含资源身份、原报价来源、刊发次数、日期与对客单价；其他费用放 `fees`。同稿多站发布计 1 篇内容、多次刊发，默认一稿一发，额外分发有明确约定才安排。
- `media_recommendations` 是独立的宽推荐池，至少含 `media_id`、`media_name`、`source_sheet`，可沿用目录字段并补推荐理由。状态为推荐、候选或需核实；不需要刊次或执行金额，不回退用 placements 代替。
- `logic_links` 留内部，串联诊断发现、事实依据、选择理由、内容或客户动作、媒体角色、阶段与检查日。内容、媒体和投入要解决对应缺口，共享任务只计费一次。

使用目录建议价时，`unit_price` 保留 null，`client_unit_price` 填市场参考价，同时保留 `price_tier=市场价格`、`quotation_date` 和清楚的 `price_basis`；只有已确认客户报价才替换。未报价的写作、页面建设、复核和维护不作为已含刚性交付。

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/.work/内部判读-豆包.xlsx" --plan "工作目录/.work/plan.json" --out "工作目录/.work/analysis-final.json"
```

默认实际执行已知费用为 18,000—20,000 元。目标与上限来自本轮明确要求；不抬价或虚加差额凑预算。推荐池不计入预算。执行 PDF 重新计算计划并检查上限与目标，提供 analysis 时还会核对预算一致性。

## 6. 固定背景填充两份客户 PDF

完整阅读 [逐页生成说明](template-generation.md) 与 [PDF 契约](pdf-output.md)，参考 [客户配置示例](report.example.json) 及 [schema](customer-report.schema.json)。客户成稿 JSON 独立组织，根包含 `schema_version: "2.0"`、`customer`、`purpose`、`diagnosis.pages`（8 页）、`execution.pages`（9 页）；不混入原答、截图、内部映射和核算台账。

```text
python "技能目录/scripts/export_pdf.py" --analysis "工作目录/.work/analysis-final.json" --plan "工作目录/.work/plan.json" --report "工作目录/.work/report.json" --output-dir "工作目录/正式输出/客户PDF"
```

入口只填固定文字槽与数据区，保留原背景、坐标、字号和 1200×675 页面。文字溢出时精简客户表述，不缩字、截断、增页或改模板。执行金额和数量按同源 plan 注入；单套计划只显示一套真实报价。详细字段与运行选项以随包 `--help` 和 schema 为准。

## 7. 推荐媒体 Excel

```text
python "技能目录/scripts/export_media_word.py" --analysis "工作目录/.work/analysis-final.json" --plan "工作目录/.work/plan.json" --output "工作目录/正式输出/推荐媒体.xlsx"
```

沿用 [原媒体表规范](media-word-output.md) 和 `templates/推荐媒体模板.xlsx`，只交一个工作簿：sheet1 网络媒体、sheet2 自媒体，原 16/17 列、分组、配色与六档价格保持。脚本名为兼容旧使用保留，默认 `.xlsx` 输出；不另交 Word。

## 8. 验收与交付

逐页检查 8 页诊断与 9 页执行：客户逻辑、事实、费用、模板位置、完整文字与无重叠裁切；打开或渲染两张媒体 sheet 核对资源归类、推荐完整性与六档原价。只给客户两份 PDF 和推荐媒体.xlsx，内部 JSON、判读与核算留 `.work`。

判读工作簿和 analysis/plan JSON 留在内部即可；本版已移除旧的诊断/执行明细 Excel 导出链路，不将内部底稿另包装为客户附件。
