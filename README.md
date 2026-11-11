# 软文街GEO诊断与执行规划

WorkBuddy内部技能：客户资料 → 三列人工AI回答采集 → GPT分析品牌与同行选择差距 → 固定8页诊断PDF和9页执行方案PDF。新版0.11.0不检索或推荐具体媒体，不生成推荐媒体表，也不向模型发送媒体候选；旧客户文件和历史成果保留。

## 执行方式

- 本地MCP调用GPT `gpt-6.1-sol`，推理`max`、后台提交。返回pending后每15至30秒用`geo_resume_task(run_dir)`查询同一任务，只有completed且业务产物齐备才推进。
- 使用实际客户资料、原答和截图，区分品牌点名认知、自然候选与明确推荐；不编造未调查平台或未经证实的事实。
- 按权威媒体、行业媒体、自媒体三类安排传播用途与计划刊次，但不列具体媒体、账号或栏目。普通、高权重两档同内容、同稿数、同刊次；具体媒体、刊发条件和两档实际权益差异待确认，不能冒称已落实或保证效果。
- 两档各计划媒体费最低12,000元，写作默认单列原价200元/篇、打包100元/独立稿；客户供稿不收写作费。`budget_target`为意向预算，只有客户明确不能超过才设`budget_limit`。
- 两份PDF先在客户`.work`生成；GPT独立终审读取实际17页和原模板，只有`status=completed`且`passed=true`、审后哈希未变才能`geo_publish`到新的交付目录。
- 原资料、采集表、旧候选和旧成品保留。客户数据、原答、截图、请求结果与成品不上传公共仓库。

完整规则：[SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md)、[本地MCP安装与续跑](.codebuddy/skills/ruanwenjie-geo/references/local-mcp.md)、[固定页式生成说明](.codebuddy/skills/ruanwenjie-geo/references/template-generation.md)。

## 在WorkBuddy安装

从[GitHub仓库](https://github.com/zhuyi041107-cloud/geo-skill)获取0.11.0，或下载[0.11.0完整技能ZIP](dist/ruanwenjie-geo-0.11.0.zip)。备份旧技能后，把`.codebuddy/skills/ruanwenjie-geo`完整复制到项目相同路径；ZIP顶层`ruanwenjie-geo`即技能目录。仓库为历史兼容仍保留旧媒体脚本及目录，0.11.0 ZIP不包含这些文件，新MCP也不使用它们。客户工作目录和旧成品不动。安装后按[本地MCP说明](.codebuddy/skills/ruanwenjie-geo/references/local-mcp.md)配置并重连，密钥仅使用本机环境变量或DPAPI隐藏输入，不在聊天中展示。

可交给WorkBuddy：

> 从GitHub获取0.11.0并备份更新当前项目的ruanwenjie-geo技能；保留客户原件、已有分析、候选和旧成品。按references/local-mcp.md重连本地MCP，确认gpt-6.1-sol、max、background和geo_resume_task。本版不检索或推荐具体媒体，不传候选文件、不生成推荐表，仅在通过GPT终审后交付两份PDF。先检查现有run状态；失败、过期或未知时停止，不自动发起新的付费请求。

已有失败方案若要复用分析继续，只有用户明确授权新付费请求，才在`geo_create_plan`传入与当前失败检查点匹配的`retry_failed_response_id`；原任务与检查点保留，pending继续查新任务。失败、过期、未知或没有ID的情况不可通过篡改文件绕过。详细步骤见[本地MCP说明](.codebuddy/skills/ruanwenjie-geo/references/local-mcp.md)。

## 验证

旧版0.10.2曾通过真实API续跑、付费修正和两轮终审生成三件旧版成品；另一次真实任务因海量媒体候选触发上下文超限。0.11.0采用新的无候选流程，不能把旧版真实运行冒称新版真实验收。[0.11.0验收记录](.codebuddy/skills/ruanwenjie-geo/references/local-mcp-verification-0.11.0.json)记录154项自动化测试通过；未运行新版真实付费全流程，也未验证WorkBuddy界面。维护时使用虚构资料，不重做或覆盖真实客户报告。

```text
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements-mcp.txt
python -m unittest discover -s tests -v
python tools/package_skill.py
```
