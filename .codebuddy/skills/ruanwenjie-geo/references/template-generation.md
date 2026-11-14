# 品牌版式与生成说明

0.13.0新任务使用3.0品牌报告。内容要求、证据、数量和费用校验统一，页面标题、组件组合、数量和客户主题可变。两份PDF均使用1200×675横版基础画布；自动分页后的实际页数由内容决定，不复用固定8／9页背景。历史客户成果保持原样。

## 1. 先定方案主线

先读[strategy-playbook.md](strategy-playbook.md)，在内部明确：客户想改变什么、当前阻碍、真实可用优势、首批动作、如何判断进展。按客户类型选择[参考案例](case-library/index.md)，不要仅换品牌名。普通方案、首次提案、开业投放和执行复盘各有不同叙事重点。

内部文件：project保存客户和采集资料；analysis保存判读与事实状态；3.0 plan保存evidence/findings/actions/service_scope/pricing；report保存客户主题、独立成稿和源页位置。findings与actions由WorkBuddy理解资料后填写，程序不代替分析。

## 2. 品牌主题

report.theme必需primary、accent、cover_style，可选background、text、logo。颜色为#RRGGBB。editorial偏品牌叙事、留白与重点文字；technical偏技术信息、清晰分区与图表。按本品牌真实视觉选择，不给所有客户同一套绿色或只机械按行业猜颜色。两种基础风格可以搭配不同模块和顺序。

Logo只读本地PNG/JPG，放在report.json所在目录或子目录，以相对路径指定；不下载网络图，不读取越界路径，不借其他案例Logo。没有合适物料就用品牌字标与矢量图形，事实和文字仍须属于本客户。

## 3. 可组合组件

| layout | 适合的信息 | 字段 |
| --- | --- | --- |
| cover | 品牌与本次核心主张 | title，选填headline/body |
| insights | 诊断及其影响、应对 | items中的heading/body，选填impact/action |
| cards | 品牌定位、场景或内容主题 | items中的heading/body，选填impact/action |
| table | 同行比较、诊断动作、内容计划与分工 | headers、rows，列数相同 |
| timeline | 按阶段推进与复核 | items中的period/title/body |
| quotes | 程序核算后的方案费用 | 使用source=quotes注入，不手填价格 |
| text | 必要论述与边界 | paragraphs |

正文模块均可选lead/note。具体字段遵守[PDF契约](pdf-output.md)，不临时发明未渲染字段。组件数量没有固定三卡／四块要求；长内容按真实高度自动续页，表格续页重复表头。页面增多时先删重复和无商业价值文字，不能删除必要事实、动作或费用明细。

## 4. 诊断与执行如何对应

report.diagnosis.pages须包含source=findings，覆盖计划中要交付的诊断。execution须包含关键诊断摘要、action-map、quotes和service-scope源页。可用ids按主题分组，标题和位置自由；必须覆盖所有高优先诊断、执行或有理由的暂缓动作、费用与责任。

源页写layout/title/source，可选lead/note/ids；禁止同时另写items、headers或rows。findings用insights/cards/table，action-map与service-scope用table，quotes用quotes。准备阶段从plan生成可见文字，内部ID与原始证据不进入PDF。

每项执行在客户页显示对应现状、措施、内容关键词、媒体作用、阶段、承担方、交付与复核；不能只在内部关联ID，而正文还是通用“增加曝光”。诊断可有多种成因，清楚区分观察、合理解释与建议，不将AI缺席直接断言为全网无声量。

## 5. 客户大纲按内容决定

可考虑：品牌目标→关键诊断→定位或场景策略→关键词与内容主题→媒体分工→阶段安排→分工与报价→复核与调整。此顺序是内容检查参考，不是固定页序。没有实质冲突就不加冲突汇总；同行不足就收窄比较；复杂产品线按任务拆页。执行只摘要诊断并承接动作，不复制整份诊断报告。

同一复核规则或共同前提不在每个阶段重复，放在lead或note中，行内保留该阶段的任务、数量和依赖差异。表格仅容纳便于比较的短句；原因论述放分析页，动作表保留具体措施与交付。若续页只剩几行，先合并重复和合理分组，再检查分页；不能用删除关键事实、缩字或裁切处理。

## 6. 费用由本次指令产生

按[报价结构](pricing-contract.md)核本次指令。报价页从plan.pricing生成，允许一档或多档、分项或整包，不继承任何旧最低费、旧单价、旧写作规则或参考件规模。服务范围须和每档的包含／另计／客户提供逐项一致。稿数和刊发次数分开，单价×数量、整包金额及总价使用同一源。

## 7. 逐页自审与发布

按[commands.md](commands.md)导出草稿；结果返回实际pages、audit和review_dir。另轮先对照本次用户要求与证据检查结论，再实际查看每张PNG，检查标题、品牌色、内容密度、表格续页、费用、遮挡和截断。结构与禁词检查只能辅助，不能证明事实或策略质量。

若发现问题，先改plan或report的内容和模块安排，另存新版本目录并重导；不覆盖旧成果，不改渲染器绕过校验。通过后只把已审两PDF复制到新的正式输出目录，内部记录不作客户附件。没有额外用户确认环节或外部GPT终审门槛。

兼容2.0旧固定稿的说明见[历史记录](legacy-fixed-rules.md)。旧样例和参考件不是新任务的事实、价格或页数默认。
