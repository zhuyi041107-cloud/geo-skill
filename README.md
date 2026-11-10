# 软文街 GEO 诊断与执行规划

给内部业务同事使用的 WorkBuddy 技能：客户素材 → AI问题与人工采集表 → 回答及引用诊断 → 品牌传播与GEO执行计划 → PPT、Excel。

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

也可克隆本仓库后，在 WorkBuddy 中以该目录作为项目使用；项目技能已经放在正确路径。[ZIP备用包](dist/ruanwenjie-geo-0.1.0.zip)可在「专家·技能·连接器 → 技能 → 添加技能 → 上传技能」导入。完成安装后新建项目会话；若对话无法自动安装，使用上述CLI或上传ZIP。

官方依据：[WorkBuddy 项目技能目录](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)、[技能安装及上传入口](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)。

## 使用

首次上传 `软文街_GEO客户素材收集表.xlsx`，说：

> 用软文街GEO诊断技能检查资料，按我的客户业务生成采样问题和AI回答采集表。先完成采集准备，等我回传实采结果再诊断。

回传填写后的采集表及证据附件，说：

> 保留原始回答，核验引用并补充判读，输出按平台和采样条件分组的GEO诊断。资料不足或链接打不开的地方标为待核验。

再提供最新媒体报价、指定报价档位、对客价格口径、年度预算和执行周期，说：

> 按诊断缺口制定品牌传播与GEO年度计划，按季度排期，筛除不接当前题材的资源，输出客户PPT、客户Excel和内部核算Excel。全部数字从同一明细计算。

包内模板包括客户素材表、AI回答采集表、诊断与执行Excel、诊断PPT、执行方案PPT。采集阶段由同事填原始回答和来源；WorkBuddy完成判读并保留待核验项。媒体报价体积较大且会变化，使用时单独提供，不写进技能正文。

## 安装后验证

1. 让WorkBuddy列出技能实际路径和模板，检查运行依赖能导入。
2. 使用空白客户表，确认它提示核心资料缺项，而非生成真实诊断。
3. 用一份客户资料生成问题和Excel；检查自然题没有预埋客户品牌。
4. 回传少量真实采样和引用，检查失败/未采/待判不会被当作未提及；查看分子、分母与来源。
5. 提供少量真实选用媒体和预算，生成PPT/Excel，核对内容篇数、刊发次数、费用与未定价格，确认客户文件没有内部成本字段。

本地自动检查在 `tests/`；它们验证数据逻辑和文件导出，不代替WorkBuddy客户端安装及真实AI网页采样验收。

## 开发核验与打包

在仓库根目录，安装技能requirements后执行：

```bash
python -m unittest discover -s tests -v
python tools/package_skill.py
```

打包命令核对必需文件、ZIP完整性和归档内容，生成ZIP及SHA-256校验文件。只打包canonical技能目录中的正式资源；客户数据、报价和本地预览不会进入安装包。

## 0.1.0 验证范围（2026-11-10）

27项本地行为测试通过；技能格式及相对资源链接检查通过。另用独立虚构项目跑通采集准备、回答分析、媒体筛选、内外Excel及两份PPT导出，复验非新对话/缺时间、缺价及候选项边界。Excel与PPT模板及填充稿已做渲染检查。

尚未在真实WorkBuddy客户端安装运行，也未在PowerPoint/WPS中验证原生重算；没有进行真实客户AI网页采样。这些结果证明本地包和数据流程可运行，业务效果与客户端兼容性需安装后验证。
