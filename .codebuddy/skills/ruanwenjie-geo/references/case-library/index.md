# 方案参考库

先依据本次客户的问题和任务类型，读最相关的1—2份摘要，再按摘要指定页码或Sheet查看原格式文件。无需每次加载全部参考。

参考件不覆盖本次用户指令。尤其不继承旧价格、最低费用、方案档数、写作费、赠款、稿量、页数和效果承诺；缺少当前证据的百分比与排名不能填进新报告。

| 案例 | 用途与适合客户 | 阅读摘要 |
| --- | --- | --- |
| 周大福：高端定位与品类竞争 | 首次战略方案；珠宝、奢侈消费、品牌升级 | [jewelry-positioning](jewelry-positioning.md) |
| 德济医院：专科信任与需求场景 | 售前沟通及服务介绍；医疗机构、专业服务 | [medical-trust](medical-trust.md) |
| 统一AI：品牌实体与传播语境 | 首次品牌推广方案；教育科技、同名品牌、招商业务 | [education-entity](education-entity.md) |
| 爱昕集团：执行复盘与下一阶段 | 阶段效果复盘；集团、多品牌、消费健康、招商 | [group-review](group-review.md) |
| 维晏：本地开业与持续曝光 | 开业传播提案及媒体规划；本地服务、空间、开业活动 | [local-opening](local-opening.md) |
| 兰宝传感：技术、应用与项目证明 | 年度品牌与GEO执行规划；工业制造、B2B、传感器 | [industrial-b2b](industrial-b2b.md) |
| 通用品牌方案：业务要素检查 | 通用业务表样例；跨行业，仅作完整性检查 | [generic-checklist](generic-checklist.md) |
| 方案思路：从客户问题到执行 | 工作思路参考；跨行业 | [proposal-thinking](proposal-thinking.md) |
| 旧羊驼舍：服务印象与选择理由 | 原始诊断及落地执行样例；教育服务、学术辅导、升学咨询 | [education-original](education-original.md) |
| 原包与0.12版式：组件参考 | 旧视觉示例；跨行业组件参考 | [legacy-visuals](legacy-visuals.md) |
| 花小聘历史输出：问题与反例 | 生成结果反例；蓝领招聘、平台服务 | [counterexample-huaxiaopin](counterexample-huaxiaopin.md) |
| 羊驼舍后续输出：固定版式反例 | 生成结果反例；教育服务 | [counterexample-yangtuoshe](counterexample-yangtuoshe.md) |

## 调用顺序

1. 品牌定位与品类争夺看周大福；技术与选型看兰宝；专业信任看德济；本地开业看维晏；同名与口径问题看统一AI。
2. 合作后的效果复盘看爱昕；服务型业务的选择理由可看旧羊驼舍。初次提案不能冒称已执行或已有结果。
3. 需要排版组件时再看旧视觉示例；旧8／9页不是新报告的页数规则。
4. 两组历史生成结果标作反例，检查制作过程话术、机械填格、策略悬空及费用混乱，不照抄其品牌事实。

## 文件与范围

本库收录12组、24份用户参考文件，原格式载荷合计约105.1 MiB。文件相对路径、字节数和指纹见[manifest.json](manifest.json)。原客户文件保持不动；同内容以SHA256去重，来源仍分别记入索引。

原始AI采集、内部判读/采购明细、销售个人关系及无明确来源授权的其他客户文件不随库分发。少量联系号码与本机路径仅在参考副本遮蔽，具体调整见manifest。图片未做全量OCR检查。

完整仓库安装可直接取得sources中的参考件；若使用分包安装，核心包和所有参考扩展包须解压到同一个ruanwenjie-geo目录。缺少参考件时明确指出缺失文件，可先使用现有摘要，不伪装已读原件。
