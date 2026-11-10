# PPT 模板与客户稿导出

模板位于 `templates/GEO诊断报告模板.pptx`、`templates/品牌传播与GEO执行方案模板.pptx`，各 10 页。它们是可编辑的文本和原生表格，未填入历史客户结论或演示指标。模板中的“待采集”表示缺少数据。

完成采样校验与预算计算后，在本次客户的工作目录中，用标准 Python 环境运行。将“技能目录”替换为解压安装后的绝对路径，输入与输出都放客户工作目录：

```bash
python "技能目录/scripts/export_ppt.py" --analysis outputs/analysis.json --plan plan.json --report report.json --output-dir outputs/customer
```

需要安装 skill 的 `requirements.txt`。脚本仅依赖普通 Python 与 `python-pptx`，预算校验调用同目录的 `geo_data.py`，不使用 Codex 专属运行时。可用 `--kind diagnosis` 或 `--kind execution` 单独导出一种，默认 `both`。输出为 `GEO诊断报告.pptx` 和 `品牌传播与GEO执行方案.pptx`。输出目录已有同名文件时拒绝覆盖，应选择新目录或先保留旧版。

`analysis.json` 必须是 `geo_data.py` 生成的 `schema_version: 1` 文件。输出执行方案时，脚本重算 `project + plan` 预算并与 `analysis.budget` 比较。计划、排期或报价有变化时，必须先重新分析，再导出，防止媒体清单与费用使用不同版本。

## report.json

参考 `references/report.example.json`。该文件仅放经复核的客户可见叙述，不填写或覆盖样本数量、提及率、推荐率、引用率及预算数字。

| 字段 | 内容 |
| --- | --- |
| `report_date` | 报告日期，可留空采用本轮日期 |
| `summary`、`method_notes` | 诊断摘要与补充方法说明 |
| `scenarios`、`competitors`、`facts`、`sources`、`findings` | 需求场景、竞品、事实核验、信源观察、诊断问题 |
| `sentiment_summary`、`sentiment_evidence_ref` | 独立网络检索证据支持的声量与舆情观察及证据索引。未检索时明示未采集，不能用 AI 问答替代 |
| `priorities`、`objectives`、`prerequisites` | 后续动作、传播与 GEO 目标、客户配合要求 |
| `keywords` | 关键词或问题簇、业务依据及证据索引 |
| `media_notes` | `{ "媒体编号": "客户可见的选用理由" }`，不放成本或内部备注 |
| `quarterly` | 自然季度列表，`title` 为季度，`detail` 为主要工作，`retest` 为复测与调整安排 |
| `deliverables` | 交付列表，`title` 为事项，`detail` 为责任与验收依据，`time` 为时间 |
| `targets` | 目标列表，`title` 为指标，`detail` 为拟议目标及检查日期，`method` 为复测方法。无基线时不编造提升幅度 |

普通表格列表项格式为 `{ "title": "事项", "detail": "观察或建议", "evidence_ref": ["证据编号"] }`。证据不足时填“待补证据”。叙述字段可以是字符串，也可以是由字符串或上述对象组成的列表。给客户看的判断须能关联到本次证据，不以旧报告的结论作为新客户的实测结果。`quarterly`、`deliverables`、`targets` 的第三列分别采用 `retest`、`time`、`method`，不要误填证据编号。

## 数据与交付规则

- 平台指标逐组读取 `analysis.groups`，且仅输出 `analysis.sampled_contexts` 中本轮实际回传的平台，不把预配置但未回传的平台列成零条数据，不等待或提醒补其他平台。保留平台、问题类型与意图区分，不对分组比例求平均。支持引用未经核验时简短显示“未核验”。主动推荐只用于自然需求中的推荐意图题。
- 方法页日期读取 `analysis.report_scope` 的本轮日期与实际回传范围；缺失时间和方式按本轮本地日期、网页端直接联网处理，无需追问或重复警告。执行封面中的周期仍来自 `project.start_date/end_date`。已提供的历史日期与明确模式保留，不用执行周期替换采集日期。
- 客户预算仅读取 `analysis.budget.client` 及客户预算上限，不读取 `internal`、原始单价、报价档位、采集人或内部备注。客户价缺失时保留“待报价”，不使用成本代替客户价。
- 存在缺价时，可显示客户已知金额小计与缺项数；计划合计仍保持未知，不能将已知小计宣称为完整预算。
- 选题来自 `plan.contents`，取消和排除项不输出。媒体执行清单仅采用“已选、待执行、已发布”记录；候选资源不当成承诺交付。
- 长表自动续页，长单元格按行展开，叙述超出内容区时自动续页。动态客户稿可能超过模板的 10 页。不会缩小正文来挤满一页，也不以省略号丢弃长内容。
- 导出后逐页检查文字、分母与证据、自然季度归属、客户报价及空缺说明。稿件发布、搜索收录和 AI 引用分别验收，不承诺平台收录、提及、排名或转化。
- 报告中不能保留 `{{字段}}`、`${字段}` 这类未替换标记。明确的“待采集、待确认、待报价”是允许的空数据状态。

安装后使用同一套经校验的客户数据运行上述导出命令，并确认两份文件实际生成。逐页检查客户价隔离、引用分母、证据索引、长表续页及空缺说明，不能把命令退出成功代替内容验收。开发用行为测试只在仓库中保留，不属于同事安装包的使用步骤。
