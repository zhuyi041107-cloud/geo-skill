# 软文街GEO诊断与执行规划

给WorkBuddy的内部业务技能：客户资料→三列人工AI回答采集→品牌与同行选择差距分析→固定8页诊断PDF、9页执行方案PDF和六档原价推荐媒体Excel。

## 0.10.1 本地版的执行方式

- WorkBuddy调度本地MCP，由GPT `gpt-6.1-sol`完成分析、方案和客户成稿，推理强度固定为API最高档`max`，模型上下文窗口1,050,000 tokens；现有脚本继续负责资源检索、量价核算与固定模板填充。最终成品再交GPT独立终审，检查原依据、模板与实际页图，通过后才交付。模型在MCP设置，连接后用`geo_status`核对。
- 按用户认可旧版的分析逻辑与版式，先解释品牌印象、同行差异、真实优势和商业场景，再推出内容、媒体、阶段交付与复核。
- 主体纠错、合规和售后说明与已有事实支撑的业务内容并行，不一律先做整批品牌身份稿；原案例的试课、专业匹配等机制不作为其他客户默认事实。
- 诊断恢复四列冲突表和双方分工表；执行恢复同行差异、四步2×2、三类媒体三卡、复核三列表和双档报价。
- 具体媒体仍从内置资源库筛选，客户方案按权威媒体、行业媒体、自媒体三类标用途、资源和数量；推荐表仍按来源分sheet1网络媒体、sheet2自媒体，六档原价保留。
- 默认普通权重、高权重两档，同内容、同稿数、同刊次；每档媒体费最低12,000元，按三类实际刊次核算，不虚加补差。原目录价与采购价独立，规则见[证据与费用](.codebuddy/skills/ruanwenjie-geo/references/evidence-and-planning.md)。
- 媒体费不含执行文章的AI起草、正文撰稿及人工修改。默认写作另收费，原价200元／篇、打包100元／独立稿；同时列媒体费、写作费及两档含写作总价。客户供稿不收写作费。
- 意向预算budget_target不自动当硬上限，只有客户明确不能超过才填写budget_limit。按有价值的实际内容与资源规模计算两档；72篇与三类24／36／12是旧例验算数量，不强制新客户沿用。
- 只给“问题、引用截图、答案”三列采集表，不限题数。收到任一平台回答即完成本轮报告，不催补模式、联网、时间、URL或其他平台。
- 客户正文说明情况、分析、选择理由、动作与费用，制作规则、原答、采集过程和内部核算留.work。

默认三件成品：GEO诊断报告.pdf、品牌传播与GEO执行方案.pdf、推荐媒体.xlsx。客户原件与旧成品保留，更新技能本身不重做真实客户报告；维护验证使用虚构资料。

完整指引：[SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md)、[固定页式生成说明](.codebuddy/skills/ruanwenjie-geo/references/template-generation.md)、[PDF契约](.codebuddy/skills/ruanwenjie-geo/references/pdf-output.md)。

## 在WorkBuddy安装或更新

从[公开GitHub仓库](https://github.com/zhuyi041107-cloud/geo-skill)获取0.10.1，或下载[0.10.1完整技能ZIP](dist/ruanwenjie-geo-0.10.1.zip)。将`.codebuddy/skills/ruanwenjie-geo`完整复制到目标项目同路径，保留脚本、背景、字体、媒体资源和依赖文件；ZIP内的顶层`ruanwenjie-geo`对应同一技能目录。先备份已有技能，客户工作目录和旧成品保持原样。

可将这段直接交给WorkBuddy：

> 从公开仓库https://github.com/zhuyi041107-cloud/geo-skill安装0.10.1到当前项目。先备份旧技能，完整复制.codebuddy/skills/ruanwenjie-geo，确认SKILL.md版本0.10.1。读取references/local-mcp.md，找到本机可用Python 3.10+，执行scripts/setup_local_mcp.ps1并把WorkBuddyProject设为当前项目，合并配置时保留其他MCP。密钥只使用本机环境变量或隐藏输入，不在聊天窗口索取或展示；尚未配置时先完成安装，再给我本机隐藏输入命令。新会话重连ruanwenjie-geo并调用geo_status，核对gpt-6.1-sol、max及1050000模型上下文窗口，分别报告连接状态与密钥状态。本次只安装，不重新生成客户报告。

**安装技能后还要配置本地MCP。**按[本地MCP安装与运行说明](.codebuddy/skills/ruanwenjie-geo/references/local-mcp.md)执行`setup_local_mcp.ps1`，显式传入Python路径和WorkBuddy项目目录。脚本合并项目`.workbuddy/mcp.json`并保留其他MCP，配置`GEO_WORKSPACE`访问边界。需要保存密钥时使用`-SetApiKey`在本机隐藏输入；密钥用当前Windows用户DPAPI加密，不写入仓库或客户目录。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "技能目录\scripts\setup_local_mcp.ps1" -PythonExe "Python安装目录\python.exe" -WorkBuddyProject "WorkBuddy项目目录" -SetApiKey
```

在WorkBuddy中检查`ruanwenjie-geo`连接，再调用`geo_status`确认实际配置。未提供密钥仍可安装并检查连接，但GPT业务调用需要有效API Key及模型权限。安装技能不等于MCP已连接，密钥已配置也不等于真实API已验证。

本地MCP依赖使用`requirements-mcp.txt`，其中复用原`requirements.txt`。渲染不需要浏览器、Node、另外安装字体或GEO云连接器。GPT分析、成稿和终审会调用OpenAI API并产生API费用；这与客户媒体投放和执行文章写作报价分别核算。仍由同事手动采集，不启动监测、操作平台账号、下单或实际发布媒体。

[0.9.0 ZIP](dist/ruanwenjie-geo-0.9.0.zip)是历史版本，不含本地GPT MCP与本次新报价规则。技能目录与安装入口依据[官方项目说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[官方技能说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)；安装与真实调用状态分别以本次实际验证为准。

## 使用

首次提供客户资料：

> 按客户业务和采购决策生成有诊断价值的问题，给我“问题、引用截图、答案”三列采集表，等我回传。

回传任意平台回答：

> 使用本地GPT MCP，用现有回答直接完成诊断和执行方案，按固定模板写本客户的现状、同行差异、选择理由和商业场景。具体媒体分权威、行业、自媒体三类，普通和高权重两档同稿同刊，各档实际媒体费至少12,000元，写作单列收费并给含写作总价。意向预算不当硬上限，双方分工与费用包含范围一致。推荐媒体按网络/自媒体两sheet广泛列出并保留六档原价。实际成品经GPT独立终审，通过后只交两PDF和推荐媒体.xlsx，内部数据留.work。

推荐池来自media_recommendations，执行子集及两档费用来自placements和quote_options。两档资源清单及量价内部可追溯，宽推荐池标价总和不计客户支出。

## 内置媒体资源

随包网络媒体和自媒体目录保留资源身份、栏目、分类、地域、刊发条件、原记录索引及市场价格、超级代理、核心代理、高级代理、普通代理、普通会员六档原值。media.py的`--limit 0`读取相关检索全量再筛选；明确拒发剔除，限制保留。

三类客户售价不覆盖六档目录价，也不冒称已核采购价。来源、报价日期明确的更新文件优先；真实缺价保留空值，不用比例反算。公开仓库按用户要求保留六档报价，不分发供应商身份、实际联系方式、原始报价XLSX、真实客户材料或实采回答。

## 开发验证

0.10.1本地验收见[本地MCP验收记录](.codebuddy/skills/ruanwenjie-geo/references/local-mcp-verification.json)：安装后的独立环境中115项测试通过，真实SDK直连与Windows启动脚本握手通过，实际状态显示gpt-6.1-sol／max／1,050,000模型窗口。固定模板与版式未变，复用0.10.0虚构案例17页逐页对照及51项资源、306个六档价格单元格的一致性记录。模型响应使用明确的离线模拟，真实API调用、满窗口上下文与WorkBuddy界面端到端尚未验证。

```text
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements-mcp.txt
python -m unittest discover -s tests -v
python tools/package_skill.py
```

本地版分别验证接口请求与错误处理、MCP握手、路径边界、方案与价格校验、终审及交付门槛；真实API和WorkBuddy界面运行以本次实际执行结果为准。维护者用虚构数据核固定17页、三类具体媒体、两档量价与服务范围，逐页查看PDF和两sheet价格，不重做真实客户报告。

**历史0.9.0验收记录**见[旧版验收记录](.codebuddy/skills/ruanwenjie-geo/references/template-verification.json)：当时84项测试通过，两套虚构案例共34页PDF逐页检查；72稿验算例两档为20,400／28,800元，独立16稿例为4,200／6,000元。后者低于本次12,000元最低媒体费，不能用于新报价。旧版独立案例推荐媒体23项网络、11项自媒体，204个六档价格字段与目录逐值一致，中文空格路径迁移运行通过；这些只说明旧版结果，不作为0.10.0、真实API或WorkBuddy实机已通过的证据。
