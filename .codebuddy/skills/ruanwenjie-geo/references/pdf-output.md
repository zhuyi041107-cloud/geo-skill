# 品牌版PDF生成契约

新客户使用`schema_version: "3.0"`：按客户品牌、业务和本次诊断设计两份1200×675横版PDF，内容模块自动分页，页数随内容确定。WorkBuddy直接分析、成稿和另轮自审；`scripts/export_pdf.py`在本地校验并渲染，不需要MCP、API密钥或GEO云端工具。旧schema的固定版导出仅保留兼容，不作为新客户的目录与价格默认值。

先读[分析与执行思路](strategy-playbook.md)及[版式生成说明](template-generation.md)，再按[计划示例](brand-plan.example.json)、[报告示例](brand-report.example.json)和[报告schema](brand-report.schema.json)填写本案。示例客户与报价均为虚构测试数据，只说明结构，不代表行业事实、统一售价或默认方案。

## 1. 内部计划与客户稿分开

`.work/plan.json`是诊断、动作、分工和报价的唯一结构化来源。内部编号与证据留在计划中，生成器将其转换为客户能读懂的情况、分析和安排。

| 字段 | 填写规则 |
| --- | --- |
| `evidence` | 可选的`{id, summary, source?}`列表，摘要能回到本次客户材料、原答或截图。 |
| `findings` | 非空列表，每项`id, observation, analysis, business_impact, priority`；`priority`为`high/medium/low`。每项用`evidence_ids`关联证据，或用`evidence`文字摘要列表说明依据。 |
| `actions` | 执行方案必填非空列表，每项`id, finding_ids, task, content, keywords, media_role, stage, owner, deliverable, review`。`keywords`可为空列表；`status`默认`planned`，`deferred`须加`defer_reason`。 |
| `service_scope` | 非空列表，每项`id, task, provider, client, action_ids`，分别说明工作事项、软文街负责、客户配合和对应动作。同一工作不要换编号重复收费。 |
| `pricing` | 本次用户指令与明确费用，详见下一节。 |

所有诊断均须对应执行或有理由的暂缓动作；每个实际执行动作须在`service_scope`说明负责方及费用范围。一个诊断可对应多动作，多诊断也可共用同一动作。可以并行或暂缓，按业务理由安排。`media_role`按实际用途写权威媒体、行业媒体、自媒体；官方页面、客户配合等动作可写实际工作角色。

诊断稿至少呈现全部`findings`；执行稿至少呈现全部高优先级诊断、全部动作、双方分工及已核报价。程序校验关联是否存在，WorkBuddy仍须核对证据是否真正支持该结论、动作能否解决所述问题。

## 2. 报价只按当前用户指令核算

`pricing.instructions`记录本次原意；`currency`为三位大写代码，如`CNY`；`tax_note`明确含税、未税或尚未约定的税费口径。可选字段如下：

| 字段 | 含义 |
| --- | --- |
| `budget_target` | 意向预算，只作参考，不制造成交报价，也不自动限制候选与方案。 |
| `budget_limit` | 用户明确不能超过的硬上限。若内部`project.budget_limit`已有值，两处必须按最新指令同步一致。 |
| `minimum_total` / `minimum_media_total` | 仅用户本次明确最低总价或最低媒体费时填写。 |
| `required_option_count` | 仅用户明确要求报价档数时填写正整数。 |
| `options` | 单档或多档列表，每档只能含`name`与`items`。 |

每条`items`含`name, category, billing, covers`，可加`note`。`category`为`media/writing/service/package`；`covers`列本项覆盖的`service_scope`编号。同档内每项工作恰好说明一次费用归属，避免整包已含写作后再另收写作费。不同媒体角色的独立刊发工作分别建scope。

| `billing` | 允许的计价字段 | 客户含义 |
| --- | --- | --- |
| `unit` | `quantity`正整数、`unit`单位、`unit_price`明确单价 | 数量×单价。 |
| `package` | `amount`明确整包金额 | 按约定整包收费，范围由`covers`说明。 |
| `included` | 无金额字段 | 已含。 |
| `client_provided` | 无金额字段 | 客户提供或操作。 |
| `not_included` | 无金额字段 | 不在本次范围。 |
| `unquoted` | 无金额字段 | 待确认价格，不能记作零元。 |

金额建议用十进制字符串，按分核算；缺价、负价、非有限值及无效数量会被拒绝。存在`unquoted`时只显示已明确费用小计，方案总价与余额保持待确认。整包包含多种费用但未拆分媒体金额时，不编造媒体费小计；若用户又要求最低媒体费，先补明确分项后核验。

没有用户约定就不继承旧版最低媒体费、固定两档、分类单价或写作单价。用户只给预算时先保留预算性质，未明确的价格使用待确认。费用包含范围、供稿、正文写作、修改、刊发及复核均按本次约定记录。内部project与pricing上限冲突时，按最新指令修正派生工作副本，不改客户原件。

## 3. 品牌与内容模块

`.work/report.json`只存客户可见稿和源模块指令，根结构为：

```json
{
  "schema_version": "3.0",
  "customer": {"brand": "客户品牌", "company": "客户主体", "date": "2026-11-14"},
  "theme": {"primary": "#224F6B", "accent": "#BD985F", "cover_style": "technical"},
  "purpose": "本案业务目标",
  "diagnosis": {"pages": []},
  "execution": {"pages": []}
}
```

两组`pages`须为非空模块列表。`customer.observed_platforms`可选，只列实际已有回答的平台。`theme`可加`background`、`text`六位十六进制颜色；`cover_style`选`editorial`或`technical`。可加本地PNG/JPG的`logo`路径，限report文件所在目录内及其子目录。无内容的可选字段直接省略，不写空字符串。

| `layout` | 主要内容字段 |
| --- | --- |
| `cover` | `title`必填；可加`headline, body`。 |
| `text` | `title, paragraphs:[文字]`；可加`lead, note`。 |
| `insights` / `cards` | `title, items:[{heading, body, impact?, action?}]`；可加`lead, note`。 |
| `timeline` | `title, items:[{period, title, body}]`；可加`lead, note`。 |
| `table` / `quotes` | `title, headers:[文字], rows:[[文字]]`；每行列数与表头一致，可加`lead, note`。 |

品牌主题、章节和模块顺序根据本案组织；品牌定位、竞品、冲突与舆情等页面按证据和任务选择，不凑页数。客户稿写当前情况、原因分析、业务影响、具体安排和费用，不放采集过程、内部ID、制作步骤或工具状态。

## 4. 必须从计划注入的源模块

源模块仅填写`layout, title, source`及可选`lead, note, ids`；不同时填写`items/headers/rows`。生成器会从plan填入正文并移除`source/ids`。以下四种`source`是完整枚举：

| `source` | 可用layout | 注入内容与覆盖要求 |
| --- | --- | --- |
| `findings` | `insights/cards/table` | 当前情况、分析、业务影响；卡片还显示关联动作摘要。`ids`可选诊断编号，不填显示全部。诊断稿合计覆盖全部发现，执行稿合计覆盖高优先级发现。 |
| `action-map` | `table` | 对应诊断、动作与内容、媒体阶段、分工交付、复核重点。`ids`可选动作编号，执行稿合计覆盖全部动作。 |
| `service-scope` | `table` | 工作事项、软文街负责、客户配合和各档费用范围，须完整呈现。 |
| `quotes` | `quotes/table` | 仅注入已核算的分项、数量、单价、整包价、合计和预算余额，须完整呈现。 |

诊断必须含`findings`源模块；执行必须含这四种源模块。可拆成多个源模块组织长内容，但`service-scope/quotes`不接受`ids`截取。金额与计费数量统一在pricing中填写，客户报价页面使用`quotes`源模块，不另写一套费用表或自由报价正文。

报价为2—3档且各项名称、费用类别、覆盖工作、计价方式、单位和说明完全相同时，程序自动按项目横向比较各档；数量、单价与金额可以不同，同一范围只写一行。每档保留实际计价式、小计、总价、税费和硬上限信息，未报价保持待确认。范围或说明不同、以及超过3档时，按各档明细分别显示；单档格式不变。

例如：

```json
{"layout":"cards","title":"关键诊断与执行重点","source":"findings","ids":["F1"]}
```

## 5. 本地导出与逐页确认

Python 3.10或更新版，使用随包`requirements.txt`中的依赖与字体。标准入口直接识别3.0，不需要运行MCP：

```text
python "技能目录/scripts/export_pdf.py" --plan "客户目录/.work/plan.json" --report "客户目录/.work/report.json" --output-dir "客户目录/.work/草稿-v1/客户PDF"
```

`--report`、`--output-dir`必填；默认`--kind both`，另可选`diagnosis/execution`。品牌诊断需要有证据的plan；执行需要完整plan。可传`--project`或`--analysis`交叉核对项目，但新pricing只从plan计算，不继承旧`analysis.budget`。若同时传`--project`和`--analysis`，两者project内容须一致。

`geo_data.py analyze`在新流程中仅生成统计：不把3.0新plan传入其旧`--plan`参数。统计中的旧预算字段不参与新报价。业务判读与结论由WorkBuddy读原答、截图和客户资料完成。

导出先生成完整批次，再把两PDF放到目标目录；同名文件拒绝覆盖，修改后使用新版本目录。`GEO诊断报告.pdf`与`品牌传播与GEO执行方案.pdf`是默认文件名。PNG、审计JSON及页数在结果的`review_dir/audit/pages`中；通常存report同级`pdf-review`，使用技能自带示例时存输出父目录的`.work/pdf-review`，不写回技能资源。

模块按需要自动续页，结果`pages`是实际物理页数。查看每个audit的全部`rendered_pages`，逐张打开诊断和执行的全部PNG，检查封面、标题层级、中文、留白、表格续页、颜色及Logo。再对照plan核诊断依据、动作关联、三类媒体用途、分工、供稿、全部报价和费用范围。长内容优先精简重复表达或合理拆模块，不能藏字、裁字或通过缩小字体挤入单页。

运行`check_client_report.py`清除制作话术，再做完整语义与视觉自审；文本检查通过不能代替全页查看。所有问题修正后重新导出，复查全部新画面及关联合计，通过后仅交付两份已审PDF。JSON、判读、截图、PNG和审计留客户内部工作目录。测试用虚构资料，真实客户原件与现有报告保持不动；本地导出、WorkBuddy实际安装与用户验收分别记录。
