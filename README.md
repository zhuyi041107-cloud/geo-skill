# 软文街 GEO 诊断与执行规划

给内部业务同事使用的 WorkBuddy 技能：客户素材 → 核心需求问题与三列采集表 → 回传任一平台回答 → 直接交付诊断报告、执行方案的PPT和Excel。

技能目录：[`.codebuddy/skills/ruanwenjie-geo`](.codebuddy/skills/ruanwenjie-geo)。客户原件、媒体报价和历史方案不包含在安装包中；使用时提供当次文件，项目数据留在自己的工作目录。

## 从 GitHub 安装

本仓库公开，下载和安装无需 GitHub 私库授权。真实客户资料、AI实采回答和媒体报价仍由使用者在自己的工作目录单独提供。

可把下面这段发给 WorkBuddy：

> 请从公开GitHub仓库 https://github.com/zhuyi041107-cloud/geo-skill 安装技能 ruanwenjie-geo 到当前项目，保留SKILL.md、references、scripts和templates。使用项目级.codebuddy/skills目录，不覆盖已有不同内容的同名技能。检查Python 3.10+及requirements.txt依赖，缺失时说明并按本环境权限安装。安装完成后告诉我实际技能路径，再等我上传客户素材表开始第一阶段。

如果 WorkBuddy 有可用终端和 Node.js，可使用 [Vercel Skills CLI](https://github.com/vercel-labs/skills/blob/main/docs/commands.md) 安装到当前项目：

```bash
npx skills add zhuyi041107-cloud/geo-skill --list
npx skills add zhuyi041107-cloud/geo-skill --skill ruanwenjie-geo -a codebuddy --copy
```

`codebuddy` 是安装目标目录选项，WorkBuddy 官方项目配置兼容 `.codebuddy/skills/`；无需猜测一个 `workbuddy` CLI参数。CLI版本与Node要求以其官方说明为准。

也可克隆本仓库后，在 WorkBuddy 中以该目录作为项目使用；项目技能已经放在正确路径。[ZIP备用包](dist/ruanwenjie-geo-0.1.2.zip)可在「专家·技能·连接器 → 技能 → 添加技能 → 上传技能」导入。已安装旧版时更新到0.1.2，保留客户工作目录及本地自定义改动后新建会话；若对话无法自动安装，使用上述CLI或上传ZIP。

官方依据：[WorkBuddy 项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[技能安装及上传入口](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)。

## 使用

首次上传 `软文街_GEO客户素材收集表.xlsx`，说：

> 用软文街GEO诊断技能检查资料，根据我的客户业务和目标生成真正有诊断价值的问题，不按题数或分类凑题。给我只有“问题、引用截图、答案”三列的采集表，各AI平台分别一个文件，等我回传后再诊断。

回传填写后的采集表及证据附件，说：

> 这是本轮一个平台的答案和引用截图，按当前本轮日期、AI网页端联网采集处理。直接利用已有客户资料、报价和预算，完成诊断报告PPT、执行方案PPT、客户Excel和内部核算Excel。不等其他平台，不追问模式/联网/时间，不汇报导入和锚点处理过程；具体未确认项写在成品相应栏目。

媒体报价、对客价格口径、预算和周期可与客户材料一起提供，也可使用会话已有文件。未报价项在方案中标注，不影响先交付完整诊断和执行文件。后续新增平台回传再增量更新，不主动催补。

问题生成按“真实用户为何会问、答案能判断什么、相比已有题新增什么信息”筛选并合并，不固定数量，不把行业科普或素材表字段逐项变成采样题。

包内模板包括客户素材表、三列AI回答采集表、诊断与执行Excel、诊断PPT、执行方案PPT。同事只填“引用截图、答案”，问题由WorkBuddy预填；平台用文件名区分。截图可直接粘到Excel，也可用同目录附件。内部判读底表由WorkBuddy维护，旧版已采数据仍兼容。媒体报价使用时单独提供。

## 安装后验证

1. 让WorkBuddy列出技能实际路径和模板，检查运行依赖能导入。
2. 使用空白客户表，确认它提示核心资料缺项，而非生成真实诊断。
3. 用一份客户资料生成问题和Excel；检查每题确有独立诊断用途，自然题没有预埋品牌，采集表只有三列。
4. 只回传一个平台，确认本轮只统计此平台，截图位置偏列也能内部处理，不出现催补其他平台或采样元数据的清单。
5. 确认同一轮直接生成两份PPT与内外Excel；核对内容篇数、刊发次数、金额和缺价项，客户文件没有内部成本字段。

本地自动检查在 `tests/`；它们验证数据逻辑和文件导出，不代替WorkBuddy客户端安装及真实AI网页采样验收。

## 开发核验与打包

在仓库根目录，安装技能requirements后执行：

```bash
python -m unittest discover -s tests -v
python tools/package_skill.py
```

打包命令核对必需文件、ZIP完整性和归档内容，生成ZIP及SHA-256校验文件。只打包canonical技能目录中的正式资源；客户数据、报价和本地预览不会进入安装包。

## 0.1.2 验证范围（2026-11-10）

37项本地行为测试通过，覆盖三列采集、截图关联、已回传平台范围、旧版数据兼容、预算和PPT/Excel导出。单平台直接交付、同行截图偏列及未定位截图保留的回归检查通过；另验证了只回传一平台时两份PPT与内外Excel均能生成，另外平台不进入报告。模板视觉未变。

本次更新尚未由维护者在WorkBuddy客户端重跑，也未在PowerPoint/WPS中验证原生重算；测试使用虚构资料，不代表真实客户的优化效果。
