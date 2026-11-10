# 软文街 GEO 诊断与执行规划

给WorkBuddy使用的内部业务技能：客户资料 → 三列AI回答采集表 → 填写固定HTML原模板 → 诊断PDF、执行方案PDF、含六档原报价的推荐媒体Excel。

## 0.7.0 的执行方式

完整流程写在 [原模板逐章生成说明](.codebuddy/skills/ruanwenjie-geo/references/template-generation.md)，[SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md)要求报告写作前完整阅读。WorkBuddy按指引直接执行：

- 问题按真实需求、具体诊断用途和信息增量筛选，不固定数量、不按分类凑题。
- 同事只填“问题、引用截图、答案”。只回传一个平台也直接完成本轮诊断和执行方案。
- PDF改用按原稿复刻的四份固定HTML，分别对应platform/service的诊断与执行。BeautifulSoup只填纯文本和固定数据行，本机Chrome/Edge无界面打印；没有ReportLab回退，也不让模型自由重排。
- 写作前先读对应HTML及templates/pdf-template-manifest.json的文字槽、段落与表绑定清单。manifest记录模板SHA；客户生成阶段只填数据，不改模板、CSS、清单或生成器，也不另写临时PDF脚本。
- 诊断保留原模板的用户决策路径、场景/竞品矩阵、信源覆盖、优化与标签或业务维度分析；客户正文呈现情况和分析。
- 执行保留总览、创作机制、本案口径、阶段七列表、维护、费用、客户动作、目标场景和逐篇原排期表（平台型十列、服务型九列），内容和媒体逐项对应。
- 平台型使用原费用报价卡和三块两列场景清单，阶段/季度费用及实际媒体长清单留内部或推荐Excel。状态格按枚举填短值，名单与分析放说明列；不拿长段撑大格子。
- report保留sections，plan保留内部logic_links；fields只填固定文字槽，blocks只填原段落位置，diagnosis.priority_cards填四行优先卡，layer_questions填四条已有问法。字段说明见 [PDF填写规范](.codebuddy/skills/ruanwenjie-geo/references/pdf-output.md)。
- 模板一致包括论证逻辑：决策环节不借错证据，诊断缺口推出品牌选择理由，再推出文章、信源角色、阶段投入与交付。内部logic_links校验引用与时点，业务语义仍需WorkBuddy逐项审查。
- 未给不同预算时，默认建议目标及上限为20,000元；正式建议包已知费用达到18,000—20,000元，不能将两千元的零散小包交付。实际单价、数量和费用可复算，不添加虚构差额。
- 推荐媒体.xlsx的sheet1、sheet2分别放网络媒体、自媒体，沿用原规划表的16/17列、列序、列宽、配色与合并分组，六档原报价自动填齐，仅原表缺价时留空。
- 推荐池与预算脱钩：网络媒体、自媒体分开广泛列适配资源，不限制条数。`media_recommendations`供推荐媒体Excel，`placements`只计实际执行费用；不能把预算内已选名单当全部推荐。
- 默认只交两个PDF和一个推荐媒体.xlsx：sheet1网络媒体、sheet2自媒体；内部判读/核算留在.work。
- 客户正文直接写品牌情况、分析和执行安排；采集模式、回答条数、观察基础和判读教程留内部。保留原模板，只替换客户内容。
- WorkBuddy自己分析和撰写，脚本只做资源检索、计算与排版；不等用户再次解释下一步。

模板只固定显示形式，不替代WorkBuddy的业务判断。原案例篇数、客户事实与经验机制不作为新客户默认事实；随包只提供空槽HTML、虚构示例和推荐媒体Excel模板。

## PDF运行环境

需要本包Python依赖、本机Chrome或Edge，以及系统微软雅黑常规与粗体。生成器核对PDF实际字体；缺浏览器、缺字库或打印失败时拒绝交付，不用Noto伪粗体、缩字或通用排版器代替。微软雅黑不随包分发，字体缺项先恢复运行环境。PDF生成不依赖Node、CDP或Codex私有运行时；下面的可选安装CLI需要Node。

## 内置媒体资源

技能随包提供 **91,628条媒体资源目录**（网络媒体11,930条、自媒体79,698条），默认由media.py直接查询，不需要同事再上传媒体报价。

目录保留资源身份、分类、地域、可发限制、原记录索引及六档原价：市场价格、超级代理、核心代理、高级代理、普通代理、普通会员，报价日期为2026-11-10。推荐媒体Excel按推荐池自动补齐六档，不计算折扣；`--limit 0`读取相关匹配全量，不只选默认前30条。明确拒发剔除，有条件资源保留限制。

本仓库公开，按用户要求内置六档价格；供应商身份与实际联系方式继续排除。执行预算默认采用市场参考价，有明确选用档位或客户售价时按该口径计算。原始XLSX、真实客户资料与实采回答不随包分发；更新报价优先于旧目录。

## 在 WorkBuddy 安装或更新

可以把这段交给WorkBuddy：

> 从公开仓库 https://github.com/zhuyi041107-cloud/geo-skill 更新 ruanwenjie-geo 到0.7.0，保留客户原件与旧成品。生成前读取对应固定HTML和manifest绑定，只填report/plan数据，调用随包生成器用本机Chrome/Edge与微软雅黑常规、粗体打印，不改模板或另写PDF脚本。按原推导逻辑核对“诊断缺口→品牌选择理由→文章→媒体角色→阶段投入与交付”。推荐池独立于2万元执行预算，网络/自媒体分别广泛筛选。默认只交两PDF和推荐媒体.xlsx（sheet1网络媒体、sheet2自媒体），内部数据留.work；更新skill本身不重做真实客户成品。

支持终端和Node.js时，也可在目标项目使用：

```bash
npx skills add zhuyi041107-cloud/geo-skill --skill ruanwenjie-geo -a codebuddy --copy
```

WorkBuddy项目配置兼容 `.codebuddy/skills/`；本仓库的技能已位于该目录。也可下载 [0.7.0 ZIP](dist/ruanwenjie-geo-0.7.0.zip)，在「技能 → 添加技能 → 上传技能」导入。更新后新开会话。

官方依据：[WorkBuddy项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[技能上传入口](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、[Skills CLI](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)。

## 使用

首次给客户资料时：

> 根据客户业务和目标生成真正有诊断价值的问题，交给我三列AI回答采集表，等我回传回答。

回传任意平台后：

> 按固定HTML的原结构和推导逻辑填写客户内容，只改数据。推荐媒体按网络/自媒体分开广泛列出，不限于预算内已选媒体。约2万元只约束实际执行方案。直接给两PDF与六档原价推荐媒体Excel（sheet1网络媒体、sheet2自媒体），复用已有判读，不加采集说明或内部工作表。

默认交付：

- GEO诊断报告.pdf
- 品牌传播与GEO执行方案.pdf
- 推荐媒体.xlsx

两个旧明细Excel不默认交付。内部记录与核算留.work；明确要诊断/执行明细Excel才按需导出。推荐媒体.xlsx属于默认客户成品。PDF中的执行费用来自placements，推荐媒体Excel资源来自更广的media_recommendations，推荐池标价总额不计作客户预算。旧文件保留原样。

## 开发验证

```bash
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements.txt
python -m unittest discover -s tests -v
python tools/package_skill.py
```

开发验证分开记录三类证据：代码与引用/金额检查、固定模板同原文私有重放、宿主安装运行。模板由维护者使用已经提供的原文逐页对照原稿，检查字体字重、图形、列宽、网格、胶囊、合并、续表与断页；程序成功、页数相同或虚构示例好看均不等于原模板验收通过。manifest的SHA只确认固定文件未改，不证明视觉一致。

公开仓库和迁移包只放空槽模板与虚构示例，不放原客户PDF、页面截图、重放上下文或实采资料。私有重放不是要求同事重新采集，也不授权为测试skill重做客户成品。推荐池与Excel检查使用虚构客户；业务语义由WorkBuddy逐项审查，具体完成范围以实际验收记录为准。WorkBuddy实机兼容仍需单独安装验证。
