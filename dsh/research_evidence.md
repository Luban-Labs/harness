# CC/DSH 本机 hook 事实核对（只读调查）

核对时点：2026-10-25 19:50 Australia/Sydney。只读文件与已安装程序；没有启动或重启 CC/DSH，没有执行 hook。以下源码结论只绑定当前安装版本，未把源码推断写成真实会话已触发。

## 证据来源

- CC 可执行文件：`/Users/sangba/.local/share/claude/versions/2.1.310`，Mach-O arm64，内嵌 `// Version: 2.1.310` JS；SHA-256 `ffb64331bc0ee1b69efb7c2c428bd3ab516bc31b75bf60886b356c97c1c25ffd`。下文数字是该文件的**字节偏移**，供 `mmap.find` 复查。符号是压缩后的本机名，跨版本不稳定。
- DSH Claude 桥接：`/Users/sangba/.dsh/profiles/desktop/node_modules/@deepseek-ai/dsh-hooks-claude-code/lib/index.js`；SHA-256 `c4f3f5d92c82e790593d977d95eef0afa4ffad07bb9b9d1609ae613fe6a76283`。
- 当前配置：`~/.claude/settings.json`、`~/.claude/settings.local.json`、`~/.claude/plugins/installed_plugins.json`，以及下列项目各自的 `.claude/settings*.json`。只读取 `hooks`、`enabledPlugins` 和安装记录的 `scope/projectPath/installPath/version`，未回显其他键或命令全文。

## 三种独立的目录/信任值

| 用途 | CC 2.1.310 源码路径 | 普通本地启动结论 |
| --- | --- | --- |
| 项目 `settings.json` | `H()` (217165838) 传 `cwd:ci(), projectConfigDir:no()??undefined`；`FEn` (216695323) 的 `projectSettings` 为 `projectConfigDir??cwd`；`mK/gT` (216698001) 接 `.claude/settings.json` | 无显式 projectConfigRoot 时读**启动 cwd** 下的文件；不是自动按 git root 读。 |
| 项目 `settings.local.json` | 同一 `FEn` 的 `localSettings` 为 `S1(cwd,canonicalGitRoot)`；`S1/s9r/_Ei` (216695569) 核验主根、当前 uid 与 `.git`、`.claude` 所有者；`vpe` (216698425) 还可能合并 cwd 中的 legacy local 文件 | 安全核验通过时可读 canonical git root 的 local 文件；失败时留在 cwd。还需考虑 legacy cwd 文件。 |
| hook `CLAUDE_PROJECT_DIR` | session 初始化 `Er(e=bis())` (215670...) 存 `{originalCwd:e,projectRoot:e,cwd:e}`；`ao()` (215675058) 读 session `projectRoot`；执行 command hook 的 `Vn=fn??b.projectRoot` (228789...)，`fn=no()` 即 `launchOptions.projectConfigRoot()` (215686833)；环境 `CLAUDE_PROJECT_DIR:Yt(Vn)` (228792543) | 通常是会话**启动目录**；显式 projectConfigRoot 优先。进入 worktree 或某些目录切换会调用 `jxe(pe())` (例如 255222605、257875153) 改 session projectRoot。它不等于信任键，也未必等于执行时 `cwd`。 |
| 持久信任键 | `WP` (218774...) 先查 `aKe()`；`aKe` (218806714) 用 `wM(cwd)`；`wM -> oi -> hr(.git root) -> Et` (217009431–217011424)；`Et/Qn` 核实 worktree `.git` 的 `gitdir/commondir/gitdir` 回链，归到主工作树；`iKe` (218771100) 严格 `projects[e].hasTrustDialogAccepted===true` | 优先候选是 canonical git root，可靠 worktree 归到主树。`WP` 接着走 `Q_(config,cwd)`：`Z_` 从 cwd 逐级找接受信任的键，到当前 worktree git root 为止；非 git 则可能上溯到文件系统根。因此**不是只查主树一个键**。 |

注意：上述 session `projectRoot` 是 CC 生命周期值。DSH 日志只给初始 `header.cwd`、后续桥接给当前工作目录，不能无证据复原 CC 的显式 projectConfigRoot、worktree 切换或当前 permission mode。当前这几个本地目录在 `~/.claude.json` 的相关信任键状态：`harness` 主树键存在但 `hasTrustDialogAccepted` 非 true；`harness-wt-dsh` 键缺；`ticket-seller-tools`、`dashboard`、`krapi` 主树键为 true。未读取或记录该文件其他字段。

## matcher、hook 输出与插件

- CC `Mst` (228804894) 对 Pre/PostToolUse/Failure/PermissionRequest/Denied 取 `tool_name`，SessionStart 取 `source`，SubagentStart/Stop 取 `agent_type`；Stop 无 matcher subject。`Hte/aMn` (228804523、228807386)：无 matcher 或 `*` 全选；简单字符集模式按 `|` 拆字面候选，工具类也可含逗号/空格，大小写敏感；还可匹配工具别名/家族；其他模式走 regex 测试。故 CC 配置 `Edit|Write|MultiEdit` 不会仅因 DSH 的 `edit/write` 而命中。DSH 桥接自身 `selectHookGroups(..., exec.name, 'claude-code')` (index.js:170, 253)，需另按其协议核对，不能把 CC 的匹配规则直接当桥接规则。
- CC 的 PreToolUse 输出在 `hookSpecificOutput.permissionDecision` (228781241 起) 接受 `allow/deny/ask/defer`，也读取 `additionalContext/updatedInput`；顶层 `decision` 仅为旧 `approve/block` (228739735)。CC 命令退出 2 阻断，非零且非 2 是普通错误（228883591、228883928；具体事件映射还需按事件复核）。DSH 桥接 `index.js:253–266` 把合并后的 `deny/ask` 映成工具拒绝/询问；它当前 payload 未含 `permission_mode`。外部 `public-push-guard.sh` 依赖该字段与 `CLAUDE_PROJECT_DIR`，不可猜一个 CC permission mode 填入。
- CC 插件开关 `A8` (223256799) 按 managed → user → project → local → flag 的 `enabledPlugins` 层顺次覆盖，true 加入、false 删除。安装记录筛选 `EO/One` (229666...)：`user/managed` 接受；`project/local` 要 `projectPath===originalCwd` 或双方 `wM()` canonical git root 相等；macOS 只用此筛选。`D5n` (229824379) 多条候选时取首个安全且现存的 `installPath`，否则首个候选。插件 loader 在 229868... 自动读 `hooks/hooks.json`，manifest `hooks` 另可为字符串、列表或对象；重复路径去重；`h5n` (229873672) 对同事件的 hook 组按原顺序拼接。当前项目没有额外 enabledPlugins 覆盖。
- CC 运行时 hook 收集 `B2/c` (223251444) 从多种注册源拼成事件数组，`BL` (228826...) 再接 session/function hooks；项目 settings、插件文件和临时注册钩子不能用对象键覆盖来模拟。用户指定的调度范围仅含用户、已信任项目和启用插件的 command hooks；其它 CC 注册源不在本次枚举中。
- DSH 桥接只解析 `SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop/SubagentStart/SubagentStop`，只运行 command hooks（index.js:7–100）；启动时读一次单一 `configPath` (index.js:139–151)，不自动合并项目 `.claude/settings.json`。每个工具事件用 `exec.name` 作 matcher subject，stdin `tool_name=exec.name, tool_input=exec.arguments, tool_use_id=exec.callId` (index.js:253–284, 376–390)；`transcript_path:""`，Stop `stop_hook_active:false` (index.js:357–398)。工具名实际小写：`bash/read/write/edit/glob/grep`，相应参数为 `command`；`file_path,offset?,limit?`；`file_path,content`；`file_path,old_string,new_string,replace_all?`；`pattern,path?`；`pattern,path?,include?`（已装 DSH app 的 `dsh-tool-bash-persistent`, `dsh-tool-fs`, `dsh-tool-fs-search` 源码）。
- 上一条的 `bash` 参数简写仅列公共 `command` 字段；**当前 desktop/base 挂载的是 `dsh-tool-bash`，不是 `dsh-tool-bash-persistent`**。当前 `bash` 完整基础输入是 `{description:必填, command:必填, timeoutMs?, workdir?, run_in_background?}`，权限字段随部署配置；依据已装 app 的 `dsh-base/cordis.patch.yml:281–283` 与 `dsh-tool-bash/lib/index.js:493–525`。
- CC 同事件并发：`LD` (228876889) 对匹配到的 `xe` 用 `xe.map(async handler)` 启动各 handler，(228884444) 用 `Promise.all` 汇合；普通 settings/plugin 的相同 command 仍按条目运行，没有命令级去重。Stop 输入在 (228756551) 一次构造 `stop_hook_active:s`，该次全部 handler 收同一个 payload；block 后只在后续 Stop 迭代的 guard (234453859) 把 flag 变 true。DSH 桥接原实现的双层 `for` 是串行 (index.js:172–213)，两者存在执行顺序差异。
- CC **command hook** 占位符分两路：shell form（无 `args`）在 AU (228791707–228794...) 用原 `e.command` 作为 shell 字符串，仅把 `CLAUDE_PLUGIN_ROOT`、`CLAUDE_PROJECT_DIR` 放入进程 env，**不**预先替换命令文本；POSIX shell 单引号内的 `${CLAUDE_PLUGIN_ROOT}` 因此保留字面，双引号或裸写由 shell 展开。exec form（有 `args`）对 command 与每个 args 元素先 `replaceAll("${CLAUDE_PROJECT_DIR}",projectDir)`，有插件根时再 `replaceAll("${CLAUDE_PLUGIN_ROOT}",pluginRoot)`，以及插件数据目录；随后无 shell 直接 spawn。此处的替换与其它插件配置/skill/MCP 使用的 `Tde` 函数不同，不能把 `Tde` 的做法套到 shell hook。

## 当前 DSH 工具名与输入字段

依据已装 app 的 `dsh-base/cordis.patch.yml`、desktop profile patch 与各 `dsh-tool-*/lib`；preset 可能过滤工具，动态 MCP/扩展可增工具。语义近似只帮助定位原 CC hook；不能把不等价参数改名后假装原 hook 已执行。

| DSH 实际注册名 | 关键 `tool_input` 字段 | CC 对应判断 |
| --- | --- | --- |
| `bash` | `description`, `command` 必填；`timeoutMs?`, `workdir?`, `run_in_background?` | 对应 CC `Bash`。CC 本机 Bash 输入 `timeout` 是毫秒（binary 230123567），DSH `timeoutMs` 可原值映射；与 hook 配置的秒单位 timeout 分开。 |
| `read`, `write`, `edit` | `file_path,offset?,limit?`；`file_path,content`；`file_path,old_string,new_string,replace_all?` | 对应 CC `Read/Write/Edit`；本机外部文件 hook 所需 `file_path/content/new_string` 可直读。 |
| `glob`, `grep` | `pattern,path?`；`pattern,path?,include?` | 对应 CC `Glob/Grep`。 |
| `subagent`, `subagent_fork` | `cwd?,description,prompt,agent_preset?`；spawn 可有 `provider?,model?,reasoning_effort?` | 对应 CC `Agent` 的委派语义；只能映已证等义字段，原 CC guard 要的 `subagent_type` 不在 DSH 输入中。 |
| `workflow` | `script,meta`，`meta.name/description` 必填 | 对应 CC `Workflow`；`script` 可用，DSH 没有 `scriptPath`。脚本约束不能未经实测按 CC 判。 |
| `todo_write` | `todos:[{content,status}]` | 对应 CC `TodoWrite` 的列表语义；原始 `todos` 保留。 |
| `web_search`, `web_fetch` | `queries:[string]`；`url` | 对应 CC `WebSearch/WebFetch`；只在单个 `queries` 字符串时可另给 `query` 别名，保留原始 `queries`。 |
| `working_directory` | `cd?`（省略为查询） | 无已核实的同名 CC tool，保留 DSH 名。 |
| `send_message`, `interrupt_agent`, `list_agents`, `list_subagent_models` | `{agent_id,message}`；`{agent_id}`；`{scope?}`；`{provider?,model?}` | DSH 子代理控制面；无可无损映射的 CC `Agent` tool input。 |
| `job_output`, `job_list`, `job_kill`; `get_goal`, `create_goal`, `update_goal`; `skill` | job id / goal id / skill name 等各自 schema | 保留 DSH 名；不当成 CC `Task`。 |
| `schedule_create`, `schedule_list`, `schedule_delete`, `schedule_update` | create 的 `prompt,title,after_seconds?/selector?`；list 无参数；delete/update 用 id | 已读 `unrestricted` preset 注册；无已核实的 CC 等价工具，保留 DSH 名。 |
| `ask_user_question`, `present`, `ralph` | `{questions:[...]}`；`{files:[{path,description?}]}`；`{objective,maxRounds?}` | 已读 preset 注册；无损 CC tool input 映射未核，保留 DSH 名。 |

当前 base/preset 中未见注册名 `Agent`、`Workflow`、`TodoWrite`、`WebSearch`、`WebFetch`、`delegate`、`multitask` 或 `task`。`subagent_codex`、`subagent_claude_code` 在已读 preset 里为 disabled；此句仅说明安装配置，未声称所有当前会话工具表相同。

## DSH v4 日志首行白名单核查

使用 Python 3.14 标准库 `compression.zstd` 只读现有 12 份 `session.v4.jsonl.zstd` 的第一行，程序仅输出 `type/version/id` 格式、`parentSession` 键是否存在及是否 null、`cwd` 是否绝对路径的聚合计数；没有输出或保留消息/命令。6 份顶层均为 `type=session, version=4, id=session-<uuid>, cwd=绝对路径`，并且 **`parentSession` 键缺失**；6 份子代理均为 `type=session, version=4, id=<uuid>, cwd=绝对路径`，`parentSession` 存在且非 null。因此顶层 read_header 不能要求该键存在且为 null；缺键应与 `session-<uuid>` 格式、版本及目录一致性共同判顶层，不能单凭缺键放行。

## 当前 hooks 对齐矩阵（仅安全名称）

截至核对时 `~/.claude/settings.json` 为 **27 个** command handler；`settings.local.json` 无 hooks/插件覆盖。空 matcher 与未设 matcher分别照实标出。`inline` 只表示命令里没有可安全提取的脚本 basename，未记录命令正文。

| 来源 | 事件 | matcher | handler basename / 数量 | DSH 桥接支持事件 |
| --- | --- | --- | --- | --- |
| CC 用户 | PostToolUseFailure | 空 | codeisland-hook.sh | 否 |
| CC 用户 | Notification | 空 | codeisland-hook.sh | 否 |
| CC 用户 | PreCompact | 空 | codeisland-hook.sh | 否 |
| CC 用户 | StopFailure | 空 | codeisland-hook.sh | 否 |
| CC 用户 | SubagentStart | 空 | codeisland-hook.sh | 是 |
| CC 用户 | PostToolUse | `Edit|Write|MultiEdit` | inline, file-size-budget.sh, institution-refcheck.py, doc-filler-guard.sh | 是，大小写不匹配 DSH 工具名 |
| CC 用户 | PostToolUse | 空 | codeisland-hook.sh | 是 |
| CC 用户 | Stop | `*`；空 | inline；codeisland-hook.sh | 是 |
| CC 用户 | SessionEnd | 空 | inline, pm-mode-state.py, codeisland-hook.sh | 否 |
| CC 用户 | SubagentStop | 空 | codeisland-hook.sh | 是 |
| CC 用户 | PermissionRequest | 空 | codeisland-hook.sh | 否 |
| CC 用户 | UserPromptSubmit | 空 | pm-mode-state.py, codeisland-hook.sh | 是 |
| CC 用户 | SessionStart | 空 | handoff-check.sh, hookspath-check.sh, codex-plugin-patch-check.sh, codeisland-hook.sh | 是 |
| CC 用户 | PreToolUse | `Agent|Workflow`；`Workflow`；`Edit|Write|MultiEdit`；空 | subagent-model-guard.sh, workflow-agent-cap.sh, doc-filler-guard.sh, codeisland-hook.sh | 是，专用 matcher 名不匹配 DSH 工具名 |
| 已启用 codex@openai-codex | SessionStart, SessionEnd, Stop | 未设 | session-lifecycle-hook.mjs ×2, stop-review-gate-hook.mjs | SessionEnd 否 |
| 已启用 prompt-opt@prompt-opt-mp | UserPromptSubmit | 未设 | hook.sh | 是 |
| 已启用 codex-watch@luban-labs-codex-watch、native-hud@luban-labs-native-hud | hooks.json 有 modules，无 command event | — | — | 桥接不运行 modules |
| 已启用 pp@luban-labs、pyright-lsp@claude-plugins-official | 无标准 hooks/hooks.json | — | — | — |
| harness 主树、当前 worktree、ticket-seller-tools、dashboard | SessionStart, Stop | 未设 | session_start.py, stop_guard.py（每项目各两项） | 是 |
| krapi | 无项目 settings(.local).json | — | — | — |

### 27 条用户 command hook 的逐条适配核对

以下只静态读取各脚本和相关输入/输出分支，没有执行用户 hook。编号按当前 settings 的事件/组/handler 顺序；“可传入”只表示桥接能派发该事件，**不代表脚本效果已到模型或等价 CC**。CodeIsland 的 shell 层会转给本机可执行二进制，二进制行为未逆向，故只确认入口，不能宣称输出契约兼容。

下表的“名称不匹配”指**原 DSH 桥接**。owner 已要求新调度器对有明确对应的工具提供 CC `tool_name` 别名（例如 `subagent`→`Agent`、`workflow`→`Workflow`）；该别名只解决 matcher，不能凭空生成 CC 的 `subagent_type`、有效 transcript 或 permission mode。

| # | 事件 / 组:handler | 脚本 | 静态适配结论 |
| --- | --- | --- | --- |
| 1 | PostToolUseFailure 0:0 | codeisland-hook.sh | 桥接无此事件；入口不触发。 |
| 2 | Notification 0:0 | codeisland-hook.sh | 桥接无此事件；入口不触发。 |
| 3 | PreCompact 0:0 | codeisland-hook.sh | 桥接无此事件；入口不触发。 |
| 4 | StopFailure 0:0 | codeisland-hook.sh | 桥接无此事件；入口不触发。 |
| 5 | SubagentStart 0:0 | codeisland-hook.sh | 事件可传入，但 DSH 固定 `agent_type=general-purpose`；二进制输出/副作用未核。 |
| 6 | PostToolUse 0:0 | inline | `Edit|Write|MultiEdit` 与 DSH 小写工具名不匹配；只靠 `session_id/tool_input` 写 `.claude/state/edited` 标记，非 JSON stdout 不能作 DSH additionalContext。 |
| 7 | PostToolUse 1:0 | file-size-budget.sh | 同上需匹配名适配；`tool_input.file_path` 在 DSH edit/write 有，stderr+exit 2 可回馈；会话级 marker 的 SessionEnd 清理在桥接缺失。 |
| 8 | PostToolUse 1:1 | institution-refcheck.py | 同上需匹配名适配；读 `tool_input.file_path`，超限 stderr+exit 2；检测对象是固定本机文档目录。 |
| 9 | PostToolUse 2:0 | doc-filler-guard.sh | 同上需匹配名适配；读 `hook_event_name` 与 `tool_input.file_path`，stderr+exit 2 可回馈。 |
| 10 | PostToolUse 3:0 | codeisland-hook.sh | 事件可传入；二进制如何解释 DSH 小写 tool_name/输出未核。 |
| 11 | Stop 0:0 | inline | 读 `session_id` 与上述标记；输出为非 JSON 文本，无桥接 Stop `decision:block`，提醒不能照 CC 显示。 |
| 12 | Stop 1:0 | codeisland-hook.sh | 事件可传入；DSH `stop_hook_active:false` 且无 CC transcript，二进制兼容性未核。 |
| 13 | SessionEnd 0:0 | inline | 桥接无此事件；`.claude/state/edited` 标记清理不触发。 |
| 14 | SessionEnd 1:0 | pm-mode-state.py | 桥接无此事件；PM 状态 marker 清理不触发。 |
| 15 | SessionEnd 2:0 | codeisland-hook.sh | 桥接无此事件；入口不触发。 |
| 16 | SubagentStop 0:0 | codeisland-hook.sh | 事件可传入，但 DSH 固定 `agent_type=general-purpose`，`stop_hook_active:false`；二进制兼容性未核。 |
| 17 | PermissionRequest 0:0 | codeisland-hook.sh | 桥接无此事件；CC 询问流程的该入口不触发。 |
| 18 | UserPromptSubmit 0:0 | pm-mode-state.py | `prompt/session_id` 可读，也会写 PM marker；该脚本提示是普通 stdout，桥接只接 JSON `additionalContext`，提示不能照 CC 注入。 |
| 19 | UserPromptSubmit 1:0 | codeisland-hook.sh | 事件可传入；二进制如何解释/回传尚未核。 |
| 20 | SessionStart 0:0 | handoff-check.sh | 读 `cwd`，JSON `hookSpecificOutput.additionalContext` 可被桥接读取；会清外部旧 marker，具体内容依本机状态；DSH 只有 startup/resume source。 |
| 21 | SessionStart 1:0 | hookspath-check.sh | 读 stdin `cwd` 后检查 git hooksPath；只打印普通 stdout，桥接 SessionStart 忽略，告警不会注入。 |
| 22 | SessionStart 2:0 | codex-plugin-patch-check.sh | 只读本机 Codex 插件文件/配置；普通 stdout 告警被桥接 SessionStart 忽略。 |
| 23 | SessionStart 3:0 | codeisland-hook.sh | 事件可传入；二进制兼容性未核。 |
| 24 | PreToolUse 0:0 | subagent-model-guard.sh | 仅认 `Agent/Workflow`；DSH 为 `subagent/subagent_fork/workflow` 且 Agent 字段无 `subagent_type`；`transcript_path:""` 使当前主模型取证退到 settings，不能宣称保护生效。 |
| 25 | PreToolUse 1:0 | workflow-agent-cap.sh | 仅认 `Workflow`；DSH 为 `workflow`。即使改名，原脚本强制 CC 的 `agentCapped`/`agent(` 写法，须核对 DSH workflow 脚本契约，不能直接算通过。 |
| 26 | PreToolUse 2:0 | doc-filler-guard.sh | 需将 matcher 匹配 DSH `edit/write`；这两工具有 `file_path` 与 `new_string/content`，stderr+exit 2 可阻断；DSH 无 `MultiEdit` 注册名。 |
| 27 | PreToolUse 3:0 | codeisland-hook.sh | 事件可传入；二进制如何解释 DSH 小写 tool_name/输出未核。 |

启用插件另核：`codex@openai-codex` 的 SessionStart `session-lifecycle-hook.mjs` 只在 `CLAUDE_ENV_FILE` 存在时把 session/transcript/plugin data 写给后续 shell，DSH 桥接不提供它；SessionEnd 同脚本因事件缺失而不能清 broker/jobs；Stop `stop-review-gate-hook.mjs` 读取 `last_assistant_message`，桥接没有该字段，开启 gate 时 review prompt 丢失本轮回答。`prompt-opt` UserPromptSubmit `hook.sh` 的 JSON `additionalContext` 可读；`prompt-level` 切档会写其状态文件，须同时核对插件根替换与状态目录，不能只看输出格式。项目 harness SessionStart 依 `cwd/session_id`，Stop 另依记录与 loop flag；桥接原始 `transcript_path:""`、`stop_hook_active:false` 不满足原 Stop 取证与一次提醒契约。`public-push-guard.sh` 当前**未**列在这 27 条中；若后续重新登记，它要求 CC `permission_mode` 与 `CLAUDE_PROJECT_DIR`，桥接原 payload 没有前者。

`ticket-seller-tools` 的四份 `.claude/hooks/*.py` 与 harness 主树对应文件字节相同；dashboard 三份 `session_start.py/stop_guard.py/stop_evidence.py` 与主树不同且缺 `judgment_twins.py`；当前 worktree 四份脚本有进行中的修改。升级不能从单个文件名推断版本一致，需对照四脚本与项目规则/模板清单；当前 worktree 变更由主线程另出最终 diff 快照。

现有 harness 安装与升级契约（`docs/rules/harness.md`「安装与升级」）列出复制 `.claude/hooks/session_start.py`、`stop_guard.py`、`stop_evidence.py`、`judgment_twins.py` 和 `docs/rules/harness.md`；装了 interview-me 的项目再复制 `.agents/skills/interview-me/SKILL.md`、`templates/spec.md`、`references/to-spec.md`、`references/to-tickets.md`。项目改过的文件先 diff 再合；`docs/rules/core-judgments.md` 有则不覆盖；项目 `AGENTS.md` 固定路由需对照 `templates/AGENTS.md`。这是升级候选清单，不是本次已执行升级。

## 影响使用方与未验证项

- `CLAUDE_PROJECT_DIR` 的项目内使用方：`init.py` 安装命令、`migrate_trellis.py` 迁移命令、`docs/rules/harness.md` 安装段、`docs/decisions.md`；被安装的项目 settings 中 SessionStart/Stop 也引用它。Codex 相对路径配置在 `init.py`、迁移逻辑、测试与规则文档另有使用方。
- 认领/接手前 8 位与看板：`docs/rules/harness.md` 的「开工与认领」、`.claude/hooks/session_start.py` 的 `session_matches/claim_state` 与「接手自」输出、`stop_guard.py` 导入、`tests/test_takeover_board.py` / `test_session_start.py` / `test_stop_proactive.py`。DSH 顶层 `session-<uuid>` 的前 8 位都为 `session-`，不能沿用原前缀作为身份判断或显示。
- DSH 桥接的 `transcript_path:""` 和 `stop_hook_active:false` 不能满足现有 Stop 取证与循环保护；这些是源码事实，不代表已看到一次完整 DSH 动态转发。CC 的 `projectRoot` 在显式 projectConfigRoot、worktree 切换、非本地/远程运行时的实际值仍需针对目标会话验证；本报告不将其从当前工作目录或 git root 猜出。
