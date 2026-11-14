# 软文街GEO诊断与品牌方案

0.13.0：按客户品牌、业务目标和内容设计两份PDF，不再固定8＋9页。WorkBuddy直接判读人工采集回答、形成诊断、规划内容与三类媒体并逐页自审；无需MCP、OpenAI API密钥或GEO云端工具。

本次更新只改技能及虚构验证资料，没有重做现有客户报告。

## 本版如何出方案

- 诊断发现同时写清事实、原因判断、业务影响和优先级；执行动作逐项承接诊断，说明内容、关键词、媒体作用、阶段、负责人、交付和复核。客户页面显示对应关系。
- 品牌决定配色、封面和页面组合。支持分析卡片、短文、对照表、阶段和报价等组件，长内容自动分页；所有实际页面仍须视觉检查，不能把程序通过当成内容质量通过。
- 报价以本次用户指令为准，支持单档或多档、整包或按量、已含或另计、客户供稿及待报价。意向预算不自动当硬上限，未知价格不算零；不自动套用旧最低价、档位或写作单价。
- 参考库包括此前明确提供的12组案例、24份原格式资料和业务摘要。学习分析逻辑与呈现方式，禁止将旧客户事实、旧价格及效果承诺套给新客户。
- 人工采集仍为“问题、引用截图、答案”三列。收到单个平台回答就完成该范围分析，不增加采集步骤。客户只收到诊断PDF和执行PDF；内部证据、核算及页面检查留在工作目录。
- 媒体分权威媒体、行业媒体、自媒体，解释各类用途；具体资源推荐继续使用独立的媒体推荐技能。本版不重写媒体库或采购价。

规则：[技能入口](.codebuddy/skills/ruanwenjie-geo/SKILL.md)、[业务思路](.codebuddy/skills/ruanwenjie-geo/references/strategy-playbook.md)、[本地命令](.codebuddy/skills/ruanwenjie-geo/references/commands.md)、[参考索引](.codebuddy/skills/ruanwenjie-geo/references/case-library/index.md)、[报价口径](.codebuddy/skills/ruanwenjie-geo/references/pricing-contract.md)。旧schema2固定版式仅保留兼容，规则归档中不作为新任务默认值。

## WorkBuddy安装或更新

以下指令可直接复制到WorkBuddy。参考原件较大，分为核心包及参考扩展包；必须装齐清单列出的所有包。直接克隆仓库也可复制完整`.codebuddy/skills/ruanwenjie-geo`目录。

```text
从 https://github.com/zhuyi041107-cloud/geo-skill 获取 dist/ruanwenjie-geo-0.13.0-install.json，按其中required_parts下载所有ZIP并核对bytes和SHA256。它们都在同一dist目录。将所有包解压到同一临时目录，合并成完整的ruanwenjie-geo目录，核对references/case-library/manifest.json中24份参考原件都存在且SHA256匹配。先备份现有技能，再完整替换本项目.codebuddy/skills/ruanwenjie-geo，核对SKILL.md版本0.13.0；只安装requirements.txt。不要混入旧版文件，不启用MCP或外部GPT，不修改其他技能、MCP配置、客户资料或既有报告。后续按SKILL.md和references/commands.md，以schema_version=3.0按本案品牌设计PDF、使诊断与动作对应、按我本次指令报价。此次只安装并自检，不重做客户报告，完成后告诉我已安装版本并提示新开对话使用。
```

安装清单：[0.13.0全部包](dist/ruanwenjie-geo-0.13.0-install.json)。本地需要Python3.10以上及requirements.txt的三个依赖。仓库保留旧API/MCP历史源码，本版安装包不含这些服务和依赖。

## 维护验证

测试包含报价与关联校验、新旧导出兼容、中文空格目录迁移安装、禁止MCP/API导入和网络的本地流水线、完整参考包校验；另用两个不同业务的虚构客户实际生成四份PDF并逐页查看。94项测试通过；珠宝与工业两个虚构客户共27页逐页验证，记录见[0.13.0验证记录](verification/0.13.0.json)。本轮测试成品及新客户工作资料不进入公开仓库；此前授权的案例副本仅作为参考库分发。

```text
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements.txt
python -m unittest discover -s tests -p "test_brand*.py" -v
python -m unittest discover -s tests -p "test_geo_data.py" -v
python -m unittest discover -s tests -p "test_gpt_evidence.py" -v
python -m unittest discover -s tests -p "test_export_pdf.py" -v
python -m unittest discover -s tests -p "test_render_layout.py" -v
python -m unittest discover -s tests -p "test_client_language.py" -v
python -m unittest discover -s tests -p "test_skill_portability.py" -v
python tools/package_skill.py
```

本地PDF、程序校验和模拟安装与WorkBuddy界面安装验收分别记录。AI采用、推荐和业务转化按真实后续表现观察，不承诺增长比例。
