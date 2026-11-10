# 软文街 GEO 诊断与执行规划

给WorkBuddy使用的内部业务技能：客户资料 → 有真实诊断价值的问题 → 三列AI回答采集表 → 品牌现状与差距分析 → 内容、媒体、排期和预算 → PDF与Excel。

## 0.2.0 的执行方式

完整业务思路写在 [SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md) 和 [报告分析思路](.codebuddy/skills/ruanwenjie-geo/references/report-thinking.md) 中，WorkBuddy按指引直接执行：

- 问题按真实需求、具体诊断用途和信息增量筛选，不固定数量、不按分类凑题。
- 同事只填“问题、引用截图、答案”。只回传一个平台也直接完成本轮诊断和执行方案。
- 诊断写品牌现状、用户入口、竞品差异、事实一致性、信源结构与业务影响；客户正文不放“如何诊断”、后台方法、ID或本机路径。
- 执行方案将实际问题落到关键词、内容选题、真实媒体、数量、季度、费用和预期交付。
- WorkBuddy自己分析和撰写，脚本只做资源检索、计算与排版；不等用户再次解释下一步。

最终客户报告为A4蓝色报告体PDF，叙述和紧凑业务表格结合。版式参考是包内两份虚构示例，不再生成PPT。

## 内置媒体资源

技能随包提供 **91,628条媒体资源目录**（网络媒体11,930条、自媒体79,698条），默认由media.py直接查询，不需要同事再上传媒体报价。

目录保留资源身份、业务分类、地域、可发限制、市场参考价和原记录索引，报价日期为2026-11-10。具体媒体及刊发形态必须从目录选，不能用“行业媒体若干”或TBD占位。

本仓库公开，目录去掉联系方式、供应商身份和代理成本档。市场参考价用于建议媒体发布预算，不能冒充已确认客户售价或内部结算成本；用户另给更新报价时优先使用新文件。原始客户资料、实采回答和私人报价文件不随包分发。

## 在 WorkBuddy 安装或更新

可以把这段交给WorkBuddy：

> 从公开仓库 https://github.com/zhuyi041107-cloud/geo-skill 安装或更新 ruanwenjie-geo 到0.2.0，保留客户工作目录和本地自定义改动的备份。保留技能中的脚本、参考、字体、内置媒体目录及模板，按requirements.txt检查运行依赖。随后按SKILL.md里的业务思路执行，不输出PPT。

支持终端和Node.js时，也可在目标项目使用：

```bash
npx skills add zhuyi041107-cloud/geo-skill --skill ruanwenjie-geo -a codebuddy --copy
```

WorkBuddy项目配置兼容 `.codebuddy/skills/`；本仓库的技能已位于该目录。也可下载 [0.2.0 ZIP](dist/ruanwenjie-geo-0.2.0.zip)，在「技能 → 添加技能 → 上传技能」导入。更新后新开会话。

官方依据：[WorkBuddy项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[技能上传入口](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、[Skills CLI](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)。

## 使用

首次给客户资料时：

> 根据客户业务和目标生成真正有诊断价值的问题，交给我三列AI回答采集表，等我回传回答。

回传任意平台后：

> 按skill内的思路，分析这轮回答与截图，直接使用内置媒体资源完成诊断PDF、执行方案PDF、客户Excel和内部核算Excel。已有判读直接复用，不等其他平台，不追问模式时间，也不输出处理流程。

默认交付：

- GEO诊断报告.pdf
- 品牌传播与GEO执行方案.pdf
- 客户诊断与执行明细.xlsx
- 内部诊断与执行明细.xlsx

客户Excel只呈现现状分析、关键词与内容排期、实际媒体和费用；内部底表保留核算及证据溯源。报告和表格中的数量、媒体、日期与预算来自同一组数据。

## 开发验证

```bash
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements.txt
python -m unittest discover -s tests -v
python tools/package_skill.py
```

测试使用虚构数据；PDF进行文本、字体、分页及渲染检查。发布包只包含技能、通用模板、字体许可及脱敏媒体目录，不包含被审阅客户的成品或输入。实际WorkBuddy运行表现仍需安装后验证。
