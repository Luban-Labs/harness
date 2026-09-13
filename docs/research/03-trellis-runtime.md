# Trellis 运行时包 / CLI / 官方定位 —— 只读研究报告

- 研究对象：本地 checkout `/private/tmp/claude-501/-Users-sangba-Downloads-02-----------harness/c38a95e8-724a-458f-a564-59ac3a323ca8/scratchpad/trellis`
- 版本锚点：`packages/cli/package.json:3` 与 `packages/core/package.json:3` 均为 `0.6.16`；git 只有一个 shallow commit `88f4834 0.6.16`，唯一 tag `v0.6.16`。仓库自用的 `.trellis/.version` 是 `0.6.14`（自举落后两个补丁号）。
- 溯源约定：下文路径均相对上述仓库根；行号来自本次实际读取。凡我未在文件中读到、只能从上下文推断的，都显式标「解读」或「未核实」。
- 焦点：只沿「开工 → 需求澄清 → 拆任务 → 实现 → 验证/审查 → 收尾/交接 → 跨会话续工」这条链展开。UI、营销、平台适配细节只在影响周期链时提一句。

---

## 0. 一句话结论（给 owner）

Trellis 真正管「项目周期」的东西**不在它的 npm 运行时包里**，而在它 `init` 时写进你仓库的一堆 Markdown + Python 脚本里：周期状态机是 `.trellis/workflow.md` 的三阶段文本，状态存储是 `task.json` 的 24 个字段，状态机的执行者是每轮注入的 hook 面包屑。`packages/core` 里 10473 行 TypeScript 中，只有 561 行（task 模块）和周期管理相关，另外 9912 行是 mem（跨会话记忆检索）和 channel（多 agent 通信运行时）两块**附加能力**。想做「比 Trellis 轻的项目级 harness」，可参考的是它的周期状态定义与阶段闸门设计；不必抄的是 22 平台适配层、channel 运行时、mem 检索层，以及 148 份迁移清单背后的版本兼容机器。

---

## 1. 官方怎么定义自己

### 1.1 一句话定位

`README.md:10-11`：

> **An out-of-the-box engineering framework for AI coding.**
> AI writes code fast, but every session it starts from scratch — no memory of your project, your conventions, or your team's requirements. Trellis persists specs, tasks, and memory into your repo, so any coding agent works to your engineering standards.

中文版 `README_CN.md:10-11` 措辞一致：「开箱即用的 AI 编码工程化框架 …… 把规范、任务、记忆沉淀进仓库」。

它自称解决的核心问题只有一个：**AI 每次会话从零开始**。三个落地物是 spec（规范）、task（任务）、memory（记忆），都持久化在仓库里。

内部另有两套不同的自称，说明定位在演化中：
- `packages/cli/package.json:4`：`"AI capabilities grow like ivy — Trellis provides the structure to guide them along a disciplined path"`（比喻式）
- `packages/cli/src/cli/index.ts:66-68`：`"AI-assisted development workflow framework for Cursor, Claude Code and more"`（CLI `--help` 里看到的）
- `COPYRIGHT:1`：`"All-in-one AI framework & toolkit for Claude Code & Cursor"`（`init` banner 也打这句，见 `packages/cli/src/commands/init.ts:1134`）

四处口径不完全统一，但都不提「项目周期管理」这个词——它把周期链包装成「workflow / task」。

### 1.2 Why Trellis（`README.md:39-47`）

五行能力表，逐条对周期链的位置：

| README 原文能力 | 对应周期环节 |
| --- | --- |
| **Auto-injected specs** — 规范写进 `.trellis/spec/`，按会话注入 | 贯穿全周期的上下文供给 |
| **Task-centered workflow** — PRD/实现上下文/审查上下文/任务状态放 `.trellis/tasks/` | 拆任务 + 实现 + 验证 |
| **Project memory** — `.trellis/workspace/` 的 journal 保留上次发生了什么 | 收尾/交接 + 跨会话续工 |
| **Team-shared standards** — spec 进仓库，一个人的流程变成全团队基础设施 | 与周期无关（团队治理） |
| **Multi-platform setup** — 同一套结构覆盖 22 个 AI coding 平台 | 与周期无关（分发） |

即：官方五条卖点里只有三条服务周期链，另外两条是「团队共享」和「跨平台」。

### 1.3 How It Works（`README.md:78-85`）

自述是一个「4 阶段循环 + 自动触发的 skill 与子代理」：

1. **Plan** — `trellis-brainstorm` 一次一个问题走需求，写 `prd.md`；重调研的部分派 `trellis-research` 子代理；产出是精选 spec + research 文件，由 `implement.jsonl` / `check.jsonl` 编排。
2. **Implement** — `trellis-implement` 子代理照 PRD 写代码，上下文自动注入，**不执行 git commit**。
3. **Verify** — `trellis-check` 子代理对 diff 逐条核 spec，并跑 lint / type-check / 测试，能修的自修。
4. **Finish** — 最终检查后，`trellis-update-spec` 把本轮认知回写 `.trellis/spec/`。

注意：README 说的是 4 阶段，仓库里实际落地的 `.trellis/workflow.md:146-150` 是 **3 阶段**（Plan / Execute / Finish），README 的 Implement + Verify 被合并成 Phase 2 Execute。README 与运行时文档口径不一致（可核对 `.trellis/workflow.md:147-149`）。

### 1.4 How to Use（`README.md:69-76`）—— 用户视角只有 4 个动作

1. 用自然语言描述需求
2. 和 AI 头脑风暴到 PRD 清晰，然后开始实现
3. 放手让它跑（AI 自己调 Implement 并自检）
4. 活干完或上下文快满时打 `/trellis:finish-work`，Trellis 归档任务 + 更新 journal

这是它整条周期链**对人暴露的全部界面**：一次自然语言输入 + 一条收尾命令。中间的拆任务、状态流转、上下文注入都是隐式的。这一点是它设计上最值得借鉴的地方。

### 1.5 Quick Start —— 用户要做几步

`README.md:54-67` 写了三个代码块，但第 2、3 步是二选一，**实际是 2 步**：

```bash
# 1. 装
npm install -g @mindfoldhq/trellis@latest
# 2. 在仓库里初始化（二选一）
trellis init -u your-name
trellis init --cursor --opencode --codex -u your-name
```

前置要求 `README.md:49-52`：**Node.js >= 18** 与 **Python >= 3.9**（两个都是硬性的，见第 4 节）。

真实的「2 步」有水分：`trellis init` 不带 `-y` 时是一个多轮交互式向导（第 3.2 节列了 9 类交互项），并且会往仓库里写 200+ 个文件（本仓库自举的 `.trellis/.template-hashes.json` 记录了 **228** 个受管模板文件）。

### 1.6 FAQ（`README.md:97-151`，6 条）

1. **与 `CLAUDE.md` / `AGENTS.md` / `.cursorrules` 的区别**（`README.md:100-104`）：那些文件「容易变成单体巨石」，Trellis 在其上加了 scoped spec、按任务的 PRD、workflow gate、workspace memory、按平台生成的适配文件。—— 这条是它对自己价值主张最诚实的一次表述：**它卖的是"把一个大文件拆成有闸门的多文件状态机"**。
2. 是否只支持 Claude Code：不是，是项目层。
3. 个人还是团队：都行，团队收益更大。
4. 是否要手写每个 spec：不用，可 AI 起草再人工收紧。
5. 团队会不会冲突：journal 按开发者隔离，spec/task 进仓库走评审。
6. **能否临时对比开/关 Trellis**（`README.md:135-151`）：`trellis ablate` / `trellis restore`。这条 FAQ 值得注意——一个框架需要专门做「把我自己从项目里临时摘掉」的命令，说明它对项目的侵入面已经大到用户会怀疑「这东西到底有没有用」。FAQ 自己承认恢复事务里含 `.trellis` 的 task/spec/workspace 精确字节，「可能有用户编写的敏感文本」。

### 1.7 中英文 README 差异

对照读完，结构与内容逐节一一对应，无实质差异。唯一增量：`README_CN.md:162-168` 多了「联系我们」的微信群与飞书群二维码，英文版没有。技术口径完全一致（同为 22 平台、同为 Node>=18 / Python>=3.9、同为 2 步 Quick Start）。

### 1.8 仓库根的 AGENTS.md / CLAUDE.md

- `AGENTS.md:1-21` 是 Trellis 自己 `init` 写入的受管块（`<!-- TRELLIS:START -->` … `<!-- TRELLIS:END -->`），内容极短：告诉 AI 「知识在 `.trellis/` 下」，并列出 workflow.md / spec/ / workspace/ / tasks/ 四个入口。`AGENTS.md:19` 明确：块外的编辑会被保留，块内的会被 `trellis update` 覆盖。**这是一个可直接抄的设计：入口文件只做路由，不装内容。**
- `AGENTS.md:23-65` 和 `CLAUDE.md:67-108` 各有一段 `gitnexus` 代码索引 MCP 的块——不是 Trellis 的，是仓库作者自己装的第三方工具。
- `CLAUDE.md:1-65` 是通用的「减少 LLM 编码错误」行为准则（想清楚再写、最简实现、外科手术式改动、目标驱动执行）。其中 `CLAUDE.md:54-59` 的多步计划格式 `1. [Step] → verify: [check]` 与 owner 自己 CLAUDE.md 里的同名约定形态一致。

---

## 2. packages/core 的 task / mem / channel

### 2.1 包的形状

`packages/core/package.json:2-35`：包名 `@mindfoldhq/trellis-core`，ESM，导出 4 个子路径 `./channel`、`./mem`、`./task`、`./testing`，外加根 barrel。

关键结构信号 —— **根 barrel 只导出 channel 和 task，不导出 mem**：

```ts
// packages/core/src/index.ts:6-7
export * from "./channel/index.js";
export * from "./task/index.js";
```

`packages/core/src/mem/index.ts:5-13` 明确解释了原因：mem 是「刻意不 re-export」的独立子包，v1 范围只做「持久化会话检索与上下文抽取」，不读 channel 事件日志、无游标分页。

### 2.2 代码量分布（本次实测）

| 模块 | 源文件数 | 源码行数 | 测试文件数 |
| --- | --- | --- | --- |
| `src/task/` | 5 | **561** | 4 |
| `src/mem/` | 18 | **5357** | 6 |
| `src/channel/` | 29 | **4544** | 11 |
| `src/testing/` | 1 | 4 | — |
| 合计 | 53 | 10473 | 21 |

（统计命令：`find <dir> -name '*.ts' | xargs cat | wc -l`，`packages/core/src` 下执行。）

**结论：周期管理相关的代码只占 core 的 5.4%。**

### 2.3 task —— 唯一与周期直接相关的模块，且它不是执行者

`packages/core/src/task/index.ts:1-31` 的公共面只有四组东西：

1. `TrellisTaskRecord` / `taskRecordSchema` / `emptyTaskRecord`（schema.ts）
2. `loadTaskRecord` / `writeTaskRecord`（records.ts）
3. `validateTaskDirName` / `isValidTaskDirName`（paths.ts）
4. `inferTaskPhase`（phase.ts）

**这里没有 create / start / finish / archive 任何一个生命周期动作。** 它只是「task.json 的读写器 + 目录名校验器 + 状态到阶段的投影函数」。

`packages/core/src/task/schema.ts:1-11` 的头注释把话说死了：

> The runtime Python writer is `.trellis/scripts/common/task_store.py` (`cmd_create`). The 24-field shape and field order below mirror that writer exactly so every TS and Python entry point produces structurally identical task.json files.

即：**TypeScript 侧是 Python 侧的镜像**，真正跑周期的是 Python。

#### task.json 的 24 个字段（`packages/core/src/task/schema.ts:13-38`）

```
id, name, title, description, status,
dev_type, scope, package, priority,
creator, assignee, createdAt, completedAt,
branch, base_branch, worktree_path, commit, pr_url,
subtasks, children, parent, relatedFiles, notes, meta
```

按周期链分组解读（此分组是我的解读，字段本身来自上文行号）：
- **身份/描述**：id, name, title, description
- **周期状态**：status, createdAt, completedAt —— 只有 3 个字段承载状态
- **分类**：dev_type, scope, package, priority
- **人**：creator, assignee
- **代码链路**：branch, base_branch, worktree_path, commit, pr_url —— 5 个字段把任务锚到 git
- **拆解**：subtasks, children, parent —— 父子树
- **附加**：relatedFiles, notes, meta

`packages/core/src/task/schema.ts:199-228` 的默认值：`status: "planning"`, `priority: "P2"`, `createdAt` 为当天日期。

#### 状态机只有 5 个值，且是**从 status 投影出来的**

`packages/core/src/task/phase.ts:3-26` 说得非常清楚：

> Phase is a projection of `TrellisTaskRecord.status` only. There is no separate `current_phase` field stored on disk — `inferTaskPhase` exists so consumers can render the workflow phase without depending on `.trellis/workflow.md` parsing.

映射（`packages/core/src/task/phase.ts:40-51`）：

| status | phase |
| --- | --- |
| `planning` | plan |
| `in_progress` | implement |
| `review` | review |
| `completed` / `done` | completed |
| 其他 | unknown |

**这是整个 Trellis 周期管理里最值钱的一条设计：磁盘上不存阶段，只存状态；阶段是纯函数投影。** 它避免了「状态与阶段两份真相打架」这个所有工作流系统的经典 bug。

但 `.trellis/workflow.md:120-133` 揭示了一个已知的破绽：`[workflow-state:completed]` 这个面包屑块**当前是死代码**——因为 `cmd_archive` 在同一次调用里既写 `status='completed'` 又把目录挪去 `archive/`，活动任务指针随即失效，hook 永远不会在 `completed` 状态上触发。注释里承认「block kept for a future explicit in_progress→completed transition」。也就是说，`review` 和 `completed` 两个 phase 在实际运行中基本没人走到，真实运行的只有 `plan` → `implement` 两个状态。

#### 任务目录命名（`packages/core/src/task/paths.ts:1-19`）

```
DATED:  ^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])-([a-z0-9]+(?:-[a-z0-9]+)*)$   → 05-13-trellis-core-sdk-package
SYSTEM: ^00-(bootstrap-guidelines|join-[a-z0-9-]+)$                            → 00-bootstrap-guidelines
```

注意 `MM-DD` 没有年份。跨年任务靠归档目录 `archive/{year-month}/` 分离（`.trellis/workflow.md:50`）。

#### CLI 对 core/task 的实际依赖：只有一个文件

实测 `grep -rn "@mindfoldhq/trellis-core" packages/cli/src`：core/task 只被 `packages/cli/src/utils/task-json.ts` 引用一次，而后者只是给 `init.ts` 和 `update.ts` 两处提供 `emptyTaskJson`（`packages/cli/src/utils/task-json.ts:11-18`，消费者见 `packages/cli/src/commands/init.ts:31` 与 `packages/cli/src/commands/update.ts:37`）。

**即：core/task 在 CLI 里只用于"init 时造两个 bootstrap 任务的骨架"。真正的日常周期操作全走 Python。**

### 2.4 mem —— 附加能力，服务「跨会话续工」

`packages/core/src/mem/index.ts:15-24` 的公共面只有 5 个函数：`listMemSessions` / `searchMemSessions` / `extractMemDialogue` / `readMemContext` / `listMemProjects`。

它读的是**各家 AI CLI 自己的历史会话文件**，不是 Trellis 的数据。适配器 6 个（`packages/core/src/mem/adapters/`）：claude、codex、grok、opencode、pi、zcode。类型定义 `packages/core/src/mem/types.ts:10-18`：

```ts
export type MemSourceKind = "claude" | "codex" | "grok" | "opencode" | "pi" | "zcode";
export type MemPhase = "brainstorm" | "implement" | "all";
```

技能层的定位（`packages/cli/src/templates/common/bundled-skills/trellis-session-insight/SKILL.md:3`）：触发词是「上次怎么解的」「之前讨论过吗」「how did we solve X last time」。SKILL.md 第 8 行明确自述：

> It is intentionally a **capability skill, not a workflow**. There is no fixed output file, no required write-back step, no "always run after finish-work" rule.

**判定：mem 是纯附加能力。** 它服务「跨会话续工」这一环，但方式是「事后搜历史对话」，而不是「事前写好交接」。Trellis 真正的跨会话续工靠的是另外三样东西（见 2.6）：`.trellis/workspace/journal-N.md`、task.json 的 status、以及 `/trellis:continue` 命令的状态路由表。

`packages/core/src/mem/internal/sqlite-readonly.ts:5` 有一条工程注记：`better-sqlite3` 被试用后回退了（原因该行未展开，未核实）——说明 mem 为了零 runtime 依赖付出了代价。

### 2.5 channel —— 最重的附加能力，多 agent 通信运行时

`packages/core/src/channel/index.ts` 全文 242 行导出，涵盖：

- **事件日志**：`ChannelEvent` 及 18 种事件类型（`create/message/thread/context/metadata/spawned/killed/done/error/progress/undeliverable/interrupt-requested/turn-started/turn-finished/interrupted/supervisor-warning` 等，见 `packages/core/src/channel/index.ts:36-62`），`appendEvent` / `readLastSeq`
- **worker 生命周期**：`WorkerState` / `WorkerLifecycle` / `reduceWorkerRegistry` / `spawnWorker` / `interruptWorker` / `probeWorkerRuntime` / `reconcileWorkerLiveness`（`:77-215`）
- **thread / forum**：`reduceThreads` / `postThread` / `renameThread` / `listForumThreads` / `showThread`（`:117-172`）
- **inbox 投递**：`readWorkerInbox` / `watchWorkerInbox` / `matchesInboxPolicy` / `classifyDelivery`（`:89-146`）
- **上下文注入**：`addChannelContext` / `addThreadContext` 等 6 个（`:153-160`）

CLI 侧对应 `trellis channel` 一整个命令族（第 3.1 节）。技能层定位（`packages/cli/src/templates/common/bundled-skills/trellis-channel/SKILL.md:3`）：「live multi-agent collaboration, spawned workers, cross-agent review, progress inspection, forum channels」。

配置里还有一层 OOM 防护（`.trellis/config.yaml:87-116`）：`idle_timeout: 5m`、`max_live_workers: 6`、上下文文件的路径 containment 检查与 `trusted_context_dirs` 白名单。

**判定：channel 是完整的第二个产品**——一个本地多 agent 消息总线 + 进程监管器。它和「项目周期管理」的唯一交点是「派 worker 去做 implement/check」，而这件事在 sub-agent 原生支持的平台上不需要它。`packages/core/src/channel/index.ts:1` 只写了一句 `// Public channel API surface.`，没有解释它为什么存在于一个「工程化框架」里。

### 2.6 周期管理必需 vs 附加 —— 汇总判定

| 组件 | 位置 | 周期链角色 | 判定 |
| --- | --- | --- | --- |
| `workflow.md` 三阶段 + `[workflow-state:*]` 面包屑 | `.trellis/workflow.md:144-261` | 周期状态机本体 | **必需，且是全系统核心** |
| `task.json` 24 字段 | `packages/core/src/task/schema.ts:13-38` | 周期状态存储 | **必需** |
| `inferTaskPhase` | `packages/core/src/task/phase.ts:33-52` | 状态→阶段投影 | **必需**（20 行代码） |
| `task.py` 17 个子命令 | `packages/cli/src/templates/trellis/scripts/task.py:637-764` | 周期动作执行者 | **必需** |
| `.trellis/spec/` + 注入 hook | `packages/cli/src/templates/shared-hooks/*.py` | 全周期上下文供给 | 必需（但可极大简化） |
| `.trellis/workspace/journal-N.md` | `.trellis/workflow.md:78-87` | 收尾/交接 + 跨会话 | 必需 |
| `/trellis:continue` 状态路由 | `packages/cli/src/templates/common/commands/continue.md:22-34` | 跨会话续工 | **必需，设计值得抄** |
| `core/mem` + `trellis mem` | `packages/core/src/mem/`（5357 行） | 事后翻历史对话 | **附加** |
| `core/channel` + `trellis channel` | `packages/core/src/channel/`（4544 行）+ CLI 3900 行 | 多 agent 通信 | **附加** |
| 22 平台 configurator | `packages/cli/src/configurators/`（22 个平台文件） | 分发 | **附加** |
| `ablate` / `restore` | `packages/cli/src/commands/ablate.ts`（500 行） | A/B 对比 | **附加** |
| 148 份 migration manifest | `packages/cli/src/migrations/manifests/` | 版本兼容 | **附加**（是「已发布产品」的代价） |

---

## 3. CLI

### 3.1 命令清单

顶层命令 10 个（`packages/cli/src/cli/index.ts:71-397`）：

| 命令 | 行号 | 作用 | 周期链位置 |
| --- | --- | --- | --- |
| `init` | `:71-154` | 在当前项目初始化 Trellis | **开工** |
| `update` | `:156-185` | 把 Trellis 配置/命令升到最新版 | 运维 |
| `upgrade` | `:187-211` | 升级全局 CLI 包本身 | 运维 |
| `uninstall` | `:213-236` | 永久移除全部 Trellis 文件 | 运维 |
| `ablate` | `:238-261` | 临时摘除（带外部恢复事务） | 运维 |
| `restore` | `:263-284` | 恢复 ablate 保存的状态 | 运维 |
| `mem` | `:286-310` | 跨平台会话历史检索（list/search/context/extract/projects） | 跨会话续工（附加） |
| `workflow` | `:312-354` | 列出/切换 `.trellis/workflow.md` 模板 | 周期定义本身 |
| `platforms` | `:356-395` | 显示本项目已配置的平台 | 诊断 |
| `channel` | `:397` | 多 agent 通信运行时（子命令族） | 附加 |

`channel` 子命令 16 个公开 + 2 个内部（`packages/cli/src/commands/channel/index.ts` 中的 `.command()`）：`create / send / wait / interrupt / spawn / run / rm / prune / list / messages / kill / post / forum / thread / rename / context(add|delete|list) / title(set|clear)`，内部两个是 `__supervisor`、`__parse-trace`。

**关键观察：CLI 顶层没有任何一个任务生命周期命令。** 没有 `trellis task create`、没有 `trellis start`、没有 `trellis finish`。这些全在 Python：

`.trellis/workflow.md:44-72` 列出 `task.py` 的用法，实测 `packages/cli/src/templates/trellis/scripts/task.py:637-764` 有 **17 个** `add_parser`：

```
lifecycle:  create, start, current, finish, archive, list, list-archive
context:    add-context, list-context, validate
metadata:   set-branch, set-base-branch, set-scope, set-meta
hierarchy:  add-subtask, remove-subtask
misc:       rename
```

⚠️ **文档漂移（本次实测发现）**：`.trellis/workflow.md:71` 和 `packages/cli/src/templates/trellis/workflow.md:73` 都写着 `task.py create-pr [name] [--dry-run]`，但 `task.py`（801 行，17 个 add_parser）里**没有 `create-pr` 子命令**。全仓 grep 只在归档任务的研究笔记与 copilot 老 prompt 里能命中该字符串。也就是说：**Trellis 自己发布的 workflow.md 里，写着一条不存在的命令。** 这条正是「PR 创建」——周期链最后一环。

另外 `.trellis/workflow.md:74` 自己也写了「Run `task.py --help` to see the authoritative, up-to-date list」——等于承认文档不是权威。

其他 Python 入口（`packages/cli/src/templates/trellis/scripts/`）：`init_developer.py`（身份）、`get_context.py`（上下文与阶段详情）、`get_developer.py`、`add_session.py`（57458 字节，journal 记录）。

### 3.2 `trellis init` 的交互项

`init` 的 CLI flag 共 34 个（`packages/cli/src/cli/index.ts:74-130`），其中 23 个是平台开关（`--cursor --claude --opencode --codex --kilo --kiro --gemini --antigravity --devin --windsurf(已废弃别名) --qoder --codebuddy --copilot --droid --dsh --pi --reasonix --zcode --omp --trae --grok --kimi --snow`），另有 `--with-statusline / -y / -u / -f / -s / --monorepo / --no-monorepo / -t / --overwrite / --append / -r / --workflow / --workflow-source`。

平台数与 README 的「22」对得上：`packages/cli/src/configurators/` 有 25 个文件，减去 `index.ts` / `shared.ts` / `workflow.ts` 恰为 22 个平台适配器；`--windsurf` 是 `--devin` 的废弃别名（`packages/cli/src/commands/init.ts:1112-1118`）。

**交互式（不带 `-y`）会遇到的提问，按实际出现顺序：**

| # | 提问 | 类型 | 行号 |
| --- | --- | --- | --- |
| 0 | *（已初始化时）*「Trellis is already initialized. What would you like to do?」→ Add AI platform(s) / Set up developer identity / Full re-initialize | list | `commands/init.ts:813-825` |
| 0a | *（上一步选 add-platform）*「Select platforms to add:」 | checkbox | `commands/init.ts:850-856` |
| 1 | 「Your name: 」（git config user.name 取不到时才问，必填、空则重问） | 文本 | `commands/init.ts:1213-1228` |
| 2 | 「Enable monorepo mode?」（检测到 workspace 时） | confirm | `commands/init.ts:1320-1326` |
| 2a | *（monorepo）*「Spec source for `<pkg>` (`<path>`):」→ From scratch / Download remote template | list（每个包问一次） | `commands/init.ts:1340-1350` |
| 2b | *（选 remote）*「Select template for `<pkg>`:」 | list | `commands/init.ts:1373-1379` |
| 3 | 「Select AI tools to configure:」（默认勾选 Cursor + Claude） | checkbox | `commands/init.ts:1450-1461` |
| 4 | 「Install the Trellis statusLine for Claude Code?」（未传 `--with-statusline` 且选了 Claude 时） | confirm | `commands/init.ts:985-1000` |
| 5 | *（单仓）*「Select a spec template:」（含「from scratch (default)」与「custom (enter a registry source)」） | list | `commands/init.ts:1580-1602` |
| 6 | 「Directory `.trellis/spec` already exists. What do you want to do?」→ Skip / Overwrite / Append（三处不同分支各有一次） | list | `commands/init.ts:1662-1678`、`:1722-1735`、`:1834-1845` |

**即：最少 1 问（只问名字），最多 ~8 问。** `-y` 时全部跳过，默认装 Cursor + Claude（`commands/init.ts:1445-1447`），写模式退化为 skip（`commands/init.ts:1152-1157`）。

**`init` 实际写盘的东西**（`packages/cli/src/configurators/workflow.ts:125-195`）：

1. `.trellis/` 根目录
2. `.trellis/scripts/`（整目录拷贝，可执行位；**11514 行 Python**）
3. `.trellis/workflow.md`（native 或 marketplace 变体，替换 `{{PYTHON_CMD}}` 字面量）
4. `.trellis/.gitignore`
5. `.trellis/config.yaml`
6. 项目根 `.gitattributes` 追加 journal 的 `merge=union` 规则（additive，不覆盖）
7. `.trellis/agents/`（channel runtime agent 定义，**无论选了什么 workflow 都写**，理由见 `configurators/workflow.ts:165-171`）
8. `.trellis/workspace/index.md`
9. `.trellis/tasks/`
10. `.trellis/spec/` 模板（按项目类型 backend/frontend/guides）
11. 各平台目录（`.claude/`、`.cursor/` …）
12. `.trellis/.version` 与 `.trellis/.template-hashes.json`（哈希追踪，本仓库 228 条）

再加两个 bootstrap 任务：首次 init 建 `00-bootstrap-guidelines`（`commands/init.ts:602-621`），克隆者首次 init 建 `00-join-<name>`（`commands/init.ts:760-774`），三分支派发逻辑在 `commands/init.ts:2009-2048`。

`init` 还有一个 guard：拒绝在 `$HOME` 运行（`commands/init.ts:1104-1110`），理由是会把各平台的会话历史扫进哈希清单，之后 `uninstall` 会连带删掉。

### 3.3 migrations —— 版本演进频率

`packages/cli/src/migrations/manifests/` 下 **148 个 JSON**，覆盖 `0.1.9` → `0.7.0-beta.3`。

按 minor 分布（实测）：

| minor | manifest 数 |
| --- | --- |
| 0.1 | 1 |
| 0.2 | 5 |
| 0.3 | 35 |
| 0.4 | 13 |
| 0.5 | **48** |
| 0.6 | 42 |
| 0.7 | 4 |

稳定版 55 个，预发布（beta/rc）93 个。单个 minor 的 beta 链最长到 `0.6.0-beta.23`（24 个 beta）与 `0.5.0-beta.19` + `0.5.0-rc.7`（28 个预发布）。

迁移条目总数（跨全部 manifest 累计）：**395 条**，类型分布 `safe-file-delete: 192`、`rename: 181`、`rename-dir: 21`、`delete: 1`。标 `"breaking": true` 的版本 **6 个**。

**频率解读**：`.trellis/tasks/archive/` 的月份目录从 `2026-01` 到 `2026-08`（今天是 2026-09-10），即约 8-9 个月内发了 148 个带迁移清单的版本 —— **平均每月 ~17 个版本，每两天一发**。同期归档任务 231 个、活跃任务 11 个，`.trellis/tasks/` 下累计 **1361 个文件**。

`0.7.0-beta.*` 的 manifest（4 个）已存在于 `0.6.16` 的包里，说明 0.7 beta 线与 0.6 稳定线并行维护；`packages/cli/src/migrations/manifests/0.7.0-beta.3.json` 的 description 直接写「Sync release: the 0.7 beta line picks up v0.6.14」。

`migrations/index.ts:75-101` 的机制本身很简单：按 semver 排序，取 `(fromVersion, toVersion]` 区间内所有 manifest 的 migrations 拼起来。复杂度不在代码，在 148 份人工维护的清单。

**对自建 harness 的启示（解读）**：148 份迁移清单是「把模板文件发到别人仓库里」这个分发模型的必然代价——你改一个模板文件名，就得给所有已安装用户写一条 rename 迁移，还得做 hash 校验区分「用户改过的」和「原版的」。如果 harness 只服务自己一个人/一个团队，这整套机器可以省掉。

---

## 4. 依赖清单与运行时

### 4.1 runtime 依赖数量

`packages/cli/package.json:54-63` —— **8 条 dependencies，其中 7 个外部**：

| 包 | 版本 | 用途（解读） |
| --- | --- | --- |
| `@mindfoldhq/trellis-core` | `workspace:*` | 内部包 |
| `chalk` | `^5.3.0` | 终端着色 |
| `commander` | `^12.1.0` | CLI 框架 |
| `figlet` | `^1.9.4` | init 的 ASCII banner（`commands/init.ts:1130`） |
| `giget` | `^3.1.1` | 从 GitHub 拉远程 spec/workflow 模板 |
| `inquirer` | `^9.3.7` | 交互式提问 |
| `undici` | `^6.21.0` | HTTP（代理支持，`commands/init.ts:1139`） |
| `zod` | `^4.4.2` | schema 校验 |

`packages/core/package.json:63-70` —— **runtime 依赖 0 条**，只有 6 个 devDependencies（eslint / typescript / vitest / @types/node 等）。core 是零依赖包，`"sideEffects": false`。

**总计外部 runtime 依赖 7 个**，都是 CLI 层的。这个数字很克制。

### 4.2 是否需要 python3 与 node 双运行时 —— 是，两个都硬性

- `README.md:49-52`：Node.js >= 18，Python >= 3.9
- `packages/cli/package.json:77-79` / `packages/core/package.json:71-73`：`"engines": { "node": ">=18.17.0" }`
- Python 是**硬失败**：`packages/cli/src/commands/init.ts:147-157`

  ```ts
  if (!versionOutput) {
    throw new Error(`Python command "${command}" not found. Trellis init requires Python ≥ 3.9.`);
  }
  if (!isSupportedPythonVersion(versionOutput)) {
    throw new Error(`${versionOutput} detected via "${command}", but Trellis init requires Python ≥ 3.9.`);
  }
  ```

  `init()` 在流程早期就调 `resolveSupportedPython()`（`commands/init.ts:1181`），探测顺序 Windows 是 `python / python3 / py -3`，其他平台 `python3 / python`（`commands/init.ts:174-177`）。两个逃生阀：`TRELLIS_PYTHON_CMD`（显式指定）与 `TRELLIS_SKIP_PYTHON_CHECK=1`（跳过探测）。沙箱里 spawn 被 EPERM/EACCES 拒绝时降级为警告继续（`commands/init.ts:135-145`）。

**Python 侧的体量（实测）：**
- 装进项目的 `.trellis/scripts/`：**11514 行**，28 个文件。其中 `common/task_store.py` 73008 字节、`add_session.py` 57458 字节、`common/cli_adapter.py` 33397 字节、`common/active_task.py` 31978 字节、`task.py` 31810 字节。
- 平台 hook（`packages/cli/src/templates/shared-hooks/`）：4 个 Python 文件共 **2941 行** —— `session-start.py` 949、`inject-subagent-context.py` 1212、`inject-workflow-state.py` 488、`inject-shell-session-context.py` 292。
- 模板目录下 Python 总计 **16531 行**。

**职责切分（本次读到的事实）**：Node/TS 负责**安装、升级、迁移、多 agent 通信、历史检索**；Python 负责**日常周期动作**（任务增删改查、活动任务指针、上下文注入、journal 记录、git 提交）。选 Python 的原因文件里未说明（未核实），但从 hook 需要被 22 个不同平台的 hook 机制以 `python3 xxx.py` 形式直接调起来看，是为了避免每个用户项目里都要有 node_modules（解读）。

### 4.3 pnpm workspace 结构

`pnpm-workspace.yaml`（全文 2 行）：

```yaml
packages:
  - "packages/*"
```

即 2 个包：`packages/core`（`@mindfoldhq/trellis-core`）与 `packages/cli`（`@mindfoldhq/trellis`，bin 为 `trellis` 和 `tl`，见 `packages/cli/package.json:8-11`）。

根 `package.json:2-3`：`"private": true`，`"packageManager": "pnpm@10.32.1"`。构建有严格顺序：`package.json:6` `build` = 先 core 后 cli。

另有 2 个 git submodule（`.gitmodules`），**都不在 workspace 里**：
- `docs-site` → `https://github.com/mindfold-ai/docs.git`
- `marketplace` → `https://github.com/mindfold-ai/marketplace.git`

本地这两个目录是空的（未 init submodule），所以文档站与 workflow marketplace 的内容本次**未核实**。

CLI 的 lint 是双语言的：`packages/cli/package.json:29-30` 有 `lint:py: basedpyright` 与 `lint:all`；根有 `pyrightconfig.json`。

发布链：`.github/workflows/publish.yml`（未细读）、`packages/cli/package.json:31` 的 `prepublishOnly` 会把根的 README.md 与 LICENSE 拷进包。core 开了 npm provenance（`packages/core/package.json:40-43`）。

### 4.4 「轻」的量化基线（给 owner 做对比用）

| 维度 | Trellis 实测值 | 出处 |
| --- | --- | --- |
| npm 外部 runtime 依赖 | 7 | `packages/cli/package.json:54-63` |
| TS 源码（cli） | 26841 行 | `find packages/cli/src -name '*.ts' \| xargs wc -l` |
| TS 源码（core） | 10473 行 | `find packages/core/src -name '*.ts' \| xargs wc -l` |
| Python（装进用户项目） | 11514 行 / 28 文件 | `.trellis/scripts/` |
| 模板文件总数 | 226 | `packages/cli/src/templates/` |
| init 后受哈希追踪的文件 | 228 | `.trellis/.template-hashes.json` |
| 迁移清单 | 148 份 / 395 条 | `packages/cli/src/migrations/manifests/` |
| 支持平台 | 22 | `packages/cli/src/configurators/`（25 - 3 非平台文件） |
| 自举产生的任务文件 | 1361 | `.trellis/tasks/` |

---

## 5. License：AGPL-3.0 对三种行为分别意味着什么

**先声明**：以下「License 文本说了什么」部分逐条给行号；「这对你意味着什么」部分标注为**我的解读**，不是法律意见。owner 若要在商业产品里用，应找律师核。

### 5.1 授权事实

- `LICENSE:1-2`：GNU AFFERO GENERAL PUBLIC LICENSE Version 3, 19 November 2007（标准 AGPL-3.0 全文，235 行）
- `COPYRIGHT:1-2`：`Trellis - All-in-one AI framework & toolkit for Claude Code & Cursor / Copyright (C) 2026 Mindfold LLC`
- `COPYRIGHT:4-7`：`either version 3 of the License, or (at your option) any later version` —— 是 **AGPL-3.0-or-later**
- 但两个 package.json 都声明 `"license": "AGPL-3.0-only"`（`packages/cli/package.json:53`、`packages/core/package.json:62`）—— **与 COPYRIGHT 的 "or later" 冲突**。这是一处真实的元数据不一致（本次实测）。

### 5.2 License 文本里的关键定义

| 概念 | 文本 | 行号 |
| --- | --- | --- |
| "modify" | 「copy from or adapt all or part of the work in a fashion requiring copyright permission, other than the making of an exact copy」 | `LICENSE:36` |
| "covered work" | 「either the unmodified Program or a work based on the Program」 | `LICENSE:38` |
| "convey" | 「any kind of propagation that enables other parties to make or receive copies. **Mere interaction with a user through a computer network, with no transfer of a copy, is not conveying.**」 | `LICENSE:42` |
| 私用无义务 | 「You may make, run and propagate covered works **that you do not convey, without conditions** so long as your license otherwise remains in force.」 | `LICENSE:61` |
| 改后分发的四个条件 | a) 标注你改过并给日期；b) 标注按本 License 发布；c) **整个作品作为一个整体必须按本 License 授权给任何拿到副本的人**；d) 交互界面显示法律声明 | `LICENSE:77-85` |
| 聚合例外 | 「A compilation of a covered work with other separate and independent works, **which are not by their nature extensions of the covered work, and which are not combined with it such as to form a larger program** … is called an "aggregate" … does not cause this License to apply to the other parts」 | `LICENSE:88` |
| 网络条款（AGPL 特有） | 「if you modify the Program, your modified version **must prominently offer all users interacting with it remotely through a computer network** … an opportunity to receive the Corresponding Source of your version … at no charge」 | `LICENSE:188` |

### 5.3 三种行为逐个分析

#### (A) 「参考其设计自建」—— 风险最低

**文本依据**：AGPL 的义务全部挂在「covered work」上（`LICENSE:38`），而「covered work」的前提是 "modify" 的定义 —— 「copy from or adapt all or part of the work **in a fashion requiring copyright permission**」（`LICENSE:36`）。

**我的解读**：版权保护表达，不保护思想、方法、系统。读了 Trellis 的 workflow.md 之后，自己想明白「阶段应该从 status 投影出来」「入口文件只做路由」「面包屑每轮注入」这些**机制**，然后用自己的词、自己的文件结构、自己的代码重写一遍 —— 产物不是 covered work，AGPL 管不着。

**实操边界（我的解读，也是自查清单）**：
- 安全：抄机制、抄阶段划分逻辑、抄「status 只有 planning/in_progress 两个真实值」这类结论。
- 危险：把 `workflow.md` 的段落顺序、小标题、示例句子照搬后改几个词 —— 这是「adapt」，落在 `LICENSE:36` 的定义里。
- 建议做法：**先读，再合上文件，隔一段时间用自己的话重写**；不要开着 Trellis 的文件对照着写。

#### (B) 「复制其 markdown 模板」—— 是 covered work，义务取决于你是否 convey

**文本依据**：markdown 模板（`packages/cli/src/templates/markdown/`、`templates/common/skills/*.md`、`templates/trellis/workflow.md`）与代码在同一个 LICENSE 覆盖范围内（`COPYRIGHT:1-7` 覆盖整个 program，README/LICENSE 未对文档做任何单独豁免 —— 本次通读 README.md、README_CN.md、COPYRIGHT、LICENSE 均未发现「文档/模板另行授权」的条款）。

复制并修改 = "modify"（`LICENSE:36`），产物 = covered work（`LICENSE:38`）。

**分两种情况（我的解读）：**

1. **只在自己/自己公司内部用，不给外部任何人副本** —— `LICENSE:61` 明文：「You may make, run and propagate covered works **that you do not convey, without conditions**」。**没有任何义务**，不用开源，不用标注。`LICENSE:61` 后半句还允许你雇人替你改，只要他们「exclusively on your behalf, under your direction and control」且不能对外散副本。
2. **一旦分发（开源发布、给客户、放进公开仓库、发 npm）** —— `LICENSE:77-85` 的四条全部生效，其中 (c) 是杀手：「You must license **the entire work, as a whole**, under this License」。即你的整个 harness 都得 AGPL-3.0。

**「aggregate 例外」能不能救**（`LICENSE:88`）：例外只适用于「by their nature **not** extensions of the covered work」且「not combined with it such as to form a larger program」的独立作品。一个把 Trellis 的 `brainstorm.md` 改吧改吧当成自己 harness 的核心 skill 的项目，**本质上就是 extension**，我的解读是套不上这条例外。

**AGPL 网络条款对模板的影响**（`LICENSE:188`）：条款说的是「if you modify the Program, your modified version must prominently offer all users interacting with it **remotely through a computer network**」。一个跑在本地终端的 harness，用户不是「remotely through a computer network」交互的，`LICENSE:188` 的括号「(if your version supports such interaction)」正是为这种情况留的。**我的解读**：纯本地 CLI/skill harness 不触发 §13；但如果哪天把它做成 SaaS / Web 服务给别人用，§13 就生效，必须提供完整源码下载。

#### (C) 「复制其脚本」—— 与 (B) 同法，但风险更高

`.trellis/scripts/*.py`（11514 行）、`packages/cli/src/templates/shared-hooks/*.py`（2941 行）都是 covered work。法律结论与 (B) 完全相同：**内部用无义务，一分发就整体 AGPL**。

风险更高的原因（我的解读）：
1. 代码比文档更容易被逐行比对认定为复制（有变量名、函数名、注释、代码结构等强特征）。
2. Python 脚本会被原样 commit 进你的仓库并推上去。如果你的仓库是公开的，那就是 **convey**（`LICENSE:42`：「any kind of propagation that enables other parties to make or receive copies」），触发 §5 的全部四条。
3. 这些脚本互相耦合（`task.py` 依赖 `common/` 下 21 个模块，共 11514 行），不存在「只抄一小段」的选项。

**给 owner 的三行结论（我的解读）**：
1. 想商业化或想 MIT/Apache 发布自己的 harness → **一行 Trellis 的文件都别复制**，只读设计、合上文件重写。
2. 只给自己和团队内部用，永不对外分发 → `LICENSE:61` 兜底，抄什么都没有义务；但一旦哪天想开源，历史 commit 里的 AGPL 代码就是定时炸弹。
3. 无论走哪条路，**现在就在自建 harness 的仓库里记一笔「本项目未复制 Trellis 任何文件，仅参考公开设计」**，比事后自证清白便宜。

---

## 6. drafts/ 在酝酿什么方向

### 6.1 目录实况：不是「草稿箱」，是发布稿

`drafts/` 只有 **2 个文件**，且都是**同一个版本的论坛发帖稿**：
- `drafts/v0.5.0-beta-forum-post.md`（129 行，11 节）
- `drafts/v0.5.0-forum-post.md`（127 行，13 节）

**没有任何未来功能的设计草稿。** 焦点问题「drafts 里在酝酿什么方向」的直接答案是：这个目录里没有酝酿中的方向，只有已发版本的宣发文案。真正的「未来方向」线索得从 `migrations/manifests/0.7.0-beta.*.json` 里读（见 6.3）。

### 6.2 v0.5.0 发帖稿的章节（只读标题与首段）

`drafts/v0.5.0-forum-post.md` 的 13 节标题：

| # | 标题 | 周期链相关 |
| --- | --- | --- |
| 1 | `/start` 不再是必需入口（`:15`） | **开工**：自然语言直接进流程 |
| 2 | Skill-first 架构（`:21`） | 全周期：5 个命令转成 auto-triggered skill |
| 3 | workflow.md 是工作流唯一的源（`:29`） | **周期定义的 SoT 收敛** |
| 4 | `/trellis:continue` 命令：单任务内的 continue，消除工作流学习成本（`:37`） | **跨会话续工** |
| 5 | 多窗口并行不再互相覆盖（`:54`） | 并发安全 |
| 6 | Joiner onboarding：新开发者克隆项目自动生成入门任务（`:60`） | **交接** |
| 7 | 7 个平台升级到 agent-capable（`:68`） | 分发 |
| 8 | Sub-agent 上下文注入（`:78`） | 实现/验证 |
| 9 | 每轮工作流面包屑（`:84`） | **周期状态机的执行机制** |
| 10 | SessionStart payload 重构（`:90`） | 开工 |
| 11 | 迁移与升级流程改进（`:96`） | 运维 |
| 12 | 大规模清理（138 条 safe-file-delete）（`:107`） | 减重 |
| 13 | Codex 用户须知（`:116`） | 平台特定 |

beta 版发帖稿多出一节 roadmap（`drafts/v0.5.0-beta-forum-post.md:127-129`），**全文只有两条**：

> ## 11. 后续 roadmap
> - 加强 brainstorm 的规划，提问能力
> - 对 tdd 流程提供可选模板

两条都落地了：tdd 模板见 `packages/cli/src/cli/index.ts:125`（`--workflow` 的示例值含 `tdd`）；brainstorm 的强化见 `templates/common/skills/brainstorm.md:1-20` 里新增的「Non-Negotiable Planning Contract」与「Non-Negotiable Evidence Rule」两节。

### 6.3 方向判断：**表面变轻，实质变重，且加速变重**

**变轻的证据**（都在 v0.5.0，`drafts/v0.5.0-forum-post.md:107-114`）：

> 这版本移除了四类"已有更好替代"的老功能：
> - **iFlow 平台** —— CLI 已不再维护
> - **Multi-agent pipeline**（`scripts/multi_agent/` + `worktree.yaml`）—— 主流 agent CLI/IDE 都有原生 worktree 支持了
> - **Ralph Loop hook**（`ralph-loop.py`）—— SubagentStop + exit-code-2 跨平台不可移植；check sub-agent 自己的修复循环已经够用
> - **6 个命令 + 3 个 sub-agent** —— `parallel` / `onboard` / `create-command` / `integrate-skill` / `check-cross-layer` / `record-session`；`dispatch` / `debug` / `plan` agent（被 skill routing 取代）

138 条 safe-file-delete，命令从 8 个砍到 3 个（`start` / `continue` / `finish-work`，见 `packages/cli/src/templates/common/commands/`），其余转成 5 个 auto-triggered skill（`packages/cli/src/templates/common/skills/`：before-dev / brainstorm / break-loop / check / update-spec）。

**但同一份发帖稿里，"变重"的证据同样清晰**（`drafts/v0.5.0-beta-forum-post.md:118-123`）：

> - SessionStart payload 从 2.7 KB 增至 9.5 KB，把 Phase 1/2/3 step body 内联进去
> - task.py 命令表从 5 条扩到 16 条（lifecycle / context / metadata / hierarchy / PR 分组）

**即：v0.5.0 是"把命令换成 skill，把显式操作换成隐式注入"——用户看到的入口变少了（8→3），系统实际做的事变多了（payload 3.5x，task.py 命令 3.2x）。这不是减重，是把重量从用户界面挪到运行时。**

**0.6 之后是明确的加法**（本次实测，非 drafts 内容）：
- `core/channel` 4544 行 + CLI channel 命令族 ~3900 行 = 一整套多 agent 通信运行时。讽刺的是 v0.5.0 刚以「主流 agent CLI 都有原生 worktree」为由删掉了 multi-agent pipeline（`drafts/v0.5.0-forum-post.md:112`），0.6 又造了个更大的回来。
- `core/mem` 5357 行 + `trellis mem` 520 行 = 跨会话记忆检索层，6 个平台适配器。
- `ablate` / `restore` 500 行 = 「把自己临时摘掉」。
- `0.6.16` 新增 `task.py rename`、`task.py start` 的空 jsonl 拦截（`migrations/manifests/0.6.16.json` changelog）。

**0.7 的方向（从 manifest 读，唯一可得的前瞻信息）** —— `packages/cli/src/migrations/manifests/0.7.0-beta.0.json`：

> "description": "Path-scoped dynamic spec loading for Claude Code and Codex, plus **layered workflow selection per task, developer, and team**."
> "changelog": "feat(hooks): deliver path-scoped specs dynamically through Claude Code PostToolUse and Codex PreToolUse hooks … feat(workflow): save workflow variants and resolve **task, developer, team, and global** selections through one runtime chain"

**这是最重的一步**：workflow 从「一个项目一份 workflow.md」变成「task / developer / team / global 四层解析链」。任何做过配置系统的人都知道四层继承链意味着什么。

**综合判定（我的解读）**：Trellis 的走向是**变重**，且重量正在从「周期管理」外溢到「多 agent 编排 + 记忆检索 + 分层配置」三个新战场。v0.5.0 的「减重」只是命令面的一次性整理，之后每个 minor 都在净增能力。对 owner 的直接含义：**如果目标是「比 Trellis 轻的项目级 harness」，参照物应该锁定 v0.5.0 那次减重后的形态（3 命令 + 5 skill + workflow.md + task.py），而不是当前的 0.6.16。**

---

## 7. 对「自建轻量项目周期 harness」的可复用清单

（本节全部是**我的解读与建议**，每条给出所依据的 Trellis 事实与行号。）

### 7.1 值得抄的设计（4 条）

1. **阶段不落盘，从状态投影**（`packages/core/src/task/phase.ts:3-26`）
   磁盘上只有 `status`，phase 是纯函数 `inferTaskPhase(status)`。20 行代码消灭一整类「两份真相打架」的 bug。而且实测 Trellis 自己只有 `planning` / `in_progress` 两个状态真正被走到（`review` / `completed` 都因 archive 的原子操作而成为死路，见 `.trellis/workflow.md:120-133`）——**说明两个状态就够了**。

2. **入口文件只做路由，不装内容**（`AGENTS.md:1-21`，21 行）
   AGENTS.md 只说「知识在 `.trellis/` 下，四个入口分别是什么」。配上 `<!-- TRELLIS:START/END -->` 受管块标记，用户在块外的编辑被保留。这是 FAQ 第 1 条自称的核心差异化（`README.md:102`：那些文件「容易变成单体巨石」），也确实成立。

3. **`/continue` 的状态路由表**（`packages/cli/src/templates/common/commands/continue.md:22-34`）
   这是整个 Trellis 里我认为最值得直接抄的一段。它是一张「(status, 产物存在性) → 下一步」的查表：

   ```
   status=planning + 无 prd.md                    → 1.1（进 brainstorm）
   status=planning + 只有 prd.md                  → 判轻/重；轻→1.4 评审，重→回 1.1 补 design.md + implement.md
   status=planning + 重任务产物齐 + jsonl 未策展   → 1.3
   status=planning + 产物齐 + jsonl 已策展         → 1.4（请求评审，用户确认后才 task.py start）
   status=in_progress + 未开始实现                 → 2.1
   status=in_progress + 实现完未检查               → 2.2
   status=in_progress + 检查通过                   → 3.3（spec 更新）→ 3.4（提交）
   ```

   **跨会话续工的本质就是这张表**：新会话不需要读历史对话，只需要读「status + 哪些文件存在」就能算出该干什么。这比 mem 那 5357 行的历史检索便宜几个数量级，且更可靠。

4. **「任务创建同意 ≠ 实现同意」的双闸门**（`.trellis/workflow.md:156` / `:293`）
   > Task creation approval is not implementation approval; implementation waits for `task.py start` after artifact review.

   `.trellis/workflow.md:326` 还特意说明：Phase 1.0 只跑 `create` 不跑 `start`，因为 `start` 会翻转面包屑到实现阶段，导致规划产物还没评审就开跑。这是一个用真实故障换来的设计（`.trellis/workflow.md:113-118` 的注释承认「Phase 1 planning gate skip 和 Phase 3.4 commit skip 都是从这个缺口冒出来的」）。

   与 owner CLAUDE.md 的「Brainstorm 先于代码」是同一条原则的不同实现。

### 7.2 值得抄的机制，但要简化（2 条）

5. **每轮面包屑（per-turn breadcrumb）**（`.trellis/workflow.md:99-142`）
   机制：`workflow.md` 里嵌 `[workflow-state:STATUS] … [/workflow-state:STATUS]` 块，UserPromptSubmit hook 按当前 status 取对应块注入。`.trellis/workflow.md:105-107` 强调「hook 只解析这些块，v0.5.0-rc.0 之后脚本里没有 fallback 字典」——单一真相源。

   注释里还写了一条不变量（`.trellis/workflow.md:113-118`）：**每个标 `[required · once]` 的步骤，必须在对应 phase 的面包屑块里有一条强制行**，并有回归测试保障。理由：「面包屑是唯一的每轮通道；一个必做步骤如果没在那儿被提到，AI 就会静默跳过」。

   这条不变量是真知识，值得抄。但 Trellis 的实现（488 行 `inject-workflow-state.py` + Markdown 里的自定义标记语法 + 每平台一套 hook 配置）过重，自建可以用更简单的载体。

6. **spec 的 hash 追踪与「用户改过就保留」**（`.trellis/.template-hashes.json` 228 条 + `drafts/v0.5.0-beta-forum-post.md:116`：「所有清理都 hash 校验：本地改过的文件就保留 + 警告」）
   这是「把模板发到别人仓库」这个模型的必要配套。**如果 harness 只服务自己，这整套可以不要** —— 你的模板就是你的文件，不存在「上游更新覆盖本地修改」的问题。

### 7.3 明确不要抄的（4 条）

7. **多运行时**（Node + Python 双硬依赖，`README.md:49-52` / `packages/cli/src/commands/init.ts:147-157`）。Trellis 有 22 平台适配的历史包袱才需要 Python 做 hook 载体；自建 harness 单一平台，用一门语言，甚至纯 shell + markdown。

8. **channel（4544 + 3900 行）**。它解决的是「本地多 agent 通过持久事件日志协作」，与项目周期链只在「派 worker 干活」一点相交，而这点在有原生 sub-agent 的平台上不需要。Trellis 自己在 v0.5.0 刚以「原生支持够用了」为由删过一次同类东西（`drafts/v0.5.0-forum-post.md:112`）。

9. **mem（5357 行 + 6 个平台适配器）**。「上次怎么解的」这个需求，用 7.1 第 3 条的状态路由表 + journal 文件覆盖 80%；剩下 20% 值不值 5357 行代码和 6 个会随上游格式变化而腐烂的适配器，是个明确的取舍题。适配器腐烂已经在发生：`bundled-skills/trellis-session-insight/SKILL.md:13` 承认「OpenCode logs are not yet indexable (provider adapter pending)」。

10. **迁移清单机器**（148 份 manifest / 395 条迁移 / 6 个 breaking）。这是「产品化分发」的成本，不是「周期管理」的成本。自建 harness 若不对外发布，成本为零。

### 7.4 Trellis 自身暴露的三个坑（自建时避开）

11. **文档与实现漂移**：`workflow.md:71` 写着不存在的 `task.py create-pr`（第 3.1 节实测）。而 workflow.md 是**每个会话都被注入给 AI 的文件** —— AI 会照着它去跑一条不存在的命令。**教训：周期文档如果是要喂给 AI 的，就必须有测试保证它描述的每条命令真实存在。** Trellis 自己也意识到了，`.trellis/workflow.md:74` 加了「以 `--help` 为准」的免责声明，但那是止痛药不是药。

12. **状态机有死分支**：`review` 和 `completed` 两个 phase 在正常流程里走不到（`.trellis/workflow.md:120-133` 的注释自述 `[workflow-state:completed]` 是 DEAD）。原因是 archive 把「翻转状态」和「移动目录」做成了一次原子操作。**教训：状态转移和数据搬迁不要在同一个动作里做。**

13. **元数据不一致**：`COPYRIGHT:4-7` 说 AGPL-3.0-**or-later**，两个 package.json 说 `AGPL-3.0-**only**`（第 5.1 节）。对使用者而言这是真实的法律不确定性。

---

## 8. 未核实 / 读不到的部分

| 项 | 原因 |
| --- | --- |
| `docs-site/` 与 `marketplace/` 的内容 | 是 git submodule 且未 init，本地目录为空（`.gitmodules`） |
| 官方文档站 `docs.trytrellis.app` 的内容 | 本任务为只读本地研究，未联网 |
| 版本发布的真实日期与节奏 | git 是 shallow clone，只有一个 commit，无历史时间戳。第 3.3 节的「每两天一发」是用 `.trellis/tasks/archive/` 的月份目录范围（2026-01 ~ 2026-08）反推的**估算** |
| `add_session.py`（57KB）与 `task_store.py`（73KB）的内部逻辑 | 本次只读了 `task.py` 的 argparse 结构与 workflow.md 的行为描述，未逐行读实现 |
| `.github/workflows/publish.yml` 的发布流程 | 未读 |
| `packages/cli/src/commands/update.ts`（2924 行）的冲突处理细节 | 只读了 CLI 层的选项定义（`cli/index.ts:156-185`） |
| `better-sqlite3` 被回退的具体原因 | `packages/core/src/mem/internal/sqlite-readonly.ts:5` 只提到「tried and reverted」，未读全文 |
| 22 个平台各自的 configurator 差异 | 只统计了文件数，未逐个读 |
