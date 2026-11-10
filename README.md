# 软文街 GEO 诊断与执行规划

给内部业务同事使用的 WorkBuddy 技能：客户素材 → 核心需求问题与三列采集表 → 回答及截图诊断 → 品牌传播与GEO执行计划 → PPT、Excel。

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

也可克隆本仓库后，在 WorkBuddy 中以该目录作为项目使用；项目技能已经放在正确路径。[ZIP备用包](dist/ruanwenjie-geo-0.1.1.zip)可在「专家·技能·连接器 → 技能 → 添加技能 → 上传技能」导入。已安装旧版时更新到0.1.1，保留客户工作目录及本地自定义改动后新建会话；若对话无法自动安装，使用上述CLI或上传ZIP。

官方依据：[WorkBuddy 项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[技能安装及上传入口](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)。

## 使用

首次上传 `软文街_GEO客户素材收集表.xlsx`，说：

> 用软文街GEO诊断技能检查资料，根据我的客户业务和目标生成真正有诊断价值的问题，不按题数或分类凑题。给我只有“问题、引用截图、答案”三列的采集表，各AI平台分别一个文件，等我回传后再诊断。

回传填写后的采集表及证据附件，说：

> 根据三列表里的答案和引用截图做GEO诊断，保留原始证据，自动处理内部编号和判读。看不清的截图、未记录的采样条件与未核验来源如实说明，不让我再填复杂采集字段。

再提供最新媒体报价、指定报价档位、对客价格口径、年度预算和执行周期，说：

> 按诊断缺口制定品牌传播与GEO年度计划，按季度排期，筛除不接当前题材的资源，输出客户PPT、客户Excel和内部核算Excel。全部数字从同一明细计算。

问题生成按“真实用户为何会问、答案能判断什么、相比已有题新增什么信息”筛选并合并，不固定数量，不把行业科普或素材表字段逐项变成采样题。

包内模板包括客户素材表、三列AI回答采集表、诊断与执行Excel、诊断PPT、执行方案PPT。同事只填“引用截图、答案”，问题由WorkBuddy预填；平台用文件名区分。截图可直接粘到Excel，也可用同目录附件。内部判读底表由WorkBuddy维护，旧版已采数据仍兼容。媒体报价使用时单独提供。

## 安装后验证

1. 让WorkBuddy列出技能实际路径和模板，检查运行依赖能导入。
2. 使用空白客户表，确认它提示核心资料缺项，而非生成真实诊断。
3. 用一份客户资料生成问题和Excel；检查每题确有独立诊断用途，自然题没有预埋品牌，采集表只有三列。
4. 回传答案和引用截图，检查嵌图及附件保留、内部关联自动处理，失败/未采/待判不会被当作未提及；未记录采样条件时仍可描述性诊断并披露限制。
5. 提供少量真实选用媒体和预算，生成PPT/Excel，核对内容篇数、刊发次数、费用与未定价格，确认客户文件没有内部成本字段。

本地自动检查在 `tests/`；它们验证数据逻辑和文件导出，不代替WorkBuddy客户端安装及真实AI网页采样验收。

## 开发核验与打包

在仓库根目录，安装技能requirements后执行：

```bash
python -m unittest discover -s tests -v
python tools/package_skill.py
```

打包命令核对必需文件、ZIP完整性和归档内容，生成ZIP及SHA-256校验文件。只打包canonical技能目录中的正式资源；客户数据、报价和本地预览不会进入安装包。

## 0.1.1 验证范围（2026-11-10）

33项本地行为测试通过，覆盖三列采集、截图关联、跨平台汇总、旧版数据兼容、预算和PPT/Excel导出；技能格式与资源链接检查通过。独立虚构项目已跑通三列表和截图导入到两份Excel、两份PPT，未记录采样条件时保留描述性诊断。另用不同行业检验问题生成规则，未按固定题数或类别凑题。模板已做渲染检查。

尚未在真实WorkBuddy客户端安装运行，也未在PowerPoint/WPS中验证原生重算；没有进行真实客户AI网页采样。这些结果证明本地包和数据流程可运行，业务效果与客户端兼容性需安装后验证。
