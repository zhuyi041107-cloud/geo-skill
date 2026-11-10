# 客户PDF交付

两份客户PDF由 `scripts/export_pdf.py` 使用ReportLab直接生成，不经过PPT。WorkBuddy先执行 `template-generation.md` 的完整业务推导，再按 `template-contract.json` 写结构化正文。脚本只校验契约、汇总同源计划并排版，不替代业务分析。

## 原模板契约

`report.template_profile` 必填 `platform` 或 `service`。前者对应平台型客户原模板：品牌/场景/竞品/信源/机会/优化/标签；执行保持四个主章及目标场景、发文明细附录。阶段与维护是内容创作机制的二级栏目，实际媒体是费用章的二级栏目。后者保持项目或服务型原模板的主体事实、业务维度、风险、曝光、关键词、阶段推导及原执行章序。两类都保留客户选择路径与四层应答情况；它们描述客户业务，不是诊断教程。

章节顺序、标题层级、必需矩阵及原表头以契约文件为准，不能再用七个通用长段落替代。所有必需章节与关键矩阵须有本客户内容；缺章、空表、错表头会拒绝导出。行数随真实业务而变，不套用原案例的问句数、发文数、评分或平台机制。

只替换客户业务内容，原格式不增写采集前言。客户summary直接写品牌情况与差距；采集方式、联网状态、回答数量、观察基础、样本边界和模板制作说明留内部。导出器会拒绝这些元话术，要求改写成业务分析；不会通过静默删句掩盖问题。具体资质、主体关系或服务承诺未确认时，在该事项旁简短说明。原表的单元格值和具体业务风险正常保留。

最小数据形状（仅示意，不足以单独交付；完整虚构示例见 `report.example.json`）：

```json
{
  "template_profile": "platform",
  "diagnosis": {
    "summary": "品牌定位能够被识别，适用场景与交付责任仍需形成清楚的选择理由。",
    "sections": [{
      "key": "brand_recognition",
      "title": "一、品牌现状",
      "paragraphs": [{"title": "当前识别位置", "detail": "品牌服务定位清楚，客户选择前仍需要了解适用范围和双方责任。", "evidence_ref": ["内部证据索引"]}],
      "tables": [{"id": "recognition", "columns": ["判定项", "直询结果", "说明"], "rows": [["业务识别", "服务定位可识别", "回答能说明主要服务，但适用条件仍需补齐"]]}]
    }]
  },
  "execution": {"summary": "执行主线与投入重点。", "sections": []}
}
```

`paragraphs` 采用 `title/detail/evidence_ref`。每一条应连贯说明现状、原因或策略判断、对选择的影响及执行含义，矩阵每行写具体情况。`evidence_ref`仅内部溯源，不打印。客户正文不放内部ID、本机路径、模板token、采集教程或处理流水账。旧 `keywords` 可继续供表格使用，但旧摘要和findings不能代替完整模板。

## 计划字段与机械表

`source=report` 的表由WorkBuddy按契约填 `columns/rows`。`source=diagnosis` 的用户路径与四层表由执行文档复用，避免两份报告互相矛盾。`source=plan` 的表由脚本生成，报告不得手填rows覆盖：

- `stage_plan`：阶段目标与交付取 `plan.stages`，周范围、每周稿量、阶段独立内容和刊发数来自真实内容与投放。
- `article_schedule`：逐篇排期。平台型保留原十列含媒体类型、观察端口；服务型保留原九列并在原具体媒体列列出实际媒体。完整资源与费用另在媒体明细呈现。
- `selected_media/media_costs`：具体媒体、内容、刊发量、参考单价、金额及类型合计。
- `stage_budget/quarterly_budget`：阶段和自然季度费用，季度由日期推得。
- `content_volume`：服务型诊断发文量推导，独立内容与刊发次数分列。

项目需 `start_date/end_date`；`plan.stages` 为 `[{"name":"阶段名称","objective":"阶段目标","deliverables":"可承诺交付","effect_target":"AI表现观察方向"}]`，name与contents.stage完全一致。每篇已选内容除原 `content_id/title/platform/stage/scheduled_date/question_ids/evidence/status` 外，填写 `source_layer/content_form/key_facts/observation_port/checkpoint`；`target_question`可直接写实际问句，否则从project.questions关联。周次自动从项目开始日期计算，不靠手填周号。其他费用可写 `stage`；未分配阶段的费用单列，不能静默漏掉。

示例字段：

```json
{"content_id":"C001","title":"适用条件与交付边界","platform":"豆包","stage":"基础事实建设","scheduled_date":"2026-11-16","source_layer":"基础信源层","content_form":"专业说明稿","observation_port":"网页端","target_question":"哪些团队适合这项服务？","key_facts":"服务包含资料入库、权限检索与出处展示，实施范围按项目确认。","checkpoint":"第5周检查","status":"已选"}
```

实际媒体只用有效已选记录。文章日期、媒体日期、单价、次数、阶段及自然季度必须与同一plan一致；内容篇数与同稿多次刊发分别统计。修改plan后先重算analysis，PDF再次比对预算。不匹配拒绝输出。

## 预算与报价

对客单价只读 `client_unit_price`。可采用已明确对客报价，或同值采用资源目录市场参考价形成建议包；后者须将原价格依据和报价日期放进 `price_basis/quotation_date`，不能称已确认售价。内部 `unit_price/price_tier` 不进客户PDF。价格说明集中一次，媒体单价列只显示金额，缺依据不造。

当前默认建议预算目标和上限为20,000元；明确目标的正式已知方案须达到目标90%且不超上限。只给上限且明确允许少花时不强制花满。脚本调用统一 `validate_delivery_budget`，不能用虚构单价、服务费或补差项满足预算。未列价的撰稿、官网建设、后续维护等说明费用边界，不伪装已包含。约2万元示例是建议预算，不是确认结算承诺。

## 导出及验证

在客户工作目录执行，替换安装路径：

```bash
python "技能目录/scripts/export_pdf.py" --analysis analysis.json --plan plan.json --report report.json --output-dir outputs/customer-pdf
```

默认生成 `GEO诊断报告.pdf` 与 `品牌传播与GEO执行方案.pdf`；可用 `--kind diagnosis` 或 `--kind execution` 单独导出。同名文件已存在拒绝覆盖，保留旧文件并换新输出目录。首页只保留原有标题、客户与日期，不自动增加观察范围、回答条数或采集条件。

通用版式示例位于 `templates/GEO诊断报告版式示例.pdf`、`templates/品牌传播与GEO执行方案版式示例.pdf`，来自同一代码和虚构资料。真实媒体及市场参考价来自内置目录，虚构客户与观察不能直接复用于真实业务。A4纵向蓝色报告体，首屏给判断，正文与完整矩阵自然分页，不硬凑原页数。长文自动分页，长表重复表头，超高单行允许跨页，内容不截断。

中文字体已随skill分发，覆盖常用中文、扩展A及标点，不按示例文字裁剪。许可证与来源在 `assets/fonts/`；运行只需requirements的公共依赖，不需要Codex、fontTools或系统中文字体。

导出后必须打开或逐页渲染检查：分析是否具体、原栏目是否齐全、所有选题及真实媒体是否能对上、量价是否一致、续表有内容行、中文/日期/页码无裁切。文本提取或程序成功不能替代视觉验证。
