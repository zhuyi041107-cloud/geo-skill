# 软文街GEO诊断与执行规划

**0.12.0恢复无需MCP的使用方式。** WorkBuddy直接完成问题设计、回答判读、品牌与同行分析、方案成稿和逐页自审；本地脚本填充固定模板。无需OpenAI API密钥，也没有额外GPT付费请求或外部终审门槛。

客户资料 → “问题、引用截图、答案”三列人工采集表 → 回传任一平台回答 → 固定8页诊断PDF和9页执行PDF。保留0.11.0的分类规划：权威媒体、行业媒体、自媒体，不推荐具体媒体，不生成推荐表。旧报价资料和历史客户文件保留。

## 保留的业务规则

- 比较实际品牌印象、相关同行选择理由和客户真实优势，区分点名认知、自然候选与明确推荐；不编造未调查的平台或未经证实的事实。
- 固定旧版背景、版式、坐标及字号，只改内容。客户只收到情况、分析、安排、分工和费用；原答、采样条件、制作过程和内部核算留`.work`。
- 普通、高权重两档同内容、同稿数、同刊次。每档媒体费最低12,000元，写作另收费，默认原价200元／篇、打包100元／独立稿；客户供稿不收写作费。意向预算是参考，明确不能超过的预算才作为媒体与写作总额硬上限。
- 媒体按三类说明用途、计划刊次和费用；分类单价沿用450／200／200元及600／300／300元。具体媒体、刊发条件和两档实际权益差异待确认，不承诺AI采用或推荐。
- 两份PDF先在`.work`生成，另轮逐页检查17页后复制到新的正式输出目录。客户原件、旧成品、密钥和历史请求检查点不动。

规则：[SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md)、[本地执行命令](.codebuddy/skills/ruanwenjie-geo/references/commands.md)、[固定页式生成说明](.codebuddy/skills/ruanwenjie-geo/references/template-generation.md)。

## 在WorkBuddy安装或更新

下载[0.12.0完整技能ZIP](https://github.com/zhuyi041107-cloud/geo-skill/raw/refs/heads/main/dist/ruanwenjie-geo-0.12.0.zip)，解压后的`ruanwenjie-geo`完整目录放到项目`.codebuddy/skills/`。先备份旧技能，使用新目录替换，避免混入旧版文件。Python 3.10以上，只需安装技能目录的`requirements.txt`，不安装`requirements-mcp.txt`。

已装旧MCP时，仅停用或移除名为`ruanwenjie-geo`的服务条目，保留其他服务与配置备份；不用删除密钥或旧任务。新开对话，让WorkBuddy按新版技能直接执行。仓库保留旧API/MCP源文件供历史查阅，本版ZIP不含这些服务、安装脚本、配置或依赖；日常安装使用完整ZIP。

把下面这段发给WorkBuddy即可：

> 从 https://github.com/zhuyi041107-cloud/geo-skill 下载dist/ruanwenjie-geo-0.12.0.zip，先备份旧ruanwenjie-geo技能，再完整替换当前项目.codebuddy/skills/ruanwenjie-geo，核对SKILL.md版本0.12.0。只安装requirements.txt。若当前项目或用户配置仍启用旧ruanwenjie-geo MCP，备份配置并仅停用或移除该服务条目，保留其他MCP、密钥、客户资料、旧报告和历史任务。后续由你直接判读、分析、成稿和逐页自审，按references/commands.md运行本地脚本，不调用geo_* MCP工具，不等待外部GPT。保留三类媒体、两档费用、最低媒体费1.2万元与写作另收费规则。此次仅更新技能，不重做客户报告；完成后提示我新开对话使用。

## 验证

维护使用虚构资料，不重做客户报告。[0.12.0验证记录](.codebuddy/skills/ruanwenjie-geo/references/standalone-verification-0.12.0.json)记录69项测试通过，覆盖实际ZIP解压安装、三列表导入与判读副本、统计、固定模板导出、17页页数与尺寸、费用边界、客户语言和原件保护；同时禁止导入MCP/API模块及网络连接，证明本地执行不依赖服务。模板和渲染器未变，沿用已有版式视觉验收，不冒称本次重新人工逐页看图。WorkBuddy界面安装与实际客户成稿质量仍由用户安装验收。

```text
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements.txt
python -m unittest discover -s tests -p "test_geo_data.py" -v
python -m unittest discover -s tests -p "test_gpt_evidence.py" -v
python -m unittest discover -s tests -p "test_export_pdf.py" -v
python -m unittest discover -s tests -p "test_render_layout.py" -v
python -m unittest discover -s tests -p "test_client_language.py" -v
python -m unittest discover -s tests -p "test_skill_portability.py" -v
python tools/package_skill.py
```

`test_gpt_evidence.py`验证纯本地证据与判读副本，历史命名不代表调用GPT。旧MCP测试与历史运行记录留在仓库，不属于本版基础依赖或验收前提。真实客户数据、截图、回答、密钥与成品不得上传公开仓库。
