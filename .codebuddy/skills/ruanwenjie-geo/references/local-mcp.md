# 本地 GPT MCP 安装与续跑（0.11.0）

本地stdio服务由WorkBuddy启动，GPT固定使用`gpt-6.1-sol`、推理`max`。分析、分类方案、成稿和两份PDF逐页终审使用OpenAI API并产生费用；不自动监测、操作平台账号、下单或发布媒体。本版不检索或推荐具体媒体，不发送媒体候选，不生成推荐媒体表。

## Windows 安装

将完整技能目录放到长期保留的位置，在PowerShell执行，替换路径：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "技能目录\scripts\setup_local_mcp.ps1" -PythonExe "Python安装目录\python.exe" -WorkBuddyProject "WorkBuddy项目目录" -SetApiKey
```

首次设置`-SetApiKey`在本机隐藏输入，密钥经当前用户Windows DPAPI加密保存；已设置时省略该参数。密钥不发送到聊天、不写入客户文件或仓库。脚本安装独立依赖并合并项目`.workbuddy/mcp.json`，保留其他服务器和修改前备份。`GEO_WORKSPACE`限定客户路径；Python须为3.10以上。路径移动后重新安装更新配置。

重连后调用geo_status，核对`gpt-6.1-sol`、`max`、`1050000`、`background`及`geo_resume_task`。状态仅证明本地配置，不代表账号权限、实际请求或WorkBuddy界面已验收。官方接入依据：[WorkBuddy MCP指南](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)、[Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create)。

## 后台任务与停止规则

每个付费生成任务先保存任务描述和response_id，`pending`仅表示已提交；每15至30秒调用`geo_resume_task(run_dir)`查询同一任务。`isError:false`、结果文件存在或pending均不表示业务完成；仅`status=completed`并且对应业务产物齐备才进入下一步。终审可能顺序提交两份PDF的独立请求；检查任务内两个检查点，同一检查点的ID不能变化。

后台`store:false`的服务端临时结果保留时间有限，持续查询并及时落盘，不承诺跨天恢复。无ID、状态未知、过期或失败时停止，不自动重发付费请求；旧请求、检查点和输入保留。终审只有`passed=true`并且审后哈希未改变时才能发布；失败按意见修改并复审，最多两轮修正。

## 执行顺序

1. 整理客户project.json并将原答和截图导入内部判读XLSX，原件保留。已有`analysis.json`、`model-analysis.json`及`judged.xlsx`的有效run直接复用，不重新分析。
2. `geo_analyze_customer(workspace, project_file, answers_file)`：对新任务调用，pending时持续续查。仅凭实际收到的平台回答分析。
3. `geo_create_plan(run_dir, revision_instructions='')`：不传媒体候选，生成内容、四阶段、三类传播用途与同范围两档报价。`budget_target`为意向，只有明确硬上限才设`budget_limit`。两档各计划媒体费至少12,000元，正文写作默认单列原价200元/篇、打包100元/独立稿；客户供稿不收写作费。具体媒体、刊发条件和两档资源权益差异待确认，不冒称已选定。
4. `geo_write_reports(run_dir, revision_instructions='')`：在内部生成8页诊断及9页执行PDF。日期未确认时仅可使用明确标记待确认的示例日期；正文不得列具体媒体名称。
5. `geo_review_deliverables(run_dir)`：独立读取原证据、两份原模板与实际17页画面，核事实、版式、分类刊次、两档费用、分工与待确认边界。
6. `geo_publish(run_dir, output_dir)`：仅终审通过且哈希未变时复制两份PDF到项目内新交付目录，拒绝覆盖。客户原件、旧推荐表与旧成品不变。

## 既有失败方案的明确授权重试

0.10.2的失败方案不会因升级自动重发。先核查当前任务及其`requests/`检查点：必须是本run的单个方案请求，状态明确为`failed`且保留有效response_id。若用户**明确授权一次新的付费方案请求**，可调用：

```text
geo_create_plan(run_dir, revision_instructions="按新分类方案生成，不指定具体媒体", retry_failed_response_id="原失败请求的完整response_id")
```

工具在登记锁下核对ID和失败状态，旧任务和检查点原样保留；新任务有独立ID。ID不匹配、等待中、过期、状态未知、非方案或未给授权ID时拒绝新任务。pending仍只续查新任务；未获用户明确授权不填写该参数、不发新请求。原分析和采集表不重跑、不改写，不能手工改状态绕过保护。旧版尚在运行的请求先按原ID处理；旧版已生成具体媒体的计划、草稿保留但不用于新版发布。

## 版本与验证范围

0.10.2曾在真实API任务中经明确付费修正和两轮终审生成三件旧版成品，另一个任务因一次发送海量媒体候选触发`context_length_exceeded`。0.11.0改为不发送候选、只交两PDF；本版的自动化和真实API验收结果应分别记录，不将旧版真实运行冒充新版已验证。WorkBuddy界面验收独立进行，客户资料和响应不得上传公共仓库。
