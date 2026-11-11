# 本地 GPT MCP 安装

本地stdio服务由WorkBuddy启动，GPT固定使用`gpt-6.1-sol`，推理强度`max`。客户资料与手动采集流程沿用原技能；服务负责将本次所需资料和规则发送到OpenAI API。安装不重新生成客户报告，不部署共享服务器。

## 模型与上下文

模型在本地MCP的`scripts/gpt_client.py`配置，WorkBuddy主模型选择不会替代此处设置。当前固定`MODEL="gpt-6.1-sol"`、`REASONING_EFFORT="max"`；官方API推理档位为low、medium、high、xhigh、max，没有ultra档，也不把ultra冒充为API已支持的值。`geo_status`会返回model、reasoning_effort与model_context_window_tokens，便于连接后核对。

该模型官方API上下文窗口为1,050,000 tokens，覆盖输入、推理及输出；无需另发虚构的`context_window=1000000`参数。单次输出预算由各业务阶段的max_output_tokens设置，并受模型128,000输出上限约束，这不把模型上下文降为同样大小。每次请求显式truncation=disabled，超出上下文时失败，不静默裁掉客户材料。模型能力标注与账号实际权限、长上下文实测分开确认；提高推理强度可能增加调用时间及token用量。

## Windows 首次安装

先将整个技能目录放到长期保留的位置，在 PowerShell 执行以下命令；替换技能路径、Python 路径和当前 WorkBuddy 项目目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "技能目录\scripts\setup_local_mcp.ps1" -PythonExe "Python安装目录\python.exe" -WorkBuddyProject "WorkBuddy项目目录" -SetApiKey
```

`-SetApiKey` 会在本机隐藏输入密钥，使用 Windows 当前用户 DPAPI 加密保存到 `%LOCALAPPDATA%\RuanwenjieGEO\openai-key.dpapi`。密钥不写入 GitHub、MCP 配置或客户文件。已经通过进程环境变量配置 `OPENAI_API_KEY` 时可以省略此参数；launcher 优先使用环境变量。

脚本在 `%LOCALAPPDATA%\RuanwenjieGEO\runtime` 创建独立 Python 环境并安装随包依赖，向指定项目的 `.workbuddy\mcp.json` 合并 `ruanwenjie-geo` 服务，保留其他服务器配置，修改前备份已有文件。配置中的 `GEO_WORKSPACE` 为该项目的绝对路径，客户输入、运行目录与交付目录均须在此项目内。Python 需要 3.10 或更新版本，依赖安装需要网络。路径移动后重新运行安装脚本更新绝对路径。

未配置密钥也可以安装并启动 MCP，GPT 业务调用会明确报缺少密钥。API Key 不要发送到聊天窗口。

## 在 WorkBuddy 连接

打开安装时指定的项目，在“插件 → MCP服务器”检查 `ruanwenjie-geo` 状态；如果没有出现，在“配置MCP”核对项目 `.workbuddy\mcp.json`，必要时新开会话。安装 Skill 与配置 MCP 是两个步骤。

服务配置形状见 [workbuddy-mcp.example.json](workbuddy-mcp.example.json)。示例路径不能直接用于其他电脑，安装脚本会生成实际路径。MCP 配置超时为 1800 秒，以容纳两份 PDF 的逐页审核；模型请求失败不会自动改用 WorkBuddy 内置模型冒充 GPT 结果。

## WorkBuddy 执行顺序

安装后先调用 `geo_status` 检查本地配置，再按以下顺序执行：

1. 沿用原流程整理客户 `project.json`，将三列表通过原 `normalize` 命令导入内部判读 XLSX。原件保留，收到一个平台就继续，不要求补采其他平台或重新记录模式、联网、时间。
2. `geo_analyze_customer(workspace, project_file, answers_file)`：传入项目内的客户目录、项目 JSON 和内部判读 XLSX，交由 GPT 读取本次真实材料，返回本次 `run_dir`。后续操作统一使用该运行目录。
3. `geo_search_media(run_dir, query, kind='all', region='')`：按 GPT 给出的业务方向检索实际资源；可按多组关键词分别检索，记录返回的候选文件路径。推荐池保持广泛，不按执行预算截断推荐数量。
4. `geo_create_plan(run_dir, candidate_files, revision_instructions='')`：使用实际候选文件，由 GPT 形成具体选媒、内容、阶段和两档方案。本地脚本校验资源身份及量价。每档实际媒体费最低12,000元，依实际类别单价与刊次汇总，不虚加补差；执行文章写作不含在媒体费中，默认单列原价200元／篇、打包100元／独立稿及含写作总价。客户供稿不收写作费。`budget_target`只记意向预算，客户明确不能超过时才设`budget_limit`。
5. `geo_write_reports(run_dir, revision_instructions='')`：由 GPT 填写客户正文，使用原固定模板生成诊断 PDF、执行方案 PDF 和双 sheet 推荐媒体表。
6. `geo_review_deliverables(run_dir)`：独立调用 GPT，连同原材料、原模板及实际 PDF 页图审核事实、分析、媒体、费用、客户措辞和版式。根据问题回到方案或成稿步骤修改，再终审；最多两轮修正，仍不通过时保留内部草稿及具体问题，不标记已通过。
7. `geo_publish(run_dir, output_dir)`：仅在终审通过且成品未改动时，将三件客户成品复制到项目内的新交付目录。审核记录与制作材料保留内部，不交给客户。

`revision_instructions` 只传本轮需要修正的事项；具体分析、方案和成稿通过 GPT 工具完成。WorkBuddy 调度这些工具并说明实际状态，不自行绕过终审发布未通过的文件。

官方接入依据：[WorkBuddy MCP 指南](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)、[远程及本地传输与连接器凭证说明](https://open.workbuddy.cn/en/docs/connector)。

模型与请求依据：[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)、[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)。客户端固定官方端点，失败不会自动重试付费请求；大于本地64MB请求限制时明确报错并要求拆分，不静默漏答或漏图。

## 本地状态与验收

区分依赖安装、MCP 握手、真实 API 调用、WorkBuddy 界面运行和成品终审。密钥已保存只表示有本机凭证，不表示账号已获得模型权限或已完成真实调用。所有运行记录留在客户 `.work`，客户只收到原定三件成品。
