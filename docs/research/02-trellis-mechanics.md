# Trellis 执行机制与「重」的来源

调研对象:`/private/tmp/claude-501/-Users-sangba-Downloads-02-----------harness/c38a95e8-724a-458f-a564-59ac3a323ca8/scratchpad/trellis`(`@mindfoldhq/trellis` v0.6.16,见 `packages/cli/package.json`)
只读调研,所有结论均带 `path:line` 出处;本次未读到的一律标「未核实」。
下文所有相对路径均相对该仓库根。

---

## 0. 一页结论

**周期链条是真的闭环的**:用户命令/技能 → python 脚本改 `task.json` 一个 `status` 字段 → 三个 hook 在三个时机把不同粒度的文本注入上下文。整条链只有一个状态变量(`task.json.status`:`planning` → `in_progress` → `completed`),三次赋值分散在三个函数里(`common/task_store.py:499`、`task.py:112-114`、`common/task_store.py:1317`)。

**「重」不在依赖,在两处**:

1. **多平台适配**——22 个平台(`packages/cli/src/types/ai-tools.ts:11-32`),仓库里 7 个平台目录共 398 个文件,`.trellis/.template-hashes.json` 记录 228 个受管模板文件,CLI 源码 26,841 行(119 个 .ts)。单平台版这一层直接归零。
2. **健壮性与容错**——14,163 行 Python(31 个文件)里,真正做周期决策的不到 10%,其余是 Windows 路径/编码、JSON 损坏容错、幂等续跑、路径逃逸防护、21 个平台的 session 环境变量表。

**Python 依赖为零**:`.trellis/scripts` + `.claude/hooks` 的全部 import 都是标准库(`__future__ pathlib sys json re os typing datetime subprocess dataclasses argparse warnings time io hashlib threading tempfile shutil shlex queue collections`),连 YAML 都是自己手写的简易解析器(`common/trellis_config.py:113-226`)。运行时要求:python3 ≥ 3.9(`packages/cli/src/commands/init.ts:70-71`)+ node ≥ 18.17(仅安装/升级时用,`packages/cli/package.json` engines)。

**最有说服力的一条实测**:Trellis 自己的仓库里 242 个任务(含归档),`implement.jsonl` 只有 107 个真正填了内容,52 个存在但为空,83 个根本没有;而 `task.py start` 却对这个文件**硬门禁**(`task.py:194-215`)。设计上的必经关卡,作者自己有一半以上的时候绕过去了。这是轻量版最该砍的东西。

---

## 1. 周期链条:谁触发、谁执行、落到哪个文件、哪个 hook 读它

### 1.1 全景图(Claude Code 平台)

```
                    ┌──────────────────────── 状态文件(真相源) ────────────────────────┐
                    │ .trellis/tasks/<MM-DD-slug>/task.json      ← status 唯一权威        │
                    │ .trellis/tasks/<MM-DD-slug>/prd.md|design.md|implement.md           │
                    │ .trellis/tasks/<MM-DD-slug>/implement.jsonl|check.jsonl|research/   │
                    │ .trellis/.runtime/sessions/<context_key>.json ← 每会话的"当前任务"指针│
                    │ .trellis/workflow.md                        ← 所有提示词文本的源     │
                    │ .trellis/workspace/<dev>/journal-N.md       ← 跨会话记忆             │
                    └────────────────────────────────────────────────────────────────────┘
                         ▲ 写                           ▲ 读                    ▲ 读
                         │                              │                       │
     ┌───────────────────┴──────────┐      ┌────────────┴──────────┐  ┌─────────┴─────────┐
     │ .trellis/scripts/task.py     │      │ .claude/hooks/        │  │ get_context.py    │
     │ .trellis/scripts/add_session │      │  session-start.py     │  │ (--mode 四档)      │
     └──────────────▲───────────────┘      │  inject-workflow-state│  └─────────▲─────────┘
                    │ 调用                  │  inject-subagent-ctx  │            │ 调用
     ┌──────────────┴───────────────┐      └────────────▲──────────┘  ┌─────────┴─────────┐
     │ .agents/skills/trellis-*/    │                   │ 由           │ .claude/commands/ │
     │ .claude/agents/trellis-*.md  │      .claude/settings.json 注册  │  trellis/*.md     │
     └──────────────────────────────┘                                 └───────────────────┘
```

### 1.2 逐步拆解

| 周期步骤 | 触发者 | 执行者 | 写哪个状态文件 | 哪个 hook 因此改变注入 |
|---|---|---|---|---|
| **开工(冷启动)** | 打开会话 / `/clear` / compact | `.claude/hooks/session-start.py`(由 `.claude/settings.json` 的 `SessionStart` matcher `startup|clear|compact` 注册) | 只读;副作用是把 `TRELLIS_CONTEXT_ID` 追加进 `$CLAUDE_ENV_FILE`(`session-start.py:278-307`) | 自身注入 `<session-context>/<current-state>/<trellis-workflow>/<guidelines>/<task-status>/<ready>` 六个块(`session-start.py:866-916`) |
| **需求澄清(分类闸)** | 无任务时用户提任何需求 | `inject-workflow-state.py` 每轮注入 `[workflow-state:no_task]` 断言先问「要不要建 Trellis 任务」(`.trellis/workflow.md:176-181`) | 无 | UserPromptSubmit,每轮 |
| **建任务(1.0)** | 用户同意后,AI 跑 `task.py create` | `task.py create` → `common/task_store.py:295` | 新建 `task.json`(`status: "planning"`,`task_store.py:499`)、默认 `prd.md`(`task_store.py:536-542`)、空 `implement.jsonl`/`check.jsonl`(`task_store.py:545-556`);并自动把该任务设为本会话 active(`task_store.py:594-646`) | 下一轮 breadcrumb 自动切到 `[workflow-state:planning]` |
| **澄清需求(1.1)** | breadcrumb 指令 + `trellis-brainstorm` 技能 | 主会话对话,一次只问一个最高价值问题(`.agents/skills/trellis-brainstorm/SKILL.md:9-27`) | 反复改写 `prd.md`;复杂任务加 `design.md` + `implement.md` | `_get_task_status` 按 artifact 存在与否给不同 Next-Action(`session-start.py:479-511`) |
| **调研(1.2)** | 按需 | `trellis-research` sub-agent(`.claude/agents/trellis-research.md`) | **必须落盘** `<task>/research/*.md`(`trellis-research.md:14-16`) | `inject-subagent-context.py` 在 PreToolUse 改写 research 子代理的 prompt(`:762-866`) |
| **配上下文清单(1.3)** | breadcrumb / `/trellis:create-manifest` | AI 手写或 `task.py add-context` | `implement.jsonl` / `check.jsonl`,每行 `{"file":..,"reason":..}` | 决定 2.1/2.2 子代理能拿到多少 spec |
| **开始实现(1.4)** | 用户确认评审后,AI 跑 `task.py start <dir>` | `task.py cmd_start:171` | ① 硬校验 jsonl(`task.py:194-215`);② `status: planning → in_progress`(`task.py:112-114`);③ 记录当前分支到 `task.json.branch`(`task.py:119-125`);④ 写会话指针 `.trellis/.runtime/sessions/<key>.json`(`common/active_task.py:734-762`) | breadcrumb 切到 `[workflow-state:in_progress]`(`.trellis/workflow.md:225-230`) |
| **实现(2.1)** | breadcrumb 要求主会话派 `trellis-implement` | Task 工具派子代理 | 只改产品代码,**禁止 git commit**(`.claude/agents/trellis-implement.md:106` 附近约束、`inject-subagent-context.py:679-682`) | `inject-subagent-context.py` PreToolUse 把 jsonl 引用的文件 + prd/design/implement 全文塞进子代理 prompt(`:534-590`),并在开头打 `<!-- trellis-hook-injected -->` 标记(`:650`) |
| **验证/审查(2.2)** | breadcrumb | `trellis-check` sub-agent,**自审自修**(`.claude/agents/trellis-check.md:36-40`) | 直接改代码 | 同上,走 `get_check_context`(`:592-638`) |
| **规范回写(3.3)** | breadcrumb 流程串(`workflow.md:225-230` 的 Flow 行) | `trellis-update-spec` 技能 | `.trellis/spec/**` | — |
| **提交(3.4)** | 同上 | 主会话按 7 步批量提交流程,**必须一次性向用户出示 commit 计划再执行**(`.trellis/workflow.md:589-640`) | git | — |
| **收尾(3.5 / finish-work)** | 用户跑 `/trellis:finish-work` | `.claude/commands/trellis/finish-work.md` 四步:`get_context.py --mode record` → 分类脏文件 → `task.py archive` → `add_session.py` | archive:`status → completed` + `completedAt`(`task_store.py:1317-1318`)、目录移到 `tasks/archive/<YYYY-MM>/`、清掉所有指向它的会话指针(`task_store.py:1369-1371`)、自动 commit;add_session:追加 `workspace/<dev>/journal-N.md` + 改 `index.md` + 自动 commit | 归档后指针消失,下一轮 breadcrumb 回到 `no_task` |
| **跨会话续工** | 新会话 / `/trellis:continue` | SessionStart hook 自动恢复(会话指针 + status);`/trellis:continue` 用 `--mode phase` 定位到具体 step(`.claude/commands/trellis/continue.md:9-50`) | 读 `.trellis/.runtime/sessions/*.json` | — |

### 1.3 三个关键设计点

**(a) 状态只有一个字段,但会话指针是另一套。**
`task.json.status` 是全局的、进 git 的;「当前任务是哪个」是 per-session 的、gitignore 的(`.trellis/.gitignore:5-8`)。指针文件在 `.trellis/.runtime/sessions/<context_key>.json`(`common/active_task.py:253-255, 642-644`)。这样两个窗口可以同时开两个任务。当 context key 拿不到时,只有恰好一个 session 文件才会回退猜测,0 个或 ≥2 个一律拒绝猜(`common/active_task.py:683-707`)。

**(b) 归档时 `completed` 状态是「死」的。**
`cmd_archive` 在同一次调用里写 `status=completed` 又把目录移走(`task_store.py:1317` 和 `:1367`),指针随即被清,所以 `[workflow-state:completed]` breadcrumb 在正常流程里永远不会触发——workflow.md 自己承认了这点(`.trellis/workflow.md:250-257` 注释:"Currently DEAD in normal flow")。这是一处已知的不闭环。

**(c) 所有提示词文本都在 `workflow.md` 里,脚本只是解析器。**
`inject-workflow-state.py` 明确说没有 fallback 字典,tag 缺失就降级成一句 "Refer to workflow.md"(`:11-19`、`:209-233`、`:378-380`)。`workflow.md:647-650` 也写着 "All customization is done by editing this file; the scripts are parsers only."

---

## 2. 三个 hook:做什么、注多少、什么时候注

注册在 `.claude/settings.json`:`SessionStart`(matcher startup/clear/compact,timeout 30s)、`PreToolUse`(matcher `Task` 和 `Agent`,timeout 30s)、`UserPromptSubmit`(无 matcher,timeout 15s)。三个都有统一开关 `TRELLIS_HOOKS=0` / `TRELLIS_DISABLE_HOOKS=1`(`session-start.py:153-160`、`inject-workflow-state.py:421`、`inject-subagent-context.py:1093`)。

### 2.1 `session-start.py`(949 行)——一次性大概览

**时机**:会话启动、`/clear`、compact 后各一次。
**输出结构**(`:866-916`),按顺序:

| 块 | 内容 | 实测体量 |
|---|---|---|
| `<session-context>` | 一句话说明 | ~130 字符 |
| `<first-reply-notice>` | 要求首条回复口头确认「Trellis 已加载」,并规定用什么语言说(`:70-82`) | ~700 字符 |
| `<migration-warning>` | 仅在检测到 legacy spec 布局时出现(`:561-605`) | 0 或若干 |
| `<current-state>` | 开发者名、git 分支 + 脏文件数、当前任务路径与 status、活跃任务总数、journal 行数/2000、spec index 数量(`:697-754`) | ~6 行 |
| `<trellis-workflow>` | `workflow.md` 的 `## Phase Index` 到 `## Phase 1: Plan` 之间,**剥掉 breadcrumb 块和 HTML 注释**(`:803-820` + `:788-801`) | 原文 10,590 字符 → 剥离后 **5,632 字符 / 89 行**(本次实测) |
| `<guidelines>` | 上下文读取顺序 + 可用 spec index 路径清单 | ~10 行 |
| `<task-status>` | 90 行决策树产出的 `Status/Task/Present/Next-Action` 四行(`:424-511`) | ~4 行 |
| `<ready>` | 一句话收尾 | ~120 字符 |

合计约 **7–8 KB / 每次 SessionStart**。设计意图明确写在第一行:"compact SessionStart context. Use it to orient the session; load details on demand."(`:871`)——它只给索引,不给全文,`workflow.md` 全文 38,280 字符从不整篇注入。

**副作用**:把解析出的 session 身份写成 `export TRELLIS_CONTEXT_ID=<key>` 追加进 `$CLAUDE_ENV_FILE`(`:278-307`)。这是让**后续 Bash 里跑的 `task.py` 知道自己属于哪个会话**的唯一通道——不这么做,`task.py start` 在 hook 之外就没有身份(`:281-285` 注释原话)。它还做了去重:只比对文件里**最后一条** `TRELLIS_CONTEXT_ID` 导出,因为 shell 里后者覆盖前者(`:289-294`)。

### 2.2 `inject-workflow-state.py`(488 行)——每轮小面包屑

**时机**:`UserPromptSubmit`,**每一轮用户输入**。
**做什么**(`:420-486`):
1. 从 cwd 向上找 `.trellis/`,找不到静默 exit 0(`:83-99`)。
2. 检查 skip 关键词(默认 `no-trellis`,词边界匹配),命中则本轮不注(`:257-285`)。
3. 解析当前任务 + status。
4. 从 `workflow.md` 正则抓 `[workflow-state:<status>]...[/workflow-state:<status>]` 块(`:209-233`)。
5. 输出 `<workflow-state>\nTask: <id> (<status>)\n<body>\n</workflow-state>`(`:359-385`)。

**注入量**(本次实测各 breadcrumb 块字符数):`no_task` 472、`planning` 502、`planning-inline` 506、`in_progress` **930**、`in_progress-inline` 398、`completed` 135。也就是**每轮 0.4–0.9 KB**,是全系统里唯一的高频注入。

`in_progress` 那 930 字符值得看一眼(`.trellis/workflow.md:225-230`),它每轮都在重复四件事:哪些是 sub-agent 哪些是 skill、流水线顺序、子代理自我豁免(防止 implement 里再派 implement)、dispatch prompt 必须以 `Active task: <path>` 开头。**这是在用每轮 token 换取模型不跑偏。**

488 行里核心逻辑不到 80 行,剩下的是:Windows UTF-8 流重配(`:46-66`)、stdin 读取超时保护(`:387-418`,防 Kiro 之类 host 不关 stdin 导致永久阻塞)、平台检测(`:101-150`)、Codex 的 `dispatch_mode` 分支(`:286-338`)、Gemini 的事件名要叫 `BeforeAgent`(`:459-462`)、Kiro 要输出裸文本不要 JSON(`:451-456`)。

### 2.3 `inject-subagent-context.py`(1212 行)——派子代理时的大注入

**时机**:`PreToolUse` on `Task`/`Agent`,即**主会话每次派 sub-agent 之前**。
**做什么**(`:1092-1205`):
1. 只认三种子代理类型:`trellis-implement` / `trellis-check` / `trellis-research`(`:65-71`),其余静默放行。
2. implement/check 必须有 active task,否则 exit 0。
3. **路径包含校验**:把 task_dir 做 realpath,必须落在 repo 或 `.trellis` 真实位置之内,否则退出(`:1122-1148`)。注释说明这是防「升级前写入的越界指针在升级后仍然存活」。
4. 组装上下文 → 用固定模板包成新 prompt → 通过 `hookSpecificOutput.updatedInput` 把 Task 工具的 `prompt` 参数**整个替换掉**(`:1180-1205`)。

**注入内容与预算**(`:534-590`,implement 为例,顺序即优先级):
1. `implement.jsonl` 里每一条引用的文件全文
2. `prd.md`
3. `design.md`(有才注)
4. `implement.md`(有才注)

**字节预算**是硬编码 + 可配的(`inject-subagent-context.py:177-179`,与 `common/config.py:176-178` 一致,`.trellis/config.yaml` 尾部有注释说明):

- `max_file_bytes: 32768`——单个 jsonl 引用文件上限
- `max_artifact_bytes: 65536`——单个 prd/design/implement 上限
- `max_total_bytes: 131072`——**整个注入负载上限 128 KB**

超过单文件上限就 UTF-8 安全截断并加提示(`:201-233` 的 `truncate_utf8`,专门处理不切断多字节序列);总预算耗尽后,剩下的文件降级成「索引行」(路径 + 理由 + 大小),不再内联(`:309-334`)。

**一个补偿设计值得抄**:jsonl 为空时,不是静默不注,而是**把「没有 spec 上下文」这件事本身写进 prompt**,让子代理知道要自己去读 `.trellis/spec/`(`:483-506`)。注释直言 stderr 的 WARN 从来进不了任何会话。

**双通道容错**:hook 可能不触发(Windows、`--continue` 恢复、fork 分发、hooks 关闭),所以 agent 定义文件里写了 fallback 协议——找 `<!-- trellis-hook-injected -->` 标记,没有就自己按顺序读文件(`.claude/agents/trellis-implement.md:20-27`、`.claude/agents/trellis-check.md:20-27`)。

---

## 3. `get_context.py --mode`:四档,以及它是不是上下文预算的核心手段

`get_context.py` 本体只有 16 行,是个转发壳(`.trellis/scripts/get_context.py:12`),真正的 CLI 在 `common/git_context.py:46-103`。

参数(`common/git_context.py:50-71`):`--json/-j`、`--mode/-m {default,record,packages,phase}`、`--step`(仅 phase)、`--platform`(仅 phase)。

| mode | 给 agent 看什么 | 实现 | 谁在用 |
|---|---|---|---|
| `default` | 开发者名 → root git 状态(分支/脏/最近 commit)→ 子仓库 git → **CURRENT TASK**(路径、来源、名称、status、创建日期、描述、有无 prd)→ **ACTIVE TASKS** 层级树 → journal 位置 | `common/session_context.py:578-723` | `/trellis:continue` Step 1、`trellis-start` 技能 Step 1 |
| `record` | 「我的活跃任务 + git status + 最近 commit」,专为收尾归档设计 | `common/session_context.py:803-879` | `/trellis:finish-work` Step 1(`finish-work.md:8`) |
| `packages` | 所有 package 及其 spec 层的路径清单(不是内容) | `common/packages_context.py:158-237` | `trellis-before-dev`、`trellis-check`、1.3 配清单时找 spec |
| `phase` | 不带 `--step` → `workflow.md` 的 Phase Index;带 `--step 2.1` → 该 `#### 2.1` 小节到下一个 `####`/`##`/`---` 为止;`--platform claude` 再把不匹配的 `[平台名]...[/平台名]` 块剥掉 | `common/workflow_phase.py:100-131`(get_step)、`:134+`(filter_platform) | `/trellis:continue` Step 2/4、`trellis-start` Step 2 |

### 这是不是上下文预算的核心手段?

**不是唯一的,是三分之一。** Trellis 控预算靠三层,`--mode` 只占一层:

1. **懒加载分级(`--mode phase --step X.Y`)**——SessionStart 只注 Phase Index(5.6 KB),具体某一步的详文要主动拉。`workflow.md` 全文 38 KB,永远不整篇进上下文。**这一层是 pull 模型,靠 agent 自觉。**
2. **字节硬预算(`inject-subagent-context.py` 的 `_Budget`)**——子代理注入 128 KB 封顶,超了降级成索引行。**这一层是 push 模型,靠代码强制。**
3. **人工清单(`implement.jsonl` / `check.jsonl`)**——人/AI 事先挑好哪几个 spec 文件值得注,而不是把 `.trellis/spec/` 41 个文件全塞。**这一层是最强的裁剪,但也是最容易被跳过的(见 §5.4)。**

三层里,第 2 层是唯一有真代码强制的;第 1、3 层都是「靠约定」。

---

## 4. `task.py`:17 个子命令、状态转换在哪、有哪些硬校验

### 4.1 子命令全表(`task.py:745-762` 的 dispatch 字典)

| 子命令 | 作用 | 实现位置 |
|---|---|---|
| `create` | 建任务目录 + task.json + prd.md + 空 jsonl,并自动激活 | `common/task_store.py:295-679` |
| `add-context` | 往 implement/check.jsonl 追加一行 | `common/task_context.py` |
| `validate` | 校验 jsonl 格式与引用文件存在性 | `common/task_context.py:157-198` |
| `list-context` | 列出 jsonl 条目 | `common/task_context.py` |
| `start` | 设为本会话 active + status 翻到 in_progress + 记分支 | `task.py:171-270` |
| `current` | 显示当前任务(`--source` / `--json`) | `task.py:292-341` |
| `finish` | **只清会话指针,不改 status** | `task.py:273-289` |
| `set-branch` / `set-base-branch` / `set-scope` / `set-meta` | 改 task.json 字段 | `common/task_store.py:1704-1860` |
| `rename` | 改 slug 并同步所有引用(支持 `--dry-run`) | `common/task_store.py:1003-1132` |
| `archive` | status→completed + 移目录 + 解父子链 + 清指针 + 自动 commit | `common/task_store.py:1223-1400` |
| `list` / `list-archive` | 列表(`--mine` / `--status` / `--json`) | `task.py:369-...` |
| `add-subtask` / `remove-subtask` | 父子链接 | `common/task_store.py:1557-1699` |

注意 **`finish` 不是「完成任务」**,它只是清掉「当前任务」指针(`task.py:273-289`),`task.json` 一个字节都不动。真正的完成是 `archive`。这个命名很容易误读。

### 4.2 状态转换发生在三个地方

```
(不存在) --create--> planning --start--> in_progress --archive--> completed(同一调用内目录被移走)
```

1. `common/task_store.py:499` —— `"status": "planning"`(create 写死)
2. `task.py:112-114` —— `if data.get("status") == "planning": data["status"] = "in_progress"`(**只从 planning 翻,已经是别的状态就不动**)
3. `common/task_store.py:1317-1318` —— `data["status"] = "completed"` + `completedAt`

**没有别的写入点。** 中间态 `review` 只在 `list --status` 的 help 文本里被提到(`task.py:567`),没有任何命令能把任务设成 `review`。

### 4.3 硬校验清单(会 `return 1` 拦住的)

**`create`**(`common/task_store.py:295-353`,顺序即执行顺序,失败时不留任何文件):
- title 为空/纯空白 → 拒(理由写得很清楚:归档时会因空 title 被拒,现在拦下只花一次重敲命令)
- `--description` 为空 → 拒(同上)
- `--meta` 格式非法 → 拒
- monorepo 下 `--package` 不认识 → 拒
- 无 developer 且未给 `--assignee` → 拒
- 目录已存在且没给 `--force` → 拒(`:444-455`)
- 归档区里已有同名 → 拒

**`start`**(`task.py:171-270`):
- 任务目录解析不到 / 不是目录 → 拒
- **`implement.jsonl` 或 `check.jsonl` 存在但零条有效条目 → 拒**,必须 `--allow-empty-context` 才放行(`task.py:194-215`)。理由写在注释里:否则每个子代理都会带着零 spec 上下文跑,而且下游没有任何东西会把这件事暴露给主会话。
- 拿不到 session 身份 → **降级不拒**:打黄字提示,仍然翻 status,只是不写指针(`task.py:236-253`)

**`archive`**(`common/task_store.py:1223-1400`):
- 目标不是 `.trellis/tasks/` 的直接子目录 → 拒(防二次归档)
- 归档目的地已存在 → 拒,**且在改任何状态之前就检查**(`:1265-1277`,注释解释:否则等到 mover 发现冲突时,任务已被标 completed、子任务已被解链、会话指针已被清,全得手工回滚)
- **分支元数据校验**(`:1143-1222`):`branch == base_branch` → 拒(PR 不能以自己为目标);有 `base_branch` 且仓库有 remote 但 `branch` 为空 → 拒(分支没被记下来,归档后不可恢复)。`--skip-branch-validation` 可绕过。分支已被删只是 warning。
- 子任务解链写失败 → 停在移动之前(`:1355-1366`)
- 自动 commit 失败 → 返回 1 并要求先处理 `git status`

### 4.4 有没有「未 check 不能 finish」这类质量门禁?

**没有。** 通读 `cmd_archive`(`task_store.py:1223-1400`)与 `finish-work.md`,不存在任何「检查是否跑过 2.2」「检查 lint 是否绿」的代码级校验。质量门禁全部是**散文约束**,写在 `workflow.md:291-295`(Guardrails)和 `finish-work.md:37-44`(发现脏代码就 bail out,让用户回 Phase 3.4)。

唯一带强制性的「质量」相关校验是 `start` 的 jsonl 门禁,而它检的是**上下文准备度**,不是产出质量。

另外值得注意:2.2 的 check 是**同模型 sub-agent 自审自修**(`.claude/agents/trellis-check.md:36-40` "Self-fix - Fix issues yourself, not just report them"),不是跨模型对抗审。如果要复用这套周期,这一环需要替换。

---

## 5. 「重」的具体数字

### 5.1 运行时 Python

| 项 | 数字 | 出处 |
|---|---|---|
| `.trellis/scripts` 总行数 | **11,514 行 / 28 个 .py** | `wc -l` 实测 |
| `.claude/hooks` 总行数 | **2,649 行 / 3 个 .py** | 同上 |
| 合计运行时 Python | **14,163 行 / 31 个文件** | 同上 |

单文件 Top 6:`common/task_store.py` 1,874、`add_session.py` 1,545、`inject-subagent-context.py` 1,212、`session-start.py` 949、`common/cli_adapter.py` 950、`common/session_context.py` 892、`common/active_task.py` 857、`task.py` 801。

### 5.2 依赖与运行时

- **Python 第三方依赖:0**。全部标准库(实测统计 `.trellis/scripts` + `.claude/hooks` 全部顶层 import,只出现 `pathlib/sys/json/re/os/typing/datetime/subprocess/dataclasses/argparse/warnings/time/io/hashlib/threading/tempfile/shutil/shlex/queue/collections`)。YAML 是自己写的 114 行简易解析器(`common/trellis_config.py:113-226`)。
- **Python 版本**:≥ 3.9 强制(`packages/cli/src/commands/init.ts:70-71,93-102`),有逃生开关 `TRELLIS_SKIP_PYTHON_CHECK=1`。
- **Node**:≥ 18.17,**只在安装/升级时用**(`packages/cli/package.json` engines)。跑起来之后日常周期不需要 node。
- **CLI 自身依赖 8 个**:`chalk commander figlet giget inquirer undici zod` + 自家 core(`packages/cli/package.json`)。

### 5.3 平台适配的体量

仓库里各平台目录文件数(实测):

| 目录 | 文件数(含 .backup) | 不含 .backup |
|---|---|---|
| `.claude` | 96 | 92 |
| `.opencode` | 60 | 56 |
| `.cursor` | 59 | 54 |
| `.pi` | 51 | 51 |
| `.omp` | 38 | 38 |
| `.codex` | 9 | 9 |
| `.agents`(平台中立技能池) | 85 | 85 |
| **合计** | **398** | **385** |

- `.trellis/.template-hashes.json` 记录 **228 个受管模板文件**,分布:`.opencode` 53、`.cursor` 51、`.claude` 50、`.agents` 46、`.trellis` 12、`.codex` 8、`.pi` 7、`AGENTS.md` 1。
- 支持平台数:**22**(`packages/cli/src/types/ai-tools.ts:11-32`)。
- 配置器:**24 个 .ts**(`packages/cli/src/configurators/`)。
- CLI 源码:**119 个非测试 .ts / 26,841 行**;测试 **82 个 / 41,514 行**;core 包 **54 个 .ts / 10,473 行**。
- 光是「哪个平台装哪几个 hook」这张表就带了 **50 行注释**说明每条的验证依据(`packages/cli/src/templates/shared-hooks/index.ts:46-94`)。
- `common/active_task.py:68-140` 是 21 个平台的 session 环境变量名表,每条都标注了「REAL / REAL 但只在 hook 作用域 / UNVERIFIED」和验证日期——注释里写着 2026-08-05 的审计发现 21 个平台里有 **12 个声明的环境变量名从未存在过**,是按命名规律猜的。

### 5.4 一个新项目 init 后落多少文件(Claude Code 单平台)

按 `packages/cli/src/configurators/workflow.ts:125-195` + `configurators/claude.ts:108-126` 的代码路径推算:

**`.trellis/` 侧(约 50 个文件)**
| 项 | 数量 | 出处 |
|---|---|---|
| `scripts/**`(整目录拷贝) | **28** | `workflow.ts:139-141` + `templates/trellis/scripts/` 实际文件数 |
| `workflow.md` / `config.yaml` / `.gitignore` / `.version` | 4 | `workflow.ts:144-159`、`init.ts:1931-1933` |
| `agents/`(channel 运行时) | 2(check.md、implement.md) | `workflow.ts:171-174` + `templates/trellis/agents/` |
| `workspace/index.md` | 1 | `workflow.ts:177-181` |
| `spec/`(fullstack 默认) | **16** = guides 3 + backend 6 + frontend 7 | `workflow.ts:278-291, 200-224, 225-250` |
| `tasks/`(空目录) | 0 | `workflow.ts:184` |
| `.template-hashes.json` | 1 | `init.ts:1970` |
| 小计 | **≈ 52** | |

**`.claude/` 侧(约 47 个文件)**
| 项 | 数量 | 出处 |
|---|---|---|
| `agents/trellis-{implement,check,research}.md` | 3 | `templates/claude/agents/` |
| `settings.json` | 1 | `claude.ts:149` 路径 / `templates/claude/settings.json` |
| `commands/trellis/{continue,finish-work}.md` | 2(`start` 在 agent-capable 平台被过滤掉,`shared.ts:428-431`) | `claude.ts:113-115` |
| `skills/trellis-{before-dev,brainstorm,break-loop,check,update-spec}/SKILL.md` | 5 | `templates/common/skills/` |
| `skills/` 内建多文件技能 | **38** = trellis-channel 6 + trellis-meta 24 + trellis-session-insight 3 + trellis-spec-bootstrap 5 | `templates/common/bundled-skills/` |
| `hooks/*.py` | 3 | `shared-hooks/index.ts:99-103` |
| 小计 | **≈ 52**(与 `.template-hashes.json` 里 `.claude` 的 50 条吻合) | |

**根目录**:`AGENTS.md` 1 个 + `.gitattributes` 的 journal merge=union 规则(追加式,`workflow.ts:163`)。

> **一个 Claude-only 的新项目,init 完落地约 100 个文件、约 14,000 行 Python。** 其中周期真正必需的核心不到 15 个文件。

### 5.5 长期运行的状态膨胀(dogfood 仓库实测)

- `.trellis/tasks/` 共 **1,361 个文件**,其中归档 **231 个任务目录**;单任务平均 5.6 个文件(中位数 4)。
- `.trellis/workspace/` 21 个文件,journal 共 **10,437 行**,单开发者累计 **175 次会话记录**(`.trellis/workspace/taosu/index.md:11`)。
- `.trellis/spec/` 41 个 md。

### 5.6 最重要的一个反证数字

对 242 个任务(活跃 + 归档)统计 artifact 实际存在率:

| Artifact | 存在数 | 占比 |
|---|---|---|
| `prd.md` | 234 | **97%** |
| `design.md` | 35 | **14%** |
| `implement.md` | 35 | **14%** |
| `research/` | 46 | 19% |
| `implement.jsonl` 有真条目 | 107 | **44%** |
| `implement.jsonl` 存在但为空 | 52 | 21% |
| `implement.jsonl` 不存在 | 83 | 34% |

**解读**:
- `prd.md` 是唯一被普遍使用的规划产物。
- `design.md` / `implement.md`(「复杂任务必须有」)只在 14% 的任务里出现——说明 86% 的真实任务是「轻量任务」。
- **被 `task.py start` 硬门禁的 jsonl,超过一半(135/242)是空的或不存在的。** 这个门禁在实际使用中要么被 `--allow-empty-context` 绕过,要么被填上应付性内容(仓库里还能看到未删的 `_example` 种子行,如 `.trellis/tasks/08-06-converge-platform-templates/implement.jsonl`)。

---

## 6. 判断:单人单平台(Claude Code)轻量版,哪些能用 ≤50 行 shell/markdown 替代

判定标准:**这段代码是在解决「周期语义」问题,还是在解决「多平台 / 容错 / 幂等」问题?** 前者可以极简重写,后者要么砍掉需求,要么老老实实写代码。

### 6.1 可以用 ≤50 行替代(9 项)

| 机制 | 原体量 | 轻量替代 | 依据 |
|---|---|---|---|
| **任务状态机** | `task.py` 801 + `task_store.py` 1,874 | **一个 `task.json` + 3 行 `python -c` 改字段**;create/start/archive 各 ≤15 行 shell | 真正的状态转换只有 3 处赋值(`task_store.py:499`、`task.py:112-114`、`task_store.py:1317`)。其余是路径解析容错、父子双向链接、`--force`/`--dry-run`/`--json` 变体、损坏 JSON 的分级报错。单人项目不需要父子树(实测 242 个任务里的层级使用未核实,但 `list` 的层级渲染逻辑 `task.py:369-460` 占了 90 行) |
| **每轮 breadcrumb 注入** | `inject-workflow-state.py` 488 行 | **≤40 行 python**:读 `.trellis/current` → 读 `task.json.status` → 正则抓 `workflow.md` 的 tag 块 → 打印 `{"hookSpecificOutput":{...}}` | 核心三段:`load_breadcrumbs` 一条正则(`:209-233`)、`build_breadcrumb` 拼字符串(`:359-385`)、`main` 输出(`:465-484`)。剩余 400 行是 Windows 流重配(`:46-66`)、stdin 超时守护线程(`:387-418`)、平台检测(`:101-150`)、Codex dispatch_mode(`:286-338`)、Gemini/Kiro 输出格式分支(`:451-462`)——**单平台全部为零** |
| **SessionStart 概览注入** | `session-start.py` 949 行 | **≤45 行**:`git branch`+`git status --porcelain \| wc -l` → 读当前任务 status → `sed -n '/^## Phase Index/,/^## Phase 1/p' workflow.md` → 输出 JSON | 内容生产只有三个函数:`_build_compact_current_state`(:697-754,57 行)、`_build_workflow_overview`(:803-820,17 行)、`_get_task_status`(:424-511,87 行)。剩下的是 10 个平台的 `*_PROJECT_DIR` 环境变量轮询(:834-853)、Windows 路径归一化(:22-68)、monorepo spec scope 过滤(:517-695,178 行)、更新提醒节流(:329-350) |
| **workflow.md 分步抽取** | `workflow_phase.py` 242 行 | **≤15 行 awk**:`#### X.Y` 到下一个 `####`/`##`/`---` | `get_step` 本身就是 31 行纯行扫描(`:100-131`);`filter_platform` + `_parse_marker` + `resolve_effective_platform` 是平台块过滤,单平台**整段删掉**,连 `workflow.md` 里的 `[Claude Code, Cursor, ...]` 标记都不用写 |
| **会话身份 → shell 传递** | `active_task.py` 857 行(其中 env 表 `:68-140` + shell ticket 桥 `:381-512` 占 ~200 行) | **≤10 行**:SessionStart 里 `echo "export TRELLIS_SID=$session_id" >> $CLAUDE_ENV_FILE`;脚本读 `$TRELLIS_SID` | Claude Code 有两条现成通道:hook stdin 的 `session_id` 字段(`active_task.py:38`)和 `CLAUDE_ENV_FILE`(`session-start.py:278-307`)。21 平台环境变量表(其中 12 个被证实是编造的)、30 秒 TTL 的 shell ticket 桥、单会话回退推断(`:683-707`)——**全是为其他平台存在的** |
| **归档** | `cmd_archive` 178 行 + `_validate_branch_metadata` 80 行 + `_auto_commit_archive` 107 行 | **≤20 行**:改 status → `mv` 到 `archive/$(date +%Y-%m)/` → `git commit` | 分支元数据校验(`task_store.py:1143-1222`)整套是为「PR 元数据在离开活跃树后不可重建」服务(`:1152-1154` 原话),单人无 PR 契约的项目不需要;子任务解链(`:1338-1366`)不需要;归档冲突预检(`:1265-1277`)可以退化成 `mv` 自然失败 |
| **会话日志 / journal** | `add_session.py` 1,545 行 | **≤20 行**:`printf` 追加一段到 `journal.md` | 1,545 行的构成:commit OID 解析与本地对象库校验(`:321-432`)、fingerprint 幂等与断点续跑(`:447-520, 653-871`)、`index.md` 自动区块重写(`:952-1069`)、跨 git ref 的会话号收敛(`:556-638`)、auto-commit(`:1070-1165`)。这些解决的是「命令中途被打断后重跑不要写重复」和「多人多 worktree 的会话号不冲突」——单人单会话把这两个需求砍掉即可 |
| **`get_context.py --mode record/default`** | `session_context.py` 892 行 | **≤25 行 shell**:`git status --porcelain`、`git log --oneline -10`、`cat task.json` | 892 行里大头是 monorepo 子仓库发现与聚合(`:97-320`,~220 行)、Trellis 版本更新提醒的版本号比较与节流(`:321-489`,~170 行)。单仓库单人这两块都不需要 |
| **spec 预置模板** | 16 个 md 文件 + `workflow.ts:200-307` 的写入代码 | **0 行**:让 `.trellis/spec/` 从空开始,靠 `trellis-update-spec` 那类技能按需生长 | 预置的是通用样板(`templates/markdown/spec/backend/*.txt` 等),`trellis-spec-bootstrap/SKILL.md:29-34` 自己就说「Treat templates as starting points, not contracts. Delete, rename, split...」。预置 16 个占位文件的净收益是负的 |

### 6.2 替代不了 / 需要真代码(4 项)

| 机制 | 为什么替代不了 | 依据 |
|---|---|---|
| **子代理上下文注入(PreToolUse 改写 prompt)** | 需要:① 从 hook JSON 里解出 `tool_input`,② 把整个 `tool_input` 连同改写后的 `prompt` 回写成 `updatedInput`,③ 多文件按优先级读入并做**总字节预算 + UTF-8 安全截断**,④ 超预算时降级为索引行。shell 做嵌套 JSON 读改写 + 字节级预算不现实 | `:1180-1205`(输出结构)、`:201-233`(`truncate_utf8`,要回退到 UTF-8 lead byte)、`:235-249`(`_Budget`)、`:309-334`(降级为索引行)。**但**:如果轻量版砍掉 jsonl 清单(见下条),只注 `prd.md` 一个文件,这个 hook 可以缩到 **≤50 行 python**——单文件、单上限、无降级逻辑 |
| **路径包含校验(防指针逃逸)** | 这是安全边界,不是便利功能。任务指针在 realpath 之后必须落在 repo 或 `.trellis` 真实位置内,否则子代理 prompt 里会出现仓库外的文件内容 | `:251-261`(`_real_path_contained`,含 Windows 跨盘符 ValueError 的 fail-closed)、`:1122-1148`。`.trellis` 本身可能是符号链接指向外部存储(`:1132-1134` 注释),所以是**两个**合法基准。约 30 行 python,不能省 |
| **「hook 没触发」的双通道降级** | Claude Code 的 hook 在 `--continue` 恢复、Windows、hooks 被关时确实不跑。没有 fallback,子代理就带零上下文干活且无人知晓 | `.claude/agents/trellis-implement.md:20-27`。这一条**不需要代码**——它是写在 agent 定义 markdown 里的协议(找 `<!-- trellis-hook-injected -->` 标记,没有就自己按顺序读)。所以严格说属于「≤50 行 markdown 能做」,但**不能不做** |
| **task.json 的原子写与损坏容错** | `read_json_checked` + `write_json` 的分级失败处理贯穿全部命令。一次半写的 task.json 会让所有 hook 把任务显示成 status unknown 且无人报错 | `common/io.py` 160 行、`task.py:100-108`、`task_store.py:152-198`。轻量版可以缩到 ~30 行(写临时文件 + `os.replace`),但**不能直接 `json.dump` 到目标文件** |

### 6.3 建议直接砍掉(不是替代,是取消需求)

| 机制 | 砍掉的依据 |
|---|---|
| **`implement.jsonl` / `check.jsonl` 上下文清单 + `task.py start` 的硬门禁** | 实测:242 个任务里 135 个(56%)该文件为空或不存在,仓库里还有未删的 `_example` 种子行。一个「必经关卡」在作者自己的仓库里被绕过一半以上,说明它索取的准备成本高于它交付的价值。替代方案:子代理只注 `prd.md` + `design.md`,spec 让子代理自己按 `.trellis/spec/*/index.md` 去找——这正是 `inject-subagent-context.py:483-506` 在 jsonl 为空时已经在做的降级路径。**门禁位置**:`task.py:194-215`;**实测数据**:见 §5.6 |
| **`design.md` / `implement.md` 的「复杂任务必须有」硬要求** | 实测只有 14% 的任务有。改成「AI 判断需要时才写」,别写进 `[required]` 清单(`workflow.md:449-467` 的完成条件表) |
| **多平台一切**(configurators / templates / shared-hooks 路由表 / 21 平台 env 表 / Kiro-Gemini-Codex-ZCode 的输出格式分支) | 26,841 行 CLI + 385 个平台文件 + `active_task.py` 里 200 行的平台表。单平台**全部为零**。`shared-hooks/index.ts:46-94` 那 50 行注释本身就是这套复杂度的代价证明 |
| **`.trellis/.template-hashes.json` + `trellis update` 的模板漂移追踪** | 228 条哈希记录、`packages/cli/src/commands/update.ts`(未细读)。自己的 harness 自己改,用 git 就够了 |
| **多人 / 多 worktree 支持**(developer identity、`--mine`、journal 的跨 ref 会话号收敛、worktree 并行告警) | `init_developer.py`、`common/developer.py` 192 行、`add_session.py:556-638, 254-296`。单人项目全部无意义 |

### 6.4 一句话取舍建议

**保留:一个 `task.json`(4 个字段:title、status、prd 路径、branch)、一个 `workflow.md`(phase 索引 + 每状态一段 breadcrumb)、三个 hook(SessionStart 概览 ≤45 行 / UserPromptSubmit breadcrumb ≤40 行 / PreToolUse 单文件注入 ≤50 行)、一个 `journal.md` 追加脚本 ≤20 行。**
**砍掉:jsonl 清单及其门禁、design/implement 强制、多平台、模板哈希、多人身份、PR 分支元数据校验。**
**必须写真代码的只有两处:原子写(~30 行)和子代理注入的路径包含校验(~30 行)。**

预估:**≤400 行 Python + 1 个 workflow.md + 5 个 skill/command markdown**,对上 Trellis 的 14,163 行运行时 Python + 100 个 init 文件。

---

## 附录:本次实际读过的关键文件

**脚本与 hook**
- `.trellis/scripts/task.py`(801)、`get_context.py`(16)、`get_developer.py`(26)、`init_developer.py`(51)、`add_session.py`(1545,读 docstring + main + 函数目录)、`hooks/linear_sync.py`(243,读头部)
- `.trellis/scripts/common/`:`task_store.py`(1874,读 create/archive/branch 校验)、`active_task.py`(857,读平台表/resolve/set)、`git_context.py`(106 全读)、`workflow_phase.py`(242,读 get_step)、`task_context.py`(470,读 curated_entry_count/cmd_validate)、`task_utils.py`(498,读 run_task_hooks)、`session_context.py`(892,读函数目录 + get_context_text)、`config.py`(读 limits)、`trellis_config.py`(读 YAML 解析)、`packages_context.py`(读 docstring)
- `.claude/hooks/session-start.py`(949)、`inject-workflow-state.py`(488)、`inject-subagent-context.py`(1212)
- `.claude/settings.json`(全读)

**内容与配置**
- `.trellis/workflow.md`(709 行,重点 144-307 / 308-467 / 469-566 / 567-645 / 647-709)
- `.trellis/config.yaml`(全读)、`.trellis/.gitignore`、`.trellis/.template-hashes.json`(程序化统计)
- `.claude/commands/trellis/{continue,finish-work}.md`(全读)、`create-manifest.md`/`improve-ut.md`/`publish-skill.md`(仅行数,系仓库自用非模板)
- `.claude/agents/trellis-{implement,check,research}.md`(头部)
- `.agents/skills/trellis-{start,continue,finish-work,before-dev,check,break-loop,brainstorm,spec-bootstrap,session-insight,update-spec}/SKILL.md`

**CLI 与模板**
- `packages/cli/src/configurators/{claude.ts,shared.ts,workflow.ts}`
- `packages/cli/src/templates/{claude,common,trellis,shared-hooks,markdown}/`(目录清单 + index.ts)
- `packages/cli/src/commands/init.ts`(python 版本闸 + 落盘尾段)
- `packages/cli/src/types/ai-tools.ts`(平台表)、`packages/cli/package.json`

**未核实项**
- `trellis update` / `trellis mem` / `trellis channel` 的实现细节未读(仅从命令清单与 SKILL.md 得知其存在)
- `.trellis/spec/**` 41 个 md 的具体内容未读(只统计了数量与生成路径)
- 父子任务树在实际 242 个任务中的使用率未统计
