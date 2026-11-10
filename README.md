# 软文街 GEO 诊断与执行规划

给WorkBuddy使用的内部业务技能：客户资料 → 有诊断价值的问题 → 三列AI回答采集表 → 按原模板完成诊断、内容、选媒、逐篇排期和约2万元预算 → PDF、推荐媒体Word与Excel。

## 0.3.0 的执行方式

完整流程写在 [原模板逐章生成说明](.codebuddy/skills/ruanwenjie-geo/references/template-generation.md)，[SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md)要求报告写作前完整阅读。WorkBuddy按指引直接执行：

- 问题按真实需求、具体诊断用途和信息增量筛选，不固定数量、不按分类凑题。
- 同事只填“问题、引用截图、答案”。只回传一个平台也直接完成本轮诊断和执行方案。
- 诊断保留原模板的用户决策路径、场景/竞品矩阵、信源覆盖、优化与标签或业务维度分析；客户正文呈现情况和分析。
- 执行保留总览、创作机制、本案口径、阶段七列表、维护、费用、客户动作、目标场景和逐篇原排期表（平台型十列、服务型九列），内容和媒体逐项对应。
- 未给不同预算时，默认建议目标及上限为20,000元；正式建议包已知费用达到18,000—20,000元，不能将两千元的零散小包交付。实际单价、数量和费用可复算，不添加虚构差额。
- 推荐媒体Word严格沿用指定原媒体规划表的两类清单、16/17列表头、列序与分组，未知价档留空。
- WorkBuddy自己分析和撰写，脚本只做资源检索、计算与排版；不等用户再次解释下一步。

客户报告按原版结构输出PDF，随包虚构示例用于验证章节、矩阵、逐篇表与版式。推荐媒体另有可填充Word模板。原案例篇数、客户事实和经验机制不会作为新客户默认事实。

## 内置媒体资源

技能随包提供 **91,628条媒体资源目录**（网络媒体11,930条、自媒体79,698条），默认由media.py直接查询，不需要同事再上传媒体报价。

目录保留资源身份、业务分类、地域、可发限制、市场参考价和原记录索引，报价日期为2026-11-10。具体媒体及刊发形态必须从目录选，不能用“行业媒体若干”或TBD占位。

本仓库公开，目录去掉联系方式、供应商身份和代理成本档。市场参考价用于建议媒体发布预算，不能冒充已确认客户售价或内部结算成本；用户另给更新报价时优先使用新文件。原始客户资料、实采回答和私人报价文件不随包分发。

## 在 WorkBuddy 安装或更新

可以把这段交给WorkBuddy：

> 从公开仓库 https://github.com/zhuyi041107-cloud/geo-skill 更新 ruanwenjie-geo 到0.3.0，保留客户原件和本地改动备份。完整保留脚本、参考、字体、媒体库及模板，按requirements.txt检查依赖。先完整读references/template-generation.md及template-contract.json，复用已有判读，按原模板重新编写结构化report并规划约2万元预算，不直接重导0.2.0的旧report。

支持终端和Node.js时，也可在目标项目使用：

```bash
npx skills add zhuyi041107-cloud/geo-skill --skill ruanwenjie-geo -a codebuddy --copy
```

WorkBuddy项目配置兼容 `.codebuddy/skills/`；本仓库的技能已位于该目录。也可下载 [0.3.0 ZIP](dist/ruanwenjie-geo-0.3.0.zip)，在「技能 → 添加技能 → 上传技能」导入。更新后新开会话。

官方依据：[WorkBuddy项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[技能上传入口](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、[Skills CLI](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)。

## 使用

首次给客户资料时：

> 根据客户业务和目标生成真正有诊断价值的问题，交给我三列AI回答采集表，等我回传回答。

回传任意平台后：

> 按skill内的原模板逐章生成说明分析本轮回答与截图，直接用内置媒体库完成诊断PDF、执行方案PDF、推荐媒体Word、客户Excel和内部Excel。预算约2万元，已判读资料直接复用，不等其他平台。

默认交付：

- GEO诊断报告.pdf
- 品牌传播与GEO执行方案.pdf
- 推荐媒体.docx
- 客户诊断与执行明细.xlsx
- 内部诊断与执行明细.xlsx

客户Excel只呈现现状分析、关键词与内容排期、实际媒体和费用；内部底表保留核算及证据溯源。报告和表格中的数量、媒体、日期与预算来自同一组数据。

## 开发验证

```bash
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements.txt
python -m unittest discover -s tests -v
python tools/package_skill.py
```

测试使用虚构客户；检查完整模板契约、预算规模、费用一致性、表格与字体，并对PDF/Word渲染核验。发布包只含技能、通用模板、字体许可和脱敏媒体目录，不含真实客户输入/成品或私人报价。WorkBuddy实际运行表现仍需安装后验证。
