# 本地 GPT MCP 安装与续跑（0.10.2）

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

服务配置形状见 [workbuddy-mcp.example.json](workbuddy-mcp.example.json)。示例路径不能直接用于其他电脑，安装脚本会生成实际路径。MCP 配置超时为1800秒；0.10.2生成请求采用后台任务并及时返回pending，通过多次短查询完成，不靠单次同步连接一直等待。模型请求失败不会自动改用WorkBuddy内置模型冒充GPT结果，也不降低gpt-6.1-sol或max档位。

## 后台任务与持续查询

GPT分析、方案、成稿、终审均将请求记录保存在本次`run_dir/requests/`。任务ID取得后先落盘，后台仍在处理时返回`status="pending"`、`run_dir`、`response_id`和`resume_tool="geo_resume_task"`。这表示同一任务仍在进行，不表示业务步骤完成。

MCP的`isError:false`只表示工具正常返回，不等于业务完成。结果txt或JSON文件存在，也不能作为完成依据。仅`status="completed"`并且对应分析、方案、成稿或终审产物与业务字段齐备时，才能推进下一阶段。终审返回`status="completed", passed=false`表示审查已完成但未通过，应按问题修改并复审；只有`status="completed"`且`passed=true`，成品哈希也未改变时，才可调用`geo_publish`。旧续跑脚本若只按结果文件存在就跳过步骤，必须更新这一判断，不能原样沿用。

收到pending后每15至30秒调用`geo_resume_task(run_dir)`，持续查询同一个任务，不重新调用原生成工具，不重新POST付费请求。工具返回pending就继续查询，返回completed后才进入下一业务步骤；完成结果立即写入本地缓存。终审可能依次处理两份PDF，后续查询仍使用同一run目录。

后台调用使用`store:false`，服务端仍会为后台执行临时保留任务数据约10分钟，所以需要持续及时查询。已保存任务ID可以在短时连接中断后继续查询，不代表支持跨天恢复。若POST失败且没有拿到任务ID，结果状态为unknown；若查询返回404或任务过期，明确停止并保留本地记录，不冒称能够恢复，也不自动新建付费任务。需要新请求时由用户明确决定。

## WorkBuddy 执行顺序

安装后先调用 `geo_status` 检查本地配置，再按以下顺序执行：

1. 沿用原流程整理客户 `project.json`，将三列表通过原 `normalize` 命令导入内部判读 XLSX。原件保留，收到一个平台就继续，不要求补采其他平台或重新记录模式、联网、时间。
2. `geo_analyze_customer(workspace, project_file, answers_file)`：传入项目内的客户目录、项目JSON和内部判读XLSX，交由GPT读取本次真实材料，返回本次`run_dir`。pending时通过`geo_resume_task(run_dir)`持续查询，completed后才检索媒体；后续操作统一使用该运行目录。
3. `geo_search_media(run_dir, query, kind='all', region='')`：按 GPT 给出的业务方向检索实际资源；可按多组关键词分别检索，记录返回的候选文件路径。推荐池保持广泛，不按执行预算截断推荐数量。
4. `geo_create_plan(run_dir, candidate_files, revision_instructions='')`：使用实际候选文件，由 GPT 形成具体选媒、内容、阶段和两档方案。本地脚本校验资源身份及量价。每档实际媒体费最低12,000元，依实际类别单价与刊次汇总，不虚加补差；执行文章写作不含在媒体费中，默认单列原价200元／篇、打包100元／独立稿及含写作总价。客户供稿不收写作费。`budget_target`只记意向预算，客户明确不能超过时才设`budget_limit`。
5. `geo_write_reports(run_dir, revision_instructions='')`：由 GPT 填写客户正文，使用原固定模板生成诊断 PDF、执行方案 PDF 和双 sheet 推荐媒体表。
6. `geo_review_deliverables(run_dir)`：独立调用 GPT，连同原材料、原模板及实际 PDF 页图审核事实、分析、媒体、费用、客户措辞和版式。根据问题回到方案或成稿步骤修改，再终审；最多两轮修正，仍不通过时保留内部草稿及具体问题，不标记已通过。
7. `geo_publish(run_dir, output_dir)`：仅在终审`status="completed"`且`passed=true`、成品哈希未改变时，将三件客户成品复制到项目内的新交付目录。审查已完成但passed=false时先修改复审。审核记录与制作材料保留内部，不交给客户。

`revision_instructions` 只传本轮需要修正的事项；具体分析、方案和成稿通过 GPT 工具完成。WorkBuddy 调度这些工具并说明实际状态，不自行绕过终审发布未通过的文件。

候选媒体在本地保留全量匹配及六档原价，发送模型时整理所需元数据；不因预览只显示15项就截断推荐池，也不要求同事按旧500项或800KB门槛手工缩小候选。按业务适配筛选，推荐池不局限于执行预算。

## 既有任务从方案继续

以下指令用于已完成分析、方案请求失败的当前任务，不重新制作客户报告或重跑已完成分析：

> 更新当前项目的技能到0.10.2并重连本地MCP，确认工具中有geo_resume_task。保留已有分析完成的目标run目录的project、raw-evidence、analysis、model-analysis、judged，以及15份原始candidates和candidates-curated.json。复用该run_dir，从geo_create_plan继续，candidate_files只传该目录已有的candidates-curated.json；不重新调用geo_analyze_customer，不重新采集或检索媒体。不要沿用旧mcp_pipeline.py按结果txt存在就跳过的判断；isError:false、结果文件存在或status:pending均不代表完成。收到pending后每15至30秒调用geo_resume_task查询同一任务，只有status:completed且对应业务产物齐备才成稿和终审；终审passed:true才交付。没有任务ID或任务过期时报告具体状态并停止，不自动重发付费请求。保持gpt-6.1-sol／max和原媒体报价。

旧版失败请求若没有保存服务端任务ID，不能凭run目录找回那次服务端结果；上述create_plan是用户授权后的新方案请求。其后的0.10.2后台任务使用落盘ID续查。

官方接入依据：[WorkBuddy MCP 指南](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)、[远程及本地传输与连接器凭证说明](https://open.workbuddy.cn/en/docs/connector)。

模型与请求依据：[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)、[结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)。客户端固定官方端点，失败不会自动重试付费请求；真实请求上限仍做明确校验，不静默漏答、漏图或裁掉候选。

## 本地状态与验收

区分依赖安装、MCP 握手、真实 API 调用、WorkBuddy 界面运行和成品终审。密钥已保存只表示有本机凭证，不表示账号已获得模型权限或已完成真实调用。所有运行记录留在客户 `.work`，客户只收到原定三件成品。

用户已报告旧版真实分析成功、方案生成失败；0.10.2修复本身没有重新请求真实API。离线响应、协议检查与用户再次真实续跑的结果分别记录，不把本次代码检查写成端到端已解决。
