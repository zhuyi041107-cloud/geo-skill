# 固定模板PDF填写与打印

两份客户PDF由 `scripts/export_pdf.py` 填充随包固定HTML，再用本机Chrome/Edge无界面打印。BeautifulSoup只填文字和克隆数据行；字体、列宽、图形、表头、章节与分页骨架来自模板。生成阶段不重写HTML/CSS，不另造PDF脚本，没有ReportLab或通用排版回退。

## 先选模板，再写数据

| profile | 诊断模板 | 执行模板 |
| --- | --- | --- |
| platform | `templates/platform-diagnosis.html` | `templates/platform-execution.html` |
| service | `templates/service-diagnosis.html` | `templates/service-execution.html` |

写report前先读对应的两份HTML、`templates/pdf-template-manifest.json` 中的文字槽/段落/表绑定清单，以及 `references/template-contract.json` 的业务数据契约。HTML是固定输出骨架；contract说明要提供哪些业务数据。不能只看章节名称后自己重画页面。

模板SHA与manifest不匹配会拒绝生成。模板及manifest只在skill版本维护时一起更新；客户报告阶段修正report/plan数据，不改哈希绕过检查，也不复制模板或生成器到临时目录后改样式。

## report仍写业务分析

保留 `template_profile`、diagnosis/execution的summary与sections。原模板的推导逻辑、证据和写作要求见 `template-generation.md`，完整虚构结构参考 `report.example.json`。

| 数据位置 | 填写内容与边界 |
| --- | --- |
| `diagnosis.fields` / `execution.fields` | manifest列出的固定文字槽，值仅为字符串；如图注、原元信息栏、收口文字。客户、日期、费用等同源值由project/plan生成，不能用fields覆盖。 |
| `diagnosis.blocks` / `execution.blocks` | manifest列出的原段落位置，采用title/detail条目；只补该位置需要的业务判断，不新增章节或布局。 |
| `sections[].paragraphs` | 本节表内没有的独有判断，可为空；不逐表重复摘要或解释制作过程。 |
| `sections[].tables` | 按contract原样columns与rows填写纯文本。`source=plan`的表由脚本取数，不能手填另一套数字。 |
| `diagnosis.priority_cards` | 原四卡位置的四行 `[标题,优先级,说明]`，来自本客户真实优先任务，不照抄原案例标题与等级。 |
| `diagnosis.layer_questions` | 四层对应的四条已有用户问法。它补充原图中的“用户问”，不改变原业务矩阵列数，不要求另行采集。未提供时生成器使用已有层关注问法。 |

`data-slot`、`data-paragraphs`与`data-row`只是模板绑定方式，模型不提供HTML、CSS、样式参数或事件代码。填充器会安全转义文本，并保留固定DOM与行样式。原路径只印短阶段/问题，四层图按原左侧层级、中间现状与问法、右侧短状态填；不将旧业务影响长段再塞进图卡。

manifest的required_blocks是原独立说明标题下的必填业务内容，必须在blocks填写；不能留下只有标题的空段。表内已讲清的普通引导段仍可为空，避免重复。缺省的可选附页按模板规则整块隐藏，不自行删改版式。

原元信息槽按本案事实填写，不照搬原稿的检测模型、方法或日期。summary及正文直接说明品牌情况、差距、原因或策略及业务影响；不另加观察基础、回答数量、联网模式、样本边界或处理教程。具体主体、资质、收费及案例未确认时，在对应事实旁简短说明。`evidence_ref`与内部ID用于溯源，不打印。

## 状态格按原短值填写

| 位置 | 常用原短值 |
| --- | --- |
| scene_matrix状态列、scene_details两项提及列 | 已出现、未出现、部分出现、待核实、不适用 |
| source_layers覆盖状态 | 有、无、部分、待核实、不适用 |
| source_layers覆盖质量 | 高、中、低、待核实、—、不适用 |
| source_layers实际引用 | 是、否、部分、待核实、不适用 |

这些格有硬校验。竞品名单和详细事实放scene_details的说明列或competitor_basis，来源资产说明放对应分析段；不能用长句撑大状态格。未确认不等于无，未被引用不等于页面不存在；保留待核实，不为凑原稿的红绿色块提高核验等级。长正文在原段落位置自然分页，不缩字号、截断或隐藏事实来凑原页数。

## 计划、内部映射与费用

项目保留start_date/end_date；stages写name、objective、deliverables、effect_target。每篇内容的stage与阶段名一致，并补齐source_layer、content_form、key_facts、observation_port、checkpoint及目标问题。周次、周频、独立内容与刊发量、费用均由同一plan计算；同稿多站发布分别计一次内容和多次刊发。修改计划或报价后先重算analysis，预算不一致拒绝导出。

执行PDF前，plan.logic_links须覆盖实际诊断优先项和建议标签，每条写事实/竞争或信源依据、希望形成的选择理由、实际文章或客户自有动作、媒体角色、阶段与检查日。客户自有动作允许不增加付费稿；有付费内容时，检查不得早于内容及有效刊发日期。机器只验覆盖、引用和时点，WorkBuddy仍需逐项检查文章是否解决该缺口、投入是否支持优先级、服务承诺是否有费用依据。映射不印入客户正文。

平台型沿用原费用报价卡、原阶段七列表和三块两列场景附录，不新增实际媒体组合章或阶段/季度费用表。budget节的quote_card填写name、focus、suitability；金额、稿量、刊发量与媒体配置由plan生成。service按自己的原表取数，不混用平台型结构。原表已有端口栏只填对应值，不展开采集说明。

当前默认建议执行目标及上限为20,000元；有明确目标时，正式方案已知费用须达到目标90%且不超上限。明确只给上限、允许少花时不强制花满。对客单价读client_unit_price；采用目录市场参考价时保留price_basis与quotation_date，不冒充确认售价。未报价的撰稿、官网建设、复测或维护不能写成已含刚性交付。

预算只核实际placements与fees。推荐媒体.xlsx读取独立的media_recommendations，sheet1为网络媒体，sheet2为自媒体；推荐数量和资源标价总额不受该执行预算限制。两个输出中同一资源的原报价保持一致。

## 运行环境与命令

安装本包requirements.txt中的Python依赖。本机需要Chrome或Edge，以及微软雅黑常规和粗体；Windows对应系统字体msyh.ttc、msyhbd.ttc。生成器还核对输出PDF实际使用的字体，两字重缺失或浏览器打印失败会拒绝交付。字体不随包重新分发，不再依赖旧Noto字体或伪粗体；无需Node、CDP或Codex私有运行时。

在客户工作目录执行，替换安装路径：

```bash
python "技能目录/scripts/export_pdf.py" --analysis analysis.json --plan plan.json --report report.json --output-dir outputs/customer-pdf
```

默认同时生成GEO诊断报告.pdf、品牌传播与GEO执行方案.pdf；可用 `--kind diagnosis` 或 `--kind execution` 单独生成。同名输出已存在时保留旧文件，使用新版本目录。缺环境时说明具体缺项并保留数据，不交替代字体或临时自由排版的成品。

## 验收看原稿与实际页面

模板版本由维护者用已经提供的原文做私有重放，逐页对照原PDF：字体字重、标题位置、封面和路径页、图形与圆角、网格/胶囊、列宽、单元格写法、合并、续表、页脚与断页。相同页数、程序退出成功或虚构示例好看，都不能代替这项检查；未完成的对照不得写成已通过。

客户生成只使用发布模板和本客户数据，逐页核对业务内容、量价、文字完整性及分页。新客户行数变化可自然增减页数，固定页面骨架与表形态保持。客户生成阶段不另索取原模板，也不重做真实客户报告来验证skill。

公开仓库与迁移包只放空槽HTML及虚构版式示例；原客户PDF、截图、原文重放上下文和实采数据留私有工作区。开发验收与WorkBuddy安装实测分别记录，不用本地程序检查代替宿主环境验证。
