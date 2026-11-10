# 推荐媒体 Word 输出

完成选媒和执行预算后，另交付 `推荐媒体.docx`。使用 `templates/推荐媒体模板.docx` 的网络媒体清单、自媒体清单，不重新设计封面。模板由用户指定的原媒体投放表转换，只保留表头与空数据行，不包含案例媒体及价格。

```powershell
python scripts/export_media_word.py --analysis "项目/analysis-final.json" --plan "项目/plan.json" --output "正式输出/推荐媒体.docx"
```

需要 python-docx。脚本先按 `analysis.project` 和当前 `plan` 重算预算，确认与 `analysis.budget` 一致，再执行 `geo_data.validate_delivery_budget`。预算不符或未满足目标规模时，先修正实际执行计划并更新分析；导出器不会改价补差额。已有文件拒绝覆盖，改用新的输出目录。

## 填表步骤

1. 仅选 `已选`、`待执行`、`已发布` 的 placements。按 `source_sheet` 分至网络媒体报价、自媒体报价；同一来源表与媒体ID只列一次，首次出现顺序不变。同一媒体有相互冲突的属性或报价，先统一来源。
2. 将 `media_id + source_sheet` 与内置目录准确匹配，补充分类、地区、备注、入口形态和市场参考价。匹配到目录时媒体名与市场价必须一致；外部已知资源可直接提供这些字段。`media_type` 不能替代来源表归类。备注保留实际刊发形态，不能把自媒体号写成媒体编辑部稿件。
   更新外部报价的 `source_file` 文件名明确不同于目录源文件，且提供有效 `quotation_date` 与 `market_price` 时，优先使用该 placement 的外部报价及属性，不再用旧目录覆盖或补充；缺少这些依据则继续严格核对内置目录。
3. B列写 `media_group`，表示本计划的媒体组合分组，如本地资讯、行业垂直；相邻同组单元格合并。未提供时只写可证的网络媒体或自媒体，不套用原案例的地域、行业分组。
4. 原16/17列表头及顺序全部保留。市场价格只取 `market_price`、`market_reference_price` 或目录原值；不使用 `client_unit_price`、`unit_price` 代填。原五档代理/会员价只取 `tier_prices` 的显式报价，并要求 `tier_price_source` 指明对应的外部报价依据；缺档空白，市场价不推算代理价。
5. 联系方式列的原意是稿件可否带联系方式，写 `contact_policy` 的带、不带、可带、不可带或需确认等政策；不能写联系人的姓名、电话、微信或邮箱。文章案例、新闻源、简介、粉丝、认证、认证主体均按已有证据填，未知为空，不从媒体名猜测。

## plan 可选字段

每个 placement 可增加以下字段；未提供时对应单元格留空。现有预算字段及执行数据继续按 plan 规范填写。

| 字段 | 用途 |
| --- | --- |
| `media_group` | B列的本次策略分组 |
| `category`、`region`、`editorial_note`、`entry_type` | 分类、地区、真实限制和刊发形态；可由目录补充 |
| `market_price` / `market_reference_price` | 市场参考单价；与客户执行价分开 |
| `tier_prices` | 以超级代理、核心代理、高级代理、普通代理、普通会员为键的已知金额对象 |
| `tier_price_source` | 外部报价文件、行、档位等依据；只要填写代理档报价就必填 |
| `contact_policy` | 稿件可否带联系方式 |
| `article_example`、`news_source`、`description` | 已有文章案例、新闻源、简介 |
| `followers`、`certification`、`certification_subject` | 有依据的粉丝量、认证、认证主体 |

## 版式和验收

两清单按网络、自媒体顺序各起一页，保留合并标题、原“按需选择，按实际发布媒体计算总费用”说明、B列合并分组、黑色细边框与自媒体备注红字。原标题与表头的主题色及tint解算为浅黄褐C4BD97；费用提示为FFC000；I列高级代理保持浅色FDE9D9，未知价格仍为空。A3横向、11磅文字、固定列宽、自动行高；连续页重复标题与表头。数据多时扩展表格，不缩成小字。某清单无所选媒体时保留该清单的完整表头和一个空行。

导出后渲染并查看全部页面，逐表核对列序、媒体分组、媒体名称、市场价与空白价档，检查无缺字、截断、重叠或边界溢出。该表是所选媒体资源清单；数量、具体排期及总费用仍以执行方案和Excel中同源预算为准。
