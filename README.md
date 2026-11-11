# 软文街GEO诊断与执行规划

给WorkBuddy的内部业务技能：客户资料→三列人工AI回答采集→品牌与同行选择差距分析→固定8页诊断PDF、9页执行方案PDF和六档原价推荐媒体Excel。

## 0.9.0的执行方式

- 按用户认可旧版的分析逻辑与版式，先解释品牌印象、同行差异、真实优势和商业场景，再推出内容、媒体、阶段交付与复核。
- 主体纠错、合规和售后说明与已有事实支撑的业务内容并行，不一律先做整批品牌身份稿；原案例的试课、专业匹配等机制不作为其他客户默认事实。
- 诊断恢复四列冲突表和双方分工表；执行恢复同行差异、四步2×2、三类媒体三卡、复核三列表和双档报价。
- 具体媒体仍从内置资源库筛选，客户方案按权威媒体、行业媒体、自媒体三类标用途、资源和数量；推荐表仍按来源分sheet1网络媒体、sheet2自媒体，六档原价保留。
- 默认普通权重、高权重两档，同内容、同稿数、同刊次；客户售价按旧版三类口径核算，原目录价与采购价独立。基本服务、人工写稿增项与两档完整总价同源，规则见[证据与费用](.codebuddy/skills/ruanwenjie-geo/references/evidence-and-planning.md)。
- 按实际内容与资源规模计算两档，有明确硬预算才限制；72篇与三类24／36／12是旧例验算数量，不强制新客户沿用。
- 只给“问题、引用截图、答案”三列采集表，不限题数。收到任一平台回答即完成本轮报告，不催补模式、联网、时间、URL或其他平台。
- 客户正文说明情况、分析、选择理由、动作与费用，制作规则、原答、采集过程和内部核算留.work。

默认三件成品：GEO诊断报告.pdf、品牌传播与GEO执行方案.pdf、推荐媒体.xlsx。客户原件与旧成品保留，更新技能本身不重做真实客户报告；维护验证使用虚构资料。

完整指引：[SKILL.md](.codebuddy/skills/ruanwenjie-geo/SKILL.md)、[固定页式生成说明](.codebuddy/skills/ruanwenjie-geo/references/template-generation.md)、[PDF契约](.codebuddy/skills/ruanwenjie-geo/references/pdf-output.md)。

## 在WorkBuddy安装或更新

下载或克隆仓库，将`.codebuddy/skills/ruanwenjie-geo`完整复制到目标项目同路径，保留脚本、背景、字体、媒体资源和依赖文件，新开会话。先备份已有技能，客户工作目录和旧成品保持原样。

也可下载[0.9.0 ZIP](dist/ruanwenjie-geo-0.9.0.zip)，在“专家·技能·连接器→技能→添加技能→上传技能”导入。目录与入口依据[官方项目说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[官方技能说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)。

可将下面文字交给WorkBuddy安装：

> 从公开仓库 https://github.com/zhuyi041107-cloud/geo-skill 获取0.9.0，将完整.codebuddy/skills/ruanwenjie-geo复制到当前项目同路径。保留旧技能备份、客户原件与既有成品，更新不重做客户报告。新技能使用固定8页诊断、9页执行，客户正文按品牌与同行差异形成具体选择理由；选具体资源并分权威、行业、自媒体三类，提供普通和高权重两档及明确含服务，推荐表继续两sheet六档原价。完成文件安装后报告实际状态，新会话使用。

Python公共依赖使用随包requirements.txt。生成不需要浏览器、Node、另外安装字体或GEO云连接器；不自动采集、调用收费模型、启动监测、操作账号或执行发布。文件安装、本地运行与WorkBuddy界面实测分别确认。

## 使用

首次提供客户资料：

> 按客户业务和采购决策生成有诊断价值的问题，给我“问题、引用截图、答案”三列采集表，等我回传。

回传任意平台回答：

> 用现有回答直接完成诊断和执行方案，按固定模板写本客户的现状、同行差异、选择理由和商业场景。具体媒体分权威、行业、自媒体三类，普通和高权重两档同稿同刊，双方分工与费用包含范围一致。推荐媒体按网络/自媒体两sheet广泛列出并保留六档原价。只交两PDF和推荐媒体.xlsx，内部数据留.work。

推荐池来自media_recommendations，执行子集及两档费用来自placements和quote_options。两档资源清单及量价内部可追溯，宽推荐池标价总和不计客户支出。

## 内置媒体资源

随包网络媒体和自媒体目录保留资源身份、栏目、分类、地域、刊发条件、原记录索引及市场价格、超级代理、核心代理、高级代理、普通代理、普通会员六档原值。media.py的`--limit 0`读取相关检索全量再筛选；明确拒发剔除，限制保留。

三类客户售价不覆盖六档目录价，也不冒称已核采购价。来源、报价日期明确的更新文件优先；真实缺价保留空值，不用比例反算。公开仓库按用户要求保留六档报价，不分发供应商身份、实际联系方式、原始报价XLSX、真实客户材料或实采回答。

## 开发验证

```text
python -m pip install -r .codebuddy/skills/ruanwenjie-geo/requirements.txt
python -m unittest discover -s tests -v
python tools/package_skill.py
```

本版验收范围见[验收记录](.codebuddy/skills/ruanwenjie-geo/references/template-verification.json)。维护者用虚构数据核固定17页、三类具体媒体、两档量价与服务范围，逐页查看PDF和两sheet价格；代码检查、视觉核对、迁移安装及WorkBuddy界面运行分开记录，旧版结果不作为本版通过证据。

0.9.0本地验收：84项测试通过，两套虚构案例共34页PDF逐页检查。72稿验算例两档为20,400／28,800元；独立16稿案例两档为4,200／6,000元，证明不会强套历史稿量。独立案例推荐媒体23项网络、11项自媒体，204个六档价格字段与目录逐值一致；中文空格路径迁移运行通过。客户原报告和采集表未改，WorkBuddy界面实机尚未测试。
