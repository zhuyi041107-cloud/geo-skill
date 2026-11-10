# 软文街 GEO 诊断与执行规划

给WorkBuddy使用的内部业务技能：客户资料 → 三列AI回答采集表 → 按原模板替换客户内容 → 诊断PDF、执行方案PDF、含六档原报价的推荐媒体Word。

## 0.4.0 的执行方式

完整流程写在 [原模板逐章生成说明](.codebuddy/skills/ruanwenjie-geo/references/template-generation.md)，[SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md)要求报告写作前完整阅读。WorkBuddy按指引直接执行：

- 问题按真实需求、具体诊断用途和信息增量筛选，不固定数量、不按分类凑题。
- 同事只填“问题、引用截图、答案”。只回传一个平台也直接完成本轮诊断和执行方案。
- 诊断保留原模板的用户决策路径、场景/竞品矩阵、信源覆盖、优化与标签或业务维度分析；客户正文呈现情况和分析。
- 执行保留总览、创作机制、本案口径、阶段七列表、维护、费用、客户动作、目标场景和逐篇原排期表（平台型十列、服务型九列），内容和媒体逐项对应。
- 未给不同预算时，默认建议目标及上限为20,000元；正式建议包已知费用达到18,000—20,000元，不能将两千元的零散小包交付。实际单价、数量和费用可复算，不添加虚构差额。
- 推荐媒体Word沿用原规划表的两类清单、16/17列、列序与分组，六档原报价自动填齐，仅原表缺价时留空。
- 默认只交两个PDF和推荐媒体Word，内部判读/核算留在.work，不再自动交两份自造Excel。
- 客户正文直接写品牌情况、分析和执行安排；采集模式、回答条数、观察基础和判读教程留内部。保留原模板，只替换客户内容。
- WorkBuddy自己分析和撰写，脚本只做资源检索、计算与排版；不等用户再次解释下一步。

客户报告按原版结构输出PDF，随包虚构示例用于验证章节、矩阵、逐篇表与版式。推荐媒体另有可填充Word模板。原案例篇数、客户事实和经验机制不会作为新客户默认事实。

## 内置媒体资源

技能随包提供 **91,628条媒体资源目录**（网络媒体11,930条、自媒体79,698条），默认由media.py直接查询，不需要同事再上传媒体报价。

目录保留资源身份、分类、地域、可发限制、原记录索引及六档原价：市场价格、超级代理、核心代理、高级代理、普通代理、普通会员，报价日期为2026-11-10。Word按所选媒体自动补齐六档，缺价才留空，不计算折扣。

本仓库公开，按用户要求内置六档价格；供应商身份与实际联系方式继续排除。执行预算默认采用市场参考价，有明确选用档位或客户售价时按该口径计算。原始XLSX、真实客户资料与实采回答不随包分发；更新报价优先于旧目录。

## 在 WorkBuddy 安装或更新

可以把这段交给WorkBuddy：

> 从公开仓库 https://github.com/zhuyi041107-cloud/geo-skill 更新 ruanwenjie-geo 到0.4.0，保留客户原件与旧成品。按SKILL.md只替换原模板中的客户内容，清除旧report里的采集/观察基础/样本说明。默认只交诊断PDF、执行方案PDF和原格式推荐媒体Word，六档原报价全部自动填入，内部JSON/判读/核算留.work。复用已有回答，预算约2万元。

支持终端和Node.js时，也可在目标项目使用：

```bash
npx skills add zhuyi041107-cloud/geo-skill --skill ruanwenjie-geo -a codebuddy --copy
```

WorkBuddy项目配置兼容 `.codebuddy/skills/`；本仓库的技能已位于该目录。也可下载 [0.4.0 ZIP](dist/ruanwenjie-geo-0.4.0.zip)，在「技能 → 添加技能 → 上传技能」导入。更新后新开会话。

官方依据：[WorkBuddy项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[技能上传入口](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、[Skills CLI](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)。

## 使用

首次给客户资料时：

> 根据客户业务和目标生成真正有诊断价值的问题，交给我三列AI回答采集表，等我回传回答。

回传任意平台后：

> 按原模板仅替换客户内容，直接给我诊断PDF、执行方案PDF、六档价格齐全的推荐媒体Word。预算约2万元，已有判读直接复用，不加采集说明，不交内部工作表。

默认交付：

- GEO诊断报告.pdf
- 品牌传播与GEO执行方案.pdf
- 推荐媒体.docx

两个旧明细Excel不再是默认交付。内部记录与核算留.work；用户明确要Excel时才单独导出指定版本。旧文件保留原样。客户报告与Word的媒体、数量和预算使用同一组计划数据。

## 开发验证

```bash
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements.txt
python -m unittest discover -s tests -v
python tools/package_skill.py
```

测试使用虚构客户；检查完整模板契约、预算规模、费用一致性、表格与字体，并对PDF/Word渲染核验。发布包只含技能、通用模板、字体许可和脱敏媒体目录，不含真实客户输入/成品或私人报价。WorkBuddy实际运行表现仍需安装后验证。
