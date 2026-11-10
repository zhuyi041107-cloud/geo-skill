# 数据与命令

所有命令中的 `技能目录` 替换为实际安装的 `ruanwenjie-geo` 文件夹，`工作目录` 替换为当前客户的独立文件夹。使用当前环境的Python命令（如python、python3或py -3），路径加引号。先检查 `python -c "import openpyxl, pptx"`；需要安装依赖时用 `python -m pip install -r "技能目录/requirements.txt"`，遵守本环境权限。

## 1. 提取客户素材

```text
python "技能目录/scripts/geo_data.py" inspect-client --input "工作目录/软文街_GEO客户素材收集表.xlsx" --out "工作目录/client-fields.json"
```

结果保留字段名、答案、要求和缺失清单。客户表存在大部分选填字段时仍应先识别可完成阶段，集中补关键缺项。

## 2. 建立project.json并生成采集任务

参见 [最小虚构项目](project.example.json)。由WorkBuddy根据客户实际业务生成问题；示例只演示格式，不代替实际选题。基本结构：

```json
{
  "project_id": "客户内部编号-基线日期",
  "client_name": "客户公司名称",
  "brand_names": ["品牌全称", "经确认的别名"],
  "industry": "所属行业",
  "services": ["实际产品服务"],
  "regions": ["实际服务地区"],
  "audience": ["目标客群"],
  "advantages": ["客户填报优势，注明待核验"],
  "competitors": [],
  "public_sources": [],
  "budget_limit": null,
  "currency": "CNY",
  "start_date": null,
  "end_date": null,
  "questions": [
    {"question_id":"Q001", "type":"自然需求", "intent":"推荐", "theme":"业务场景", "text":"根据客户业务生成的中性问句", "priority":"高"}
  ],
  "contexts": [
    {"platform":"用户选择的平台", "mode":"实际预定模式", "online":"是", "round":1}
  ],
  "repeats": 1
}
```

`type`为自然需求或品牌认知；`intent`为认知、推荐、决策、对比、其他；联网值为是、否、未知。round是基线/复测轮次，repeats是同一轮独立新对话的重复次数。平台和模式使用实际值，不假定所有平台支持同一功能。start_date/end_date是执行计划起止日期，使用YYYY-MM-DD或null；采样时间另从每条回答记录读取。金额用十进制字符串或null，不写“XX万”。

```text
python "技能目录/scripts/geo_data.py" prepare --project "工作目录/project.json" --out "工作目录/客户AI回答采集表.xlsx"
```

采样任务数=题目数×context数×repeats。任务和ID由脚本生成，未采行保留，勿删除后当成没有分母。需增题/平台/重复时生成新版本，再按稳定ID迁移已有原文。

## 3. 回传采集表并补判读

工作表首行为字段名，按原表头编辑，别改ID或表头；不要把原始回答写进公式。

| 表 | 字段和分工 |
|---|---|
| 项目配置 | 字段、值(JSON)、说明；由WorkBuddy维护项目元数据 |
| 问题清单 | question_id、问题类型、意图、问题主题、目标问题、优先级、备注 |
| 回答记录 | sample_id、question_id、平台、模型或模式、联网状态、轮次、重复序号、采集状态、采集时间、新对话、回答全文、引用展示、品牌提及、品牌推荐、排名、回答证据路径、采集人、备注 |
| 引用明细 | citation_id、sample_id、URL、标题、网站或媒体、核验状态、支持品牌、支持内容、证据路径、备注 |

同事填写采集条件、原文、引用列表和证据位置；WorkBuddy回传后填“品牌提及/推荐、来源核验、支持品牌”等派生判读。采集状态为未采集、已完成、失败、待核验；拒答/平台错误填失败并备注原因。采集时间保留含时区时间文本，如2026-11-10 14:30 +09:00。新对话按实际情况填写，非新对话单列说明。

“品牌提及/推荐”“支持品牌”为是、否、待判。引用展示为已展示、未展示、待核验、不适用；不适用用于不支持来源展示的采样条件。URL须是原始HTTP(S)文章地址；核验状态为已核验、无效、待核验。脚本只校验格式和判读状态，不会替同事打开网页或伪称已查证。

保存一份新的已判读采集表后计算：

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/客户AI回答采集表-已判读.xlsx" --out "工作目录/analysis.json"
```

重复/孤儿ID、缺失采样任务或错误URL会报错；修正对应原始记录后重跑。未确认新对话或缺少采集时间的完成记录保留原文，但不进入标准可比有效样本，invalid_conditions与issues披露原因。analysis.json保留project、groups、counts和证据，每个group按平台、模式、联网、round、题型与意图隔离；0分母用null。它是数字来源，不用叙述JSON手填统计数字。

## 4. 筛选报价候选

```text
python "技能目录/scripts/media.py" --input "工作目录/最新媒体报价.xlsx" --tier "普通会员" --query "科技" --region "山西" --kind network --limit 30 --out "工作目录/media-candidates.json"
```

报价必须包含网络媒体报价/自媒体报价相应sheet及原字段。`--kind`为network/self/all；主题词以空格分隔，全部匹配名称/分类/门户/渠道；地区可逗号分隔。查询过窄时按业务合理放宽，不通过去掉限制来伪造合格资源。

返回记录含价格、备注、原文件、sheet、行号和软文街id。明确拒收GEO的排除；内容形态限制或地区/价格未知的列为需核实。候选排序是便于浏览，不代表AI引用能力排名。脚本不会把联系人和联系方式输出到候选JSON。

## 5. 执行明细plan.json

参见 [虚构执行计划](plan.example.json)。三类记录：

- `contents`：content_id、title、question_ids数组、platform、stage、scheduled_date、evidence、status。
- `placements`：placement_id、content_id、media_id、media_name、media_type、source_file、source_sheet、source_row、price_tier、unit_price、quantity、client_unit_price、scheduled_date、status。
- `fees`：fee_id、category、description、amount、client_amount、scheduled_date、status。

内部价`unit_price`/`amount`与对客价`client_unit_price`/`client_amount`分开填；未知为null。quantity为正整数。已选、待执行、已发布的执行项纳入预算；候选、取消、排除不计执行总额。日期决定自然季度（含年份）；无日期留未排期。每个内容只用一个content_id，多站刊发分别建placement。其他费用不能再重复打包已列媒体费。

同一次导出先重算带预算的分析：

```text
python "技能目录/scripts/geo_data.py" analyze --input "工作目录/客户AI回答采集表-已判读.xlsx" --plan "工作目录/plan.json" --out "工作目录/analysis-final.json"
python "技能目录/scripts/geo_data.py" export-excel --project "工作目录/project.json" --analysis "工作目录/analysis-final.json" --plan "工作目录/plan.json" --out-dir "工作目录/正式输出"
```

输出内部与客户两份Excel。budget含content_count、placement_count、publication_count，以及internal/client各自的媒体费、其他费、总额、缺价ID、季度和超预算状态。known_subtotal为已知费用小计，missing_count为缺价/缺数量项数；缺价时全部总额仍为null。客户字段不继承内部原价。

## 6. 补叙述并导出PPT

由WorkBuddy基于原始证据撰写report.json，包含摘要、发现、优先事项、关键词、竞品、信源和舆情边界；字段与命令以 [PPT导出说明](ppt-output.md) 为准。叙述不覆盖analysis的指标与预算，不带内部报价及备注。

Excel与PPT为导出时的快照。更改采集判读、执行明细或对客价后，重新计算并导出新版本；不能只改PPT一个数字。交付前打开文件，检查所有页、金额与未填项。
