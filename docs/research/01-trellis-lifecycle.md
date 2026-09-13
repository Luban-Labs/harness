# Trellis 项目周期模型本体解剖

> 只读研究报告。焦点:开工 → 需求澄清 → 拆任务 → 实现 → 验证/审查 → 收尾/交接 → 跨会话续工。
> 与周期无关的内容(平台适配细节、CLI 发布、UI/营销)一律不展开。

## 0. 溯源基准

- 克隆根:`/private/tmp/claude-501/-Users-sangba-Downloads-02-----------harness/c38a95e8-724a-458f-a564-59ac3a323ca8/scratchpad/trellis`
- HEAD:`88f4834449da9b4f607ec05e322408a0aa66f2ce`,`Thu Aug 27 15:29:28 2026 +0800`,commit message `0.6.16`
- `.trellis/.version` 内容为 `0.6.14`(与 HEAD 的 `0.6.16` 不一致,未核实是否为发版流程的正常滞后)
- 本报告所有路径均相对上述克隆根。行号来自本次实际 `cat -n` / `sed -n` 读取。
- 实际读过的文件清单见文末「附录 A」。

一句话定位:**Trellis 的周期模型 = 一份被 hook 逐回合朗读的 Markdown 状态机(`.trellis/workflow.md`)+ 一个以「任务目录」为单位的磁盘状态机(`.trellis/tasks/`)+ 一个 Python CLI 作为唯一合法状态写者(`.trellis/scripts/task.py`)。** 三者之外没有数据库、没有守护进程。

---

## 1. 周期分几个阶段:入口条件 / 产出物 / 退出条件

`workflow.md:146-150` 给出的相位索引只有三段:

```
Phase 1: Plan    → classify, get task-creation consent, then write planning artifacts
Phase 2: Execute → implement only after task status is in_progress
Phase 3: Finish  → verify, update spec, commit, and wrap up
```

但真实的周期是「**Phase 0 分诊(Request Triage)+ 三个 Phase + 一个不在 Phase 编号内的收尾命令 `/trellis:finish-work`**」。逐条列。

### 1.0 Request Triage(`workflow.md:152-156`)

| 维度 | 内容 | 出处 |
|---|---|---|
| 入口 | 无活动任务(会话指针解析不到 task) | `workflow.md:176-180`(`[workflow-state:no_task]` 每回合注入) |
| 动作 | 先对本轮请求分类:简单对话/小任务 → 只问「这轮要不要建 Trellis 任务」;复杂任务 → 问「能否建任务并进入 planning」 | `workflow.md:154-155` |
| 硬规则 | 用户拒绝时,复杂任务**不得**做宽泛的内联实现,只能解释、澄清范围或建议拆小 | `workflow.md:155` |
| 关键区分 | 「同意建任务」≠「同意开始实现」 | `workflow.md:156`、`workflow.md:293` |
| 产出物 | 无文件产出,只是一个授权门 | — |
| 退出 | 用户同意建任务 → 进 1.0;拒绝 → 本会话跳过 Trellis | `workflow.md:154` |

SessionStart 侧有同构的一份(`.claude/hooks/session-start.py:428-434`,`Status: NO ACTIVE TASK` + `Next-Action: Classify the current turn before creating any Trellis task.`)。

### 1.1 Phase 1: Plan(`workflow.md:182-188`,详解 `workflow.md:308-465`)

五个步骤,标注了 required/optional 与 once/repeatable:

| 步骤 | 标签 | 入口条件 | 产出物 | 退出条件 |
|---|---|---|---|---|
| 1.0 Create task | `[required · once]` | 已拿到建任务许可;`task.py current --source` 尚未指向任务(`workflow.md:328`) | 任务目录 `.trellis/tasks/MM-DD-slug/` + `task.json`(status=`planning`)+ 默认 `prd.md` + 空的 `implement.jsonl`/`check.jsonl` | 命令成功,breadcrumb 自动切到 `[workflow-state:planning]`(`workflow.md:324`)。**明令只跑 `create` 不跑 `start`**(`workflow.md:326`) |
| 1.1 Requirement exploration | `[required · repeatable]` | 任务已创建 | `prd.md`(需求/约束/验收标准);复杂任务另加 `design.md` + `implement.md` | 无用户方待决项;需求变更时随时回到本步(`workflow.md:350`) |
| 1.2 Research | `[optional · repeatable]` | 任何时刻 | `{TASK_DIR}/research/<topic>.md`,一主题一文件(`workflow.md:373`) | 「研究产出必须落文件,不能只留在对话里 —— 对话会被压缩,文件不会」(`workflow.md:379`) |
| 1.3 Configure context | `[required · once]`,仅 sub-agent 平台 | 有 `implement.jsonl`/`check.jsonl` | 两个 jsonl 各至少一条真实 `{"file":..., "reason":...}` | Ready gate:两个文件都要有真实条目才能 `start`,seed 行不算(`workflow.md:424`) |
| 1.4 Activate task | `[required · once]` | 完成 artifact 评审 | `task.json.status` 由 `planning` 翻成 `in_progress`,`branch` 被记录 | `task.py start` 成功,breadcrumb 切 `[workflow-state:in_progress]`(`workflow.md:446`) |
| 1.5 Completion criteria | 判据表 | — | — | `workflow.md:452-465`:`prd.md` 存在 ✅、用户确认进入实现 ✅、已跑 `start` ✅、复杂任务的 `design.md`/`implement.md` ✅、`research/` 推荐、两个 jsonl 各有真实条目 ✅ |

产出物的职责边界写得很死(`workflow.md:158-164`):

- `prd.md` = 需求 + 约束 + 验收标准。**不许**写技术设计和执行清单。
- `design.md` = 边界、契约、数据流、权衡、兼容性、灰度/回滚形状。
- `implement.md` = 有序执行清单 + 验证命令 + 评审关卡 + 回滚点。
- `implement.jsonl` / `check.jsonl` = 给 sub-agent 的 spec/research 清单,**不替代** `implement.md`(`workflow.md:163`、`workflow.md:403`)。
- 轻量任务可以只有 PRD;复杂任务三件套齐了才能 `start`(`workflow.md:164`)。

实证:归档任务 `.trellis/tasks/archive/2026-08/08-10-full-trellis-ablation/` 是这套三件套的标准样本 —— `prd.md` 140 行(纯需求 + 验收,`prd.md:11-80` 全是 Requirements 小节)、`design.md` 136 行(组件表 + 外部状态 schema,`design.md:3-43`)、`implement.md` 51 行(13 步有序清单 + `## Required focused commands` 里 10 条真实命令 + `## Rollback` 4 条,`implement.md:1-51`)。这是「实现计划必须可被另一个 agent 照做」的正例。

### 1.2 Phase 2: Execute(`workflow.md:212-215`,详解 `workflow.md:469-563`)

| 步骤 | 标签 | 入口 | 产出 | 退出 |
|---|---|---|---|---|
| 2.1 Implement | `[required · repeatable]` | status=`in_progress` | 代码改动 + lint/typecheck 通过 | 实现 agent 交回报告(格式见 `.trellis/agents/implement.md:53-71`) |
| 2.2 Quality check | `[required · repeatable]` | 有未提交改动 | 审查发现 + 自动修复 + lint/typecheck 绿 | 全绿;**最后一次 2.2 必须全量跑**,不能只覆盖最近一块实现(`workflow.md:557`) |
| 2.3 Rollback | `[on demand]` | check 发现 PRD 缺陷 / 实现走错 / 需要补研究 | 回 Phase 1 改 `prd.md`、或 revert 重做 2.1、或补 `research/` | `workflow.md:559-563` |

2.2 的「最终全量」定义得很具体:用 `get_context.py --mode packages` 列出所有受影响 package,逐个加载该 package spec index 的 Quality Check 段(`workflow.md:557`)。这是跨层/跨包问题的唯一捕获点。

分工是硬的:主会话默认**派发** implement/check 子代理,子代理**自我豁免**不得再派(`workflow.md:228`);implement/check agent 都被禁止 `git commit`/`git push`/`git merge`,提交权归主会话(`.trellis/agents/implement.md:30-36`、`.trellis/agents/check.md:32-38`)。

### 1.3 Phase 3: Finish(`workflow.md:243-249`,详解 `workflow.md:567-643`)

编号从 3.2 起 —— 3.1 已被并入 2.2 和 3.4,编号故意保留不重排以免破坏外部引用(`workflow.md:249`)。

| 步骤 | 标签 | 入口 | 产出 | 退出 |
|---|---|---|---|---|
| 3.2 Debug retrospective | `[on demand]` | 同一问题被反复修 | 根因分类 + 早前修复为何失败 + 预防措施 | 载入 `trellis-break-loop` 走完(`workflow.md:571-578`) |
| 3.3 Spec update | `[required · once]` | check 通过 | `.trellis/spec/` 下的更新 | **即使结论是「没什么可更新」,也要走完判断**(`workflow.md:587`) |
| 3.4 Commit changes | `[required · once]` | 工作树脏 | 分组的工作提交 | 用户一次性确认后按序 commit;拒绝则停手转人工(`workflow.md:631-633`) |
| 3.5 Wrap-up reminder | — | 提交完成 | 提醒用户跑 `/finish-work` | `workflow.md:641-643` |

3.4 是整份 workflow 里唯一写成 7 步 SOP 的步骤(`workflow.md:595-639`),值得逐条抄:

1. `git status --porcelain` 快照全部脏路径;干净就跳到 3.5。
2. `git log --oneline -5` 学提交风格(前缀约定、语言、长度)。
3. 把脏文件分成两组:**本会话 AI 改过的** vs **不认识的**。不认识的不许静默纳入。
4. 起草提交计划,按「一个逻辑变更一个提交」分组,不是一文件一提交。不认识的文件单列在底部。
5. **一次性**呈现计划,一次性确认(给了确切的输出模板,含中英双语的确认词 `ok`/`行`/`我自己来`/`manual`)。
6. 确认后逐批 `git add` + `git commit`。**不 amend、不 push**。
7. 被拒就停,不许再出第二版计划。

以及三条 Rules(`workflow.md:635-639`):禁 `--amend`(因为后面还有 archive commit 和 journal commit,是三段三提交流程)、禁 push、批量计划只弹一次窗。

### 1.4 收尾/交接:`/trellis:finish-work`(`.claude/commands/trellis/finish-work.md`)

这一步不在 Phase 编号内,但它才是周期的真正闭合:

1. `get_context.py --mode record` 摸底:我的活动任务、git status、近期提交(`finish-work.md:5-17`)。若发现其他已完成未归档的任务,一次性问用户要不要顺手归档(默认否)。
2. 脏路径分诊:过滤掉 `.trellis/workspace/` 和 `.trellis/tasks/`(那是本命令自己的产物),剩下的判断属于当前任务还是别的窗口的并行工作。**属于当前任务的一律打回 Phase 3.4,本命令绝不代跑 `git commit`**(`finish-work.md:37-40`)。
3. `task.py archive <task-name>` —— 每次归档产生一个 `chore(task): archive ...` 提交。
4. `add_session.py --title --commit --summary` —— 产生一个 `chore: record journal` 提交。`--commit` 只填 3.4 的工作提交哈希,**不含**归档提交哈希(`finish-work.md:64`)。

最终 git log 顺序被显式规定为:`<3.4 工作提交>` → `chore(task): archive ...` → `chore: record journal`(`finish-work.md:66`)。

### 1.5 跨会话续工:两条通道

**通道 A — SessionStart 自动注入**(`.claude/settings.json:6-40`,三个 matcher:`startup`/`clear`/`compact`)。`session-start.py` 组装一个结构化 payload(`session-start.py:870-917`):`<session-context>` → `<current-state>` → `<trellis-workflow>`(workflow.md 概览)→ `<guidelines>`(只给 spec index 的**路径列表**,不塞内容)→ `<task-status>` → `<ready>`。其中 `<task-status>` 是 `_get_task_status()` 的输出(`session-start.py:424-511`),对五种状态给出明确 Next-Action:

- `NO ACTIVE TASK` → 先分类再问建任务许可
- `STALE POINTER` → 跑 `task.py finish` 清指针
- `PLANNING` 且无 prd → 载 `trellis-brainstorm` 写 `prd.md`
- `PLANNING` 且有 prd → 列出缺失的 `design.md`/`implement.md`、jsonl 是否已 curate,并强调「用户确认前不得进入实现」
- `COMPLETED` → 跑 `/trellis:finish-work`,脏就先回 3.4

它还会列出任务目录里存在哪些 artifact(`Present:` 行,检查 `prd.md/design.md/implement.md/implement.jsonl/check.jsonl/research/`,`session-start.py:454-460`)—— 这是「靠文件在不在来判断走到哪一步」的直接体现。

**通道 B — `/trellis:continue` 手动路由**(`.claude/commands/trellis/continue.md:23-34`),把 `status` × artifact 存在性映射到具体步骤号:

```
planning + 无 prd.md                          → 1.1
planning + 仅 prd.md                          → 判轻/复杂:轻量可进 1.4,复杂回 1.1 补 design+implement
planning + 三件套齐 + jsonl 未 curate         → 1.3
planning + 三件套齐 + jsonl 已 curate/内联模式 → 1.4
in_progress + 未开工                          → 2.1
in_progress + 已实现未检查                    → 2.2
in_progress + check 通过                      → 3.3 → 3.4
completed(罕见)                              → archive flow
```

这条命令显式声明「它替代用户记住 Trellis 流程,但它本身不构成实现批准」(`continue.md:25`)。

---

## 2. 状态存在哪里:全部状态文件与 schema

### 2.1 目录全景

```
.trellis/
├── .version              # "0.6.14" —— 模板版本
├── .developer            # 开发者身份,gitignored(.trellis/.gitignore:2)
├── .runtime/sessions/    # 每会话活动任务指针,gitignored(.trellis/.gitignore:8)
├── .template-hashes.json # 30KB,模板文件哈希台账(update 判定 pristine vs 用户改过)
├── config.yaml           # 项目级配置
├── workflow.md           # 709 行,周期状态机的文本本体
├── agents/               # channel runtime 的 agent 定义(architect/check/implement/plan/research)
├── scripts/              # task.py / add_session.py / get_context.py / init_developer.py + common/
├── spec/                 # 编码规范,按 <package>/<layer>/ 分层 + guides/
├── tasks/                # 任务目录 + archive/YYYY-MM/
└── workspace/            # 每开发者 journal + index
```

### 2.2 `task.json` —— 单任务的权威状态

`cmd_create` 写入的默认结构(`.trellis/scripts/common/task_store.py:494-518`),25 个字段:

| 字段 | 默认 | 说明 / 出处 |
|---|---|---|
| `id` / `name` | slug | 两个字段存同一个 slug;rename 时这两个是「身份字段」(`task_store.py:684-686` 注释) |
| `title` | 必填非空 | 空标题在 create 就被拒(`task_store.py:303-310`),理由是「归档时会被拒,现在拒只花一次重打命令」 |
| `description` | 必填非空 | 同上(`task_store.py:312-320`)。**注意 `workflow.md:317` 给的命令示例没带 `--description`,与代码不符** |
| `status` | `"planning"` | 周期的核心状态位 |
| `dev_type` / `scope` | `null` | `scope` 供 PR 标题用 |
| `package` | 推断 | 单仓忽略;monorepo 校验后写入(`task_store.py:328-342`) |
| `priority` | 参数 | P0-P3 |
| `creator` / `assignee` | 当前开发者 | 无 `.developer` 且未传 `--assignee` 时直接失败(`task_store.py:344-351`) |
| `createdAt` / `completedAt` | 今天 / null | `completedAt` 在 archive 时写(`task_store.py:1318`) |
| `branch` | `null` | **在 `start` 时自动记录当前分支**(`task.py:119-123`),注释解释:只在 start 记录才让 archive 时的 branch 可信,否则手工设的任务往往带着 `branch: null` 进归档 |
| `base_branch` | 解析默认分支 | 优先 `origin/HEAD`,解析不到就退化到当前分支并打警告(`task_store.py:472-492`) |
| `worktree_path` / `commit` / `pr_url` | `null` | 实证:归档任务里被填满,如 `08-10-full-trellis-ablation/task.json:15-19`(branch/commit/pr_url 都有值) |
| `subtasks` / `children` / `parent` | `[]`/`[]`/`null` | 见 §3.2 |
| `relatedFiles` / `notes` / `meta` | `[]`/`""`/`{}` | `meta` 供扩展(Linear 同步写 `meta.linear_issue`) |
| `hooks`(可选) | 不默认写 | `after_create/after_start/after_finish/after_archive`(`workflow.md:688-702`) |

**schema 漂移实证**:老归档任务 `.trellis/tasks/archive/2026-04/04-16-skill-first-refactor/task.json` 只有 9 个字段(`title/status/priority/assignee/created/completedAt/branch/notes/subtasks/children`),`created` 而非 `createdAt`,`subtasks` 里存的是**完整路径**(`.trellis/tasks/archive/2026-04/04-16-agents-hooks-test`)而新 schema 的 `children` 存的是**目录名**。归档区里同时躺着两代 schema。

### 2.3 `implement.jsonl` / `check.jsonl` —— 子代理上下文清单

**是什么**:每行一个 JSON 对象,`{"file": "<repo 相对路径>", "reason": "<为什么要读>"}`(`workflow.md:389`)。

**放什么 / 不放什么**(`workflow.md:391-401`):

- 放:`.trellis/spec/<package>/<layer>/index.md` 和具体规范文件、`{TASK_DIR}/research/*.md`
- **不放**:代码文件(`src/**`、`packages/**/*.ts`)、即将被修改的文件 —— 理由是「那些是子代理实现时自己去读的,不预注册」
- 分工:`implement.jsonl` = 写对代码需要的 spec+research;`check.jsonl` = 质量规范、检查约定 + 同样的 research

**真实样本**(`.trellis/tasks/archive/2026-08/08-10-full-trellis-ablation/implement.jsonl:1-7`,7 条):6 条 spec + 1 条本任务的 research 文件,每条 reason 都是一句具体的「这条能约束什么」。对应的 `check.jsonl:1-6` 是 6 条,和 implement 有重叠但侧重质量/安全审计。这是这套机制被认真用起来时的样子。

**谁消费**:`PreToolUse` 钩子 `inject-subagent-context.py`。注入顺序被固定为 `jsonl entries → prd.md → design.md(若有) → implement.md(若有)`(`inject-subagent-context.py:539-542`,同一顺序在 `workflow.md:229`、`session-start.py:892-894`、`workflow-state-contract.md:349-352` 各复述一遍)。钩子输出 `permissionDecision: "allow"` + `updatedInput`(`inject-subagent-context.py:1183-1205`)。

**schema 宽容度**:`curated_entry_count()` 认 `file` **或** legacy `path` 两种键(`.trellis/scripts/common/task_context.py:152`)。文件不存在返回 `None`(不 gate),存在但零条返回 `0`(gate)。

**两处 schema 说法不一致**:`.trellis/agents/research.md:215-226` 给的 jsonl 样例用的是 `{"path": ..., "description": ...}`,和 `workflow.md:389` 的 `{"file":..., "reason":...}` 不同键名。代码两者都吃,但文档层面是漂移。

**注入上限**:`config.yaml:151-154`(默认注释掉)规定 `max_file_bytes: 32768` / `max_artifact_bytes: 65536` / `max_total_bytes: 131072`,超限的文件降级成「索引行(路径+reason+大小)」而非内联。

### 2.4 会话指针 `.trellis/.runtime/sessions/*.json`

`active_task.py:1-7` 的 docstring 说得最清楚:「用户面向的概念是单一『活动任务』;Trellis 把这个指针按 AI 会话/窗口存在 `.trellis/.runtime/sessions/` 下;**没有稳定的会话 key 就没有活动任务**。」

- 写:`set_active_task()`(`active_task.py:734-760`),内容为 `{current_task: <canonical ref>, current_run: null, ...metadata}`
- 清:`clear_active_task()` 删掉该会话的文件(`active_task.py:763-780`);`clear_task_from_sessions()` 删掉所有指向某任务的会话文件(`active_task.py:783+`,归档时调用)
- key 从哪来:hook stdin → `TRELLIS_CONTEXT_ID` → 平台原生 session 环境变量(`_ENV_SESSION_KEYS`,`active_task.py:66+`)
- **gitignored**(`.trellis/.gitignore:7-8`),即会话指针是本地态,不进版本库

这里有一个被自己的研究任务揭穿的坑:`.trellis/tasks/08-05-session-identity-propagation/research/platform-session-identity.md:12-16` 的结论是「**21 个平台里没有一个默认把 session id 导出给 shell 子进程**;14 个声明的环境变量名里 9 个是凭空造的」。也就是说这套「会话级活动任务」的底层前提在多数平台上不成立,会退化到 degraded mode(`task.py:236-247`:打印「Session identity not available…AI continues based on conversation context」,但**仍然翻转 `task.json.status`**)。

### 2.5 Spec 系统

- 布局:`.trellis/spec/<package>/<layer>/index.md` + 同目录具体规范文件;`.trellis/spec/guides/` 放跨包思维指南(`workflow.md:29-32`)
- 本仓实际:`spec/cli/backend/`(21 个文件)、`spec/cli/unit-test/`(4 个)、`spec/core/backend/`、`spec/docs-site/docs/`(8 个)、`spec/tech/repo/`、`spec/guides/`(3 个 guide + index)
- index 的固定结构:`## Guidelines Index` 表 + `## Pre-Development Checklist`(按「你要改什么 → 读哪个文件」的映射,`spec/cli/backend/index.md:40-65`,24 条)+ `## Quality Check`(改完后的 5 步验证,`index.md:69-84`)
- 何时更新:发现新模式/约定、要固化的 bug 预防、新技术决策(`workflow.md:38`)

### 2.6 Workspace / journal 系统

- `.trellis/workspace/<developer>/journal-N.md` —— 会话日志,**每文件最多 2000 行**,超了自动开 `journal-(N+1).md`(`workflow.md:82`;上限也在 `config.yaml:15` 的 `max_journal_lines: 2000`)
- `.trellis/workspace/<developer>/index.md` —— 个人索引,含三个自动维护块:`<!-- @@@auto:current-status -->`、`@@@auto:active-documents`、`@@@auto:session-history`(`workspace/taosu/index.md:9-13, 19-27, 33-35`)
- `.trellis/workspace/index.md` —— 全局索引 + 目录结构说明 + Session 模板(`workspace/index.md:87-121`)
- 写者:`add_session.py --title --commit --summary`(`workflow.md:86`)。它的 docstring 记了三条硬约束(`add_session.py:26-42`):每个 `--commit` token 必须是 7-40 位 hex OID 且**能在本地对象库解析出真实 subject**,解析不出就在写任何文件之前失败(「绝不记录占位散文」);journal 追加 + index 行 + 自动提交是一个可重入操作,带指纹标记,重跑修复而不是追加第二条。
- 自动提交:`config.yaml:12` `session_commit_message: "chore: record journal"`;`config.yaml:33` `session_auto_commit`(默认 true)可关。

### 2.7 `config.yaml` 全部旋钮(`.trellis/config.yaml`)

| 段 | 键 | 作用 |
|---|---|---|
| Session Recording | `session_commit_message`(:12)、`max_journal_lines`(:15) | journal 提交信息与轮转阈值 |
| Auto-commit | `session_auto_commit`(:33) | 关掉后脚本完全不碰 git,文件照写 |
| Task Lifecycle Hooks | `hooks.after_create/after_start/after_finish/after_archive`(:43-51) | 每个 hook 收到 `TASK_JSON_PATH` 环境变量;**失败只打警告不阻断主操作**(:41) |
| Packages | `packages`(:75-82)、`default_package`(:85) | monorepo 声明,决定 spec 分层与 `--mode packages` |
| Channel worker guard | `idle_timeout: 5m`、`max_live_workers: 6`(:110-113) | 多 agent 运行时的 OOM 护栏 |
| Codex | `codex.dispatch_mode: auto\|inline`(:137-138) | 决定走子代理还是内联 |
| Context injection | `max_file_bytes/max_artifact_bytes/max_total_bytes`(:151-154) | 子代理首轮注入上限 |
| Prompt injection | `prompt_injection.skip_keyword: "no-trellis"`(:165-166) | 每回合 breadcrumb 的逃生阀 |

---

## 3. 任务生命周期状态机与父子树

### 3.1 状态机

**真实状态只有三个**,加上四个伪状态。权威表在 `.trellis/spec/cli/backend/workflow-state-contract.md:251-270`,它枚举了**全部 7 个 `task.json.status` 写者**并声明「新增写者必须更新本 spec」:

| # | 写者 | 值 | 触发 |
|---|---|---|---|
| 1 | `cmd_create` | `planning` | `task.py create`(同时尽力设置会话指针) |
| 2 | `_record_start_state` | `in_progress`(仅当原值为 `planning`) | `task.py start` |
| 3 | `cmd_archive` | `completed`(+ 目录 mv) | `task.py archive` |
| 4 | `emptyTaskJson` 工厂(TS) | `planning` | init / update |
| 5 | `getBootstrapTaskJson` | `in_progress` | `trellis init`(创建者路径) |
| 6 | `getJoinerTaskJson` | `in_progress` | `trellis init`(加入者路径) |
| 7 | migration-task | `planning` | `trellis update --migrate` |

「**没有其他写者。没有任何 hook 脚本写 `task.json.status`**」(`workflow-state-contract.md:267-270`),并给出了核验方式(`grep -rn '"status"' .trellis/scripts/`)。

伪状态(由 breadcrumb 钩子合成,不落盘):`no_task`、`task_error`(task.json 读不了或没有可用 status)、`stale_<source_type>`(指针指向已删目录)(`workflow-state-contract.md:69-78, 291-303`)。

**流转图**:

```
(无任务) --create--> planning --start--> in_progress --archive--> completed + mv 到 archive/YYYY-MM/
   ^                    |                    |
   |                    |  finish(只清会话指针,status 不变)
   +--------------------+--------------------+
```

三个关键性质:

1. **`completed` 在正常流程里是死状态**(`workflow.md:128-133`、`workflow-state-contract.md:299`)。`cmd_archive` 在同一次调用里写 `status="completed"`、清会话指针(`task_store.py:1372-1374`)、再 mv 目录 —— 解析器在同一次调用里就丢了指针,所以 `[workflow-state:completed]` 这个 breadcrumb 块**永远不会触发**。块被保留是为将来可能的显式 `in_progress → completed` 转换。
2. **生命周期事件 ≠ 状态转换**(`workflow-state-contract.md:273-289`)。`after_finish` 只意味着「AI 会话关闭了指向这个任务的指针」,任务可能在另一个会话继续;想在外部系统(Linear/Jira)标记完成,**必须订阅 `after_archive`**。这一条被单独列进 DON'T(`workflow-state-contract.md:383-384`)。
3. **两个正交的「当前任务」概念**:`task.json.status`(仓库级、跨会话持久、进版本库)vs `.runtime/sessions/*.json` 指针(会话级、本地、gitignored)。`task.py start` 同时写两者;`task.py finish` 只清后者;`task.py archive` 写前者并清所有指向它的后者。

### 3.2 创建与归档的实际守卫

`cmd_create`(`task_store.py:295-673`)在写任何东西之前依次拒绝:空 title(:303)、空 description(:312)、非法 `--meta`(:323)、未知 `--package`(:335)、无 developer 且无 `--assignee`(:348)、带路径分隔符或 `..` 的 slug(:366)、带日期前缀的 slug(:383-405,今天的前缀会被规范化掉并警告,别的日期直接报错)、目录名与归档区撞名(:433)、目录已存在且未加 `--force`(:444,理由写在注释里:继续会重写 task.json 从而清掉 status/children/parent/branch/meta,「没有任何东西能重建它们」)。写 `task.json` 失败会把刚建的空目录删掉(:604-614)。

`cmd_archive`(`task_store.py:1223-1404`)的顺序同样是「先校验后变更」:

1. 拒绝不在 `.trellis/tasks/` 直下的目标(:1258)—— 防止把已归档任务再归档一次
2. **先检查归档目的地是否已存在**(:1269-1278),注释解释:mover 自己也会拒冲突,但那时任务已经被标 completed、子任务已被解链、会话指针已被清,全都得手工回滚
3. `_validate_branch_metadata`(:1305)—— 分支元数据在任务离开活动区后不可恢复,所以在这里卡;陈旧分支只警告
4. 写 `status=completed` + `completedAt`(:1317-1318)
5. 若是父任务,把所有子任务的 `parent` 置空(:1336-1370);**任一子任务写失败就整体中止**,不 mv —— 注释:「子任务指向一个已经离开 `.trellis/tasks/` 的父任务是没人会修的悬空引用」
6. 清所有指向它的会话文件(:1372-1374)
7. mv 到 `archive/YYYY-MM/`,自动提交(`chore(task): archive ...`),跑 `after_archive` hook(:1377-1401)

自动提交的作用域被刻意收窄:只 stage 被归档任务的源/目标路径 + 被改过 `task.json` 的子任务目录,**其他活动任务目录的脏改动不进这个提交**(`task_store.py:1412-1417`);`.gitignore` 挡住时只警告不 `git add -f`(:1419-1422)。

### 3.3 父子任务树

**定位**(`workflow.md:166-172`):

- 用父任务的判据:一个用户请求里含**多个可独立验证的交付物**
- 父任务拥有:源需求集合、任务地图、跨子任务验收标准、最终集成评审;**通常不作为实现目标**,除非它自己也有直接工作
- 子任务的判据:能被独立 plan / implement / check / archive
- **父子结构不是依赖系统**:若 B 依赖 A,把顺序写进 B 的 `prd.md`/`implement.md`,不能靠树位置暗示
- 起工时启动「拥有下一个可独立验证交付物的那个子任务」,不要因为有子任务就 start 父任务(`workflow.md:322, 348`)

**数据结构**:双向链接。子任务 `task.json.parent` 存父目录名,父任务 `task.json.children` 存子目录名数组。`cmd_create --parent` 一次写两边(`task_store.py:561-590`),父边写失败会明确告诉你用 `add-subtask` 补链,子边写失败会明确说「链接写了一半」(:583-587)。另有 `add-subtask` / `remove-subtask` 手动增删(`workflow.md:172`)。

**实证**:`.trellis/tasks/08-05-session-identity-propagation/task.json` 的 `children` 有 4 个;4 个子任务(`08-05-opencode-shell-env`、`08-05-session-identity-hardening`、`08-05-purge-fake-env-names`、`08-05-shell-ticket-bridge`)的 `parent` 都指回它。父任务的 `prd.md` 是一份纯研究 PRD —— 目标是「产出一张每平台矩阵和一条建议,而不是一个修复」(`prd.md:10-11`),Out of scope 明写「实现修复;任何修复作为按平台的后续任务落地」(`prd.md:48-51`)。这就是「父任务拥有源需求,子任务拥有交付物」的教科书用法。

**两处派生显示逻辑**:

- `_display_status()`(`task.py:356-372`):父任务的 status 会一直停在 `planning`(除非有人直接 start 父任务),即使子任务都在跑 —— 对扫列表的人是误导。所以 list 输出在「至少一个子任务过了 planning」时显示 `active`,**但不改磁盘上的值**。
- `children_progress()`(`common/tasks.py:100-122`):输出 ` [2/3 done]`。关键细节:活动集合里找不到的子任务算 done(因为 archive 会把它移走),这样父进度不会在子任务归档时倒退。

**遗留字段**:新 schema 同时有 `subtasks` 和 `children` 两个数组;新建任务两者都是 `[]`,只有 `children` 被写。老归档任务只有 `subtasks` 且存全路径(见 §2.2)。

---

## 4. Spec 系统与 Workspace/journal 在周期里的角色

### 4.1 Spec:项目的长期记忆,读写不对称

| 环节 | 谁 | 动作 | 出处 |
|---|---|---|---|
| SessionStart | hook | **只注入 spec index 的路径清单**,不注入内容(「read on demand」) | `session-start.py:900-908` |
| 1.2 Research | `trellis-research` 子代理 | 从 spec index 开始读,把发现的 spec 路径写进 jsonl | `.trellis/agents/research.md:24-40` |
| 1.3 Configure context | 主会话/研究代理 | 把相关 spec 路径 curate 进 `implement.jsonl`/`check.jsonl` | `workflow.md:391-401` |
| 2.1 / 2.2 | 注入钩子 | 按 jsonl 把 spec 文件内容内联进子代理首轮 prompt | `inject-subagent-context.py:539-542` |
| 2.2 最终一次 | check 代理 | 加载每个受影响 package 的 spec index `Quality Check` 段 | `workflow.md:557`;段落样例 `spec/cli/backend/index.md:69-84` |
| 3.3 Spec update | `trellis-update-spec` skill | **回写**新知识到 spec | `workflow.md:580-587` |
| 3.4 提交前 | 主会话 | Spec-sync preamble:再问一次「这次修的 bug 或发现的非显然知识该不该进 spec」,该进就退回 3.3 —— **spec 写入必须和本任务的代码在同一批提交里,不能变成被遗忘的后续项** | `workflow.md:591` |

设计原则第 2 条把这条链概括为「**Specs injected, not remembered** —— 规范通过 hook/skill 注入,不靠记忆回忆」(`workflow.md:8`);第 5 条是「**Capture learnings** —— 每个任务后回顾并把新知识写回 spec」(`workflow.md:11`)。

`trellis-update-spec` 的门槛不低:命中「新增/变更命令或 API 签名、跨层请求/响应契约变更、DB schema/迁移、基础设施集成」任一项时,必须产出 7 段式(Scope/Trigger、Signatures、Contracts、Validation & Error Matrix、Good/Base/Bad Cases、Tests Required、Wrong vs Correct)(`.claude/skills/trellis-update-spec/SKILL.md:22-40`)。`workflow-state-contract.md` 本身就是按这个模板写出来的产物。

`spec/guides/` 是另一类:不是规范而是「思维触发器」。`spec/guides/index.md:9-16` 的立论是「大多数 bug 和技术债来自『没想到』,不是能力不足」,于是把三类「没想到」做成 checklist:跨层(:32-41)、代码复用(:43-53)、跨平台(:55-64)。还有一段专治 AI 交叉审查的假阳性(:66-78),给出三种常见误报模式并直接给了个量化预期:「AI 审查按 ~35% 假阳性率预算」。

### 4.2 Workspace/journal:跨会话的叙事记忆

| 环节 | 谁 | 动作 |
|---|---|---|
| 首次使用 | 人 | `init_developer.py <name>` 建 `.developer` + `workspace/<name>/`(`workflow.md:19-25`) |
| `/finish-work` Step 4 | AI | `add_session.py` 追加一条 session 记录到 `journal-N.md` 并更新 index 三个 auto 块 |
| 新会话 | 人/AI | `cat .trellis/workspace/$(get_developer.py)/index.md`(`workspace/index.md:52-60`) |

单条 session 记录的模板(`workspace/index.md:87-121`):Session 号 + 标题 + 日期 + 任务 + 分支 + Summary + Main Changes + Git Commits 表 + Testing + Status + Next Steps。

**实证与缺口**:`workspace/taosu/index.md` 有 175 条 session 记录,每条带日期/标题/commit 哈希/分支,是一份货真价实的项目编年史。但打开具体条目(`workspace/taosu/journal-5.md:20-42`)会看到:`### Main Changes` 是 `(Add details)`,`### Testing` 是 `- [OK] (Add test results)` —— 模板占位符原样留着,真正的信息全挤在 `Summary` 一大段里。也就是说 **journal 的结构化字段基本没被填,退化成了「带元数据的长摘要」**。

更明显的缺口:`workspace/index.md:28-31` 的 Active Developers 表只列了 `kleinhe | 2026-01-26 | 12 sessions`,而磁盘上有 7 个开发者目录、taosu 一个人就 175 次 session、最后活跃 2026-08-01。**全局 index 没有任何自动写者,已经陈旧了 7 个月**(个人 index 有 `@@@auto:` 块由 `add_session.py` 维护,全局 index 没有)。这是「有产物无消费者/无写者」的典型不闭环。

---

## 5. Guardrails 与 Rules:哪些靠文字、哪些有机制

### 5.1 文字里写了什么

**`### Rules`(`workflow.md:263-269`)**,5 条:

1. 先判断自己在哪个 Phase,从那里的下一步继续
2. Phase 内按顺序跑,`[required]` 不能跳
3. Phase 可以回滚(Execute 发现 prd 缺陷 → 回 Plan 修 → 再进 Execute)
4. `[once]` 步骤若产物已存在就跳过,别重跑
5. **artifact 的存在与否决定下一步**;缺 `design.md`/`implement.md` 对轻量任务是合法的,对复杂任务是「计划未完成」

**`### Guardrails`(`workflow.md:291-295`)**,3 条:

1. 建任务批准 ≠ 实现批准;实现要等 artifact 评审后的 `task.py start`
2. 轻量任务 PRD-only 合法;复杂任务需要 `design.md` + `implement.md`
3. 计划必须持久化到任务 artifact;检查必须在报告完成之前跑

**`### Active Task Routing`(`workflow.md:271-289`)**:意图 → 工具的路由表,按平台分两组(子代理平台 / 内联平台)。

**其他散落的文字约束**:

- Fork 定制时的三条不可破不变量(`workflow.md:653-656`):无活动任务必须先分诊并征得建任务同意;planning 必须区分轻量 PRD-only 与复杂三件套;每条必经路径都必须让 3.4 的提交提醒在 `/trellis:finish-work` 之前可达
- `trellis-brainstorm` 的「Non-Negotiable Planning Contract」(`SKILL.md:9-15`):「build / implement / fix / refactor / 『go ahead』都不是离开 planning 的批准」;非平凡任务里**用户必须在初始请求之后至少回应一次**;还有用户方待决项时,回合必须以恰好一个最高价值问题结束,且不得改产品代码、不得派实现、不得跑 `task.py start`
- 同一 skill 的「Non-Negotiable Evidence Rule」(`SKILL.md:17-27`):能从代码/测试/配置/文档/spec/任务历史查到的,不许问用户;只问产品意图、偏好、范围、风险容忍度、验收行为
- 子代理的 Forbidden Operations(`.trellis/agents/implement.md:30-36`、`check.md:32-38`):禁 `git commit`/`push`/`merge`,「监督它的主会话拥有提交权」
- 研究代理的证据规则(`.trellis/agents/research.md:77-91`):每条技术论断必须配 5-40 行**逐字**代码/文档片段 + `repo/path/file.ts:120-145` 精确引用;明令禁用「it basically does X」「typically」「likely uses」「seems to」等短语;「找不到证据就删掉论断,空章节好过幻觉章节」

### 5.2 哪些真有机制兜底

| 规则 | 机制 | 位置 |
|---|---|---|
| 每回合提醒当前阶段该干什么 | `UserPromptSubmit` hook 注入 `<workflow-state>` breadcrumb,内容从 `workflow.md` 的 `[workflow-state:*]` 块解析 | `.claude/settings.json:60-70`;`inject-workflow-state.py`;契约 `workflow-state-contract.md:67-113` |
| breadcrumb 内容不许有第二份拷贝 | v0.5.0-rc.0 后**删掉了脚本里的 `_FALLBACK_BREADCRUMBS` 字典**,解析不到就降级成显眼的 `Refer to workflow.md for current step.`,让用户看得见去修 | `workflow.md:106-111`;`workflow-state-contract.md:215-227` |
| 每个 `[required · once]` 步骤都必须在对应 breadcrumb 块里被提到 | **回归测试不变量**(`test/regression.test.ts`),因为 breadcrumb 是唯一的 per-turn 通道,没提到的强制步骤 AI 会静默跳过(Phase 1 planning gate 和 Phase 3.4 commit 两次事故都是这么来的) | `workflow.md:113-118`;`workflow-state-contract.md:11-21, 305-318` |
| 解析器与剥离器正则必须同用 `\1` 反向引用 | 回归测试 `[strip-breadcrumb] ... only strips matched STATUS pairs` 覆盖三种边界 | `workflow-state-contract.md:52-63` |
| 新会话必须知道当前状态 | `SessionStart` hook 三个 matcher(startup/clear/compact)注入结构化 `<task-status>` + Next-Action | `.claude/settings.json:6-40`;`session-start.py:424-511` |
| 子代理必须带着正确 context 启动 | `PreToolUse`(matcher `Task`/`Agent`)注入 jsonl 引用文件 + prd/design/implement | `.claude/settings.json:41-58`;`inject-subagent-context.py:539-542` |
| jsonl 未 curate 不许 start | **`task.py start` 硬拒绝**(issue #573):两个 manifest 任一 curated 条目为 0 就 `return 1`,并给出 add-context/validate 命令;逃生阀 `--allow-empty-context`。文件不存在不 gate(说明该平台没子代理) | `.trellis/scripts/task.py:196-215`;计数逻辑 `common/task_context.py:128-154` |
| 任务元数据不能残缺 | `create` 拒空 title/description/非法 slug/撞名(§3.2);`archive` 前校验 branch 元数据、归档目的地冲突、子任务解链 | `task_store.py:303-450, 1258-1370` |
| 归档/journal 的提交作用域不许外溢 | 自动提交只 stage 本任务相关路径;`.gitignore` 挡住时警告而非 `git add -f` | `task_store.py:1407-1422` |
| journal 里的 commit 证据不能编 | 每个 OID 在写文件之前必须能从本地对象库解析出真实 subject,否则命令失败 | `add_session.py:26-32` |
| 模板文件被用户改过要能识别 | `.trellis/.template-hashes.json`(30KB)+ `trellis update` 的 hash 流程 | `workflow-state-contract.md:236-249` |
| 每回合注入的逃生阀 | prompt 里出现独立单词 `no-trellis`(词边界匹配,`no-trellisfoo` 不算)时本回合跳过 breadcrumb | `config.yaml:159-166` |

### 5.3 关键结论:整套工作流是**建议性**的,没有阻断

- `.claude/hooks/` 里唯一出现的 `permissionDecision` 值是 `"allow"`(两处,`inject-subagent-context.py:1188, 1197`),没有任何 `"deny"`。
- 这一点被 Trellis 自己的任务 PRD 记在案:「**代码库里没有任何 Trellis hook 拒绝过工具调用** —— 全树只有两个 `permissionDecision` 值,都是 `allow`。工作流的强制是建议性的。」(`.trellis/tasks/08-05-session-identity-propagation/prd.md:31-34`)
- 也就是说:除了 `task.py start` 的 jsonl gate(§5.2)和 `task.py create/archive` 的输入校验,**周期里所有「不许跳过」都靠模型读文字后自愿遵守**。机制层做的是「保证正确的文字每回合都出现在模型眼前」,不是「拦住错误动作」。

### 5.4 实测到的规则失效证据

| 现象 | 证据 | 说明 |
|---|---|---|
| jsonl ready gate 在存量任务上大面积未满足 | 11 个活动任务里 9 个的 `implement.jsonl`/`check.jsonl` 是**空文件**,2 个只有 `_example` seed 行,只有 `07-23-codex-inline-default-agent-model` 有真实条目(implement 2 条 / check 1 条);而这些任务的 `status` 全是 `in_progress` | gate 是后加的(#573),存量任务是在 gate 之前 start 的,或用了 `--allow-empty-context`。文档层面 `workflow.md:424` 把它写成「必须」,磁盘上的事实是「多数没做」 |
| 文档说 seed `_example`,代码写空文件 | `workflow.md:55-56, 385, 422` 说 create 会 seed 一行自描述的 `_example`;`task_store.py:546-560` 的注释明说「占位行会被 `task.py validate` 和 PR preflight 读成未解决的脚手架」,所以写空字符串 | 文档 3 处漂移 |
| `create` 命令示例缺必填参数 | `workflow.md:317` 示例是 `task.py create "<task title>" --slug <name>`,但 `--description` 是必填(`task_store.py:312-320`) | 照抄 workflow.md 会直接报错;`trellis-brainstorm/SKILL.md:40` 的示例是对的 |
| research 产物路径两套说法 | `workflow.md:362, 373` 说写 `{TASK_DIR}/research/`;`.trellis/agents/research.md:95, 267` 说写 `.trellis/tasks/{id}/context/{topic}.md` | 磁盘上实际用的是 `research/`(3 个任务目录都是) |
| `completed` breadcrumb 永不触发 | `workflow.md:128-133, 251-257`、`workflow-state-contract.md:299` 都承认 | 死代码被显式标注保留,属于诚实的技术债 |
| workspace 全局 index 陈旧 7 个月 | `workspace/index.md:28-31` vs `workspace/taosu/index.md:9-13` | 无自动写者 |
| journal 结构化字段未被填写 | `workspace/taosu/journal-5.md:20-22, 31-33` 等多处 `(Add details)` / `(Add test results)` | 模板给了但没人填,信息实际挤在 Summary |

---

## 6. 判断:哪些是核心不可少,哪些是为多人/多平台/大团队加的重

判断基准:一个**单人 + 单平台 + 项目级**的轻量 harness,要不要这条。

### 6.1 核心不可少(7 条)

**C1. 任务目录 = 状态单元,一切落盘。**
依据:核心原则第 3 条「Persist everything —— 研究、决策、教训全进文件;对话会被压缩,文件不会」(`workflow.md:9`),1.2 又重复一次(`workflow.md:379`)。整套跨会话续工(`session-start.py:454-460` 的 `Present:` 行、`continue.md:23-34` 的路由表)完全建立在「读目录里有哪些文件」之上,没有第二个真相源。这是整个模型里最便宜也最关键的设计:**状态即文件系统**。

**C2. `prd.md` / `design.md` / `implement.md` 三层分离,且职责互斥。**
依据:`workflow.md:158-164` 明确禁止把技术设计和执行清单写进 PRD。理由在 `08-10-full-trellis-ablation` 这个正例里能直接看到 —— `implement.md` 51 行里有 13 步顺序 + 10 条可复制的验证命令 + 4 条回滚约定,这是**另一个 agent 拿着能照做**的东西;如果它和需求混在一份文档里,子代理的注入预算会被需求叙述吃光。轻量任务允许 PRD-only(`workflow.md:164`)也很关键,否则小改动会被仪式压垮。

**C3. 「建任务同意 ≠ 实现同意」这道双门。**
依据:三处独立强调(`workflow.md:156`、`workflow.md:293`、`trellis-brainstorm/SKILL.md:9-15`),且被列为 fork 不可破不变量(`workflow.md:654`)。这是唯一挡住「AI 听到需求就开始写代码」的结构性设计,成本只是一次额外确认。brainstorm 那条「非平凡任务里用户必须在初始请求后至少回应一次」是把它做成了可判定条件而非态度。

**C4. 每回合注入(per-turn breadcrumb)+ 单一文本真相源。**
依据:`workflow-state-contract.md:11-21` 说破了根因 —— **breadcrumb 是任务活动期间唯一的 per-turn 通道,没在里面提到的强制步骤 AI 会静默跳过**,Phase 1 planning gate 和 Phase 3.4 commit 两次事故都是这个失效模式。配套的两个设计同样不可少:(a) 删掉脚本里的 fallback 文本字典,让 workflow.md 成为唯一可编辑源(`workflow.md:106-111`);(b) 用回归测试锁死「每个 `[required · once]` 步骤必须在对应 breadcrumb 块里有一行」(`workflow.md:113-118`)。**没有 (b),(a) 会慢慢腐烂。**

**C5. `task.json.status` 的单一写者表 + 「新增写者必须更新 spec」。**
依据:`workflow-state-contract.md:251-270` 枚举全部 7 个写者并断言「没有其他写者」,还给了核验命令。这条的价值不在于状态本身复杂(只有三个值),而在于**它把「谁能改状态」变成一个可审计的有限集合**。轻量 harness 状态更少,但这条纪律照抄成本近乎为零。

**C6. archive 是唯一的「完成」事件,且 finish ≠ 完成。**
依据:`workflow-state-contract.md:273-289` 的生命周期事件表 + DON'T 里那条「别订阅 `after_finish` 来检测完成」(:383)。这是一个真实踩过的坑被固化成契约的例子:`finish` 只清会话指针,任务可能在别的会话继续。任何轻量 harness 只要有「暂停」和「完成」两个概念,就必须区分这两者。

**C7. 提交在收尾之前,且顺序被规定死。**
依据:`workflow.md:593`(「先产出工作提交,记账提交在后 —— 绝不交错」)、`finish-work.md:37-40`(finish-work 遇到本任务的脏改动**打回 3.4,自己绝不 commit**)、`finish-work.md:66`(最终 log 顺序 `工作提交 → archive → journal`)。这条约束的收益是 git 历史可读:一个任务在历史里是「一组语义提交 + 一个归档提交 + 一个日志提交」,而不是一坨。另外 3.4 那条「不认识的脏文件不许静默纳入」(`workflow.md:611`)是防止 AI 把别人的 WIP 打包进提交的实用护栏。

### 6.2 为多人 / 多平台 / 大团队加的重(6 类)

**H1. 多平台适配(最大的一块重量)。**
依据:`workflow.md` 709 行里,平台条件块 `[Claude Code, Cursor, OpenCode, codex-sub-agent, Kiro, Gemini, Qoder, CodeBuddy, Copilot, Droid, Pi, Oh My Pi, ZCode, Snow, Reasonix, Trae, Grok, Kimi Code]` 及其内联对照组反复出现约 6 处(:275-289, :356-370, :383-434, :461-465, :475-526, :530-555),2.1 一个步骤被写了 4 个平台变体。`packages/cli/src/templates/` 下有 21 个平台目录。`.trellis/agents/` 的 agent 定义带 `provider: codex` / `provider: claude` 字段。**单平台 harness 可以把 workflow.md 砍掉至少三分之一。**

**H2. 会话身份解析(857 行,且前提在多数平台不成立)。**
依据:`common/active_task.py` 857 行,`_ENV_SESSION_KEYS` 表里每一项都配了一段「怎么核实的」注释(`active_task.py:63-120`)。而 Trellis 自己的研究结论是「21 个平台没有一个默认把 session id 导给 shell 子进程;14 个声明名里 9 个是造的」(`tasks/08-05-session-identity-propagation/research/platform-session-identity.md:12-16`)。**这整块复杂度的存在理由是「同一仓库同时开多个 AI 窗口,各自有各自的活动任务」** —— 单人单窗口场景下,一个 `.trellis/.current-task` 文件就够了(Trellis 的 `.gitignore:5` 里还留着这个老文件名的条目)。

**H3. 双 jsonl 清单 + 注入上限 + 注入钩子(1212 行)。**
依据:`inject-subagent-context.py` 1212 行;`config.yaml:151-154` 的三档字节上限;`workflow.md:381-434` 整整 54 行讲怎么 curate。这一整套的**唯一目的**是「主会话不进子代理的上下文,所以要人工挑选文件塞进子代理的首轮 prompt」。判据来自它自己:内联模式(`codex-inline` 等)直接跳过 1.3,改由 `trellis-before-dev` skill 在主会话里读(`workflow.md:430-434`)。**如果轻量 harness 不派子代理,或者派的子代理能自己读文件,这一整块可以删。** 佐证:11 个活动任务里 9 个的 jsonl 是空的,项目自己也没在日常严格执行。

**H4. 多开发者身份 + journal 轮转 + 三级 index。**
依据:`init_developer.py` / `get_developer.py` / `.developer` 文件 / `workspace/<dev>/` 每人一套 / 2000 行轮转 / 个人 index 的三个 `@@@auto` 块 / 全局 index。判据:全局 index 已经陈旧 7 个月无人维护(§4.2),说明**它服务的场景(多人协作时互相看对方进度)在这个仓库里实际没有发生**。单人 harness 需要的只是「一份带 commit 哈希的按时间倒序清单」,不需要身份层和轮转。但要注意:`add_session.py` 那条「commit OID 必须能解析出真实 subject 否则失败」(`add_session.py:26-32`)是值得抄的,它防的是 AI 编造提交记录。

**H5. Monorepo package/layer 分层与 spec scope。**
依据:`config.yaml:56-85` 的 packages 声明、`get_context.py --mode packages`、spec 的 `<package>/<layer>/` 两级目录、`session-start.py:960+` 的 `_resolve_spec_scope`。单包项目里这全部退化成一层目录。判据:`config.yaml:60` 的注释自己说「Trellis 在 `trellis init` 时自动探测 workspaces」—— 是为 monorepo 用户加的。

**H6. 父子任务树。**
这条是**边界情况**,我判它偏重但不是纯重。依据:它明确不是依赖系统(`workflow.md:170`),真正的排序仍要写进子任务的 `prd.md`/`implement.md`;它带来的代价是双向链接的一致性维护(`task_store.py:561-590` 的半写状态处理、`cmd_archive:1336-1370` 的解链失败中止)、两处派生显示逻辑(`_display_status` 的假 `active` 状态、`children_progress` 把归档算 done)、以及两代 schema 并存(`subtasks` vs `children`)。收益是「一个大请求拆成多个可独立验证交付物」这个真需求。**轻量 harness 的替代方案:在父任务的 `prd.md` 里放一张子任务清单表(路径 + 一句话 + 完成勾),不做双向链接、不做进度派生。** 依据是 Trellis 自己的父任务 PRD 就是这么写的(`tasks/08-05-session-identity-propagation/prd.md:69-81` 的 Acceptance Criteria 就是一张勾选表),树结构提供的额外信息量很有限。

### 6.3 一条容易被误判为「重」但其实是核心的:3.3 Spec 回写

看起来像「大团队才需要的文档纪律」,实际是**这套周期唯一的学习闭环**:核心原则第 5 条(`workflow.md:11`)、3.3 的「即使结论是没什么可更新也要走完判断」(`workflow.md:587`)、3.4 的 spec-sync preamble「spec 写入必须和代码在同一批提交里」(`workflow.md:591`)。没有它,周期跑一百遍,第一百零一遍还是从零开始 —— 而下一轮的 `implement.jsonl` 里能 curate 什么、`Pre-Development Checklist` 里能路由到什么,全部来自这一步的产出。轻量 harness 可以简化载体(一个 `NOTES.md` 而不是分层 spec 树),但**不能删掉「收尾时问一次:这次学到的东西该写去哪」这个动作**。

### 6.4 给轻量 harness 的最小移植集(从上面推导)

| 保留 | 形态建议 | 对应依据 |
|---|---|---|
| 任务目录 = 状态单元 | `tasks/<date>-<slug>/` 下 `task.json` + `prd.md` + 可选 `plan.md` + 可选 `research/` | C1 |
| 三个状态 + 单一写者 | `planning / in_progress / completed`,只有一个 CLI 能写 | C5 |
| 双门授权 | 建任务一次确认,start 一次确认 | C3 |
| 每回合注入 | 一个 UserPromptSubmit hook,从单一 Markdown 解析当前状态该说的话 | C4 |
| 强制步骤 ↔ 注入文本的一致性测试 | 一条断言:每个 `[required]` 步骤在对应状态块里被提到 | C4(b) |
| archive 作为唯一完成事件 | `finish` 只清指针,`archive` 才写 completed | C6 |
| 提交顺序契约 | 工作提交 → 归档提交 → 日志提交,禁 amend/push | C7 |
| 收尾学习回写 | 一个「这次学到什么、写去哪」的必答步骤 | 6.3 |

| 砍掉 | 理由 |
|---|---|
| 多平台条件块 | H1 |
| 会话身份解析层 | H2(单窗口用单文件指针) |
| 双 jsonl 清单 + 注入上限 | H3(不派子代理就不需要) |
| 开发者身份 + journal 轮转 + 全局 index | H4(保留「带真实 commit 哈希的日志」这一条纪律即可) |
| monorepo package/layer 分层 | H5 |
| 父子双向链接 | H6(用父 PRD 里的清单表替代) |

---

## 附录 A:本次实际读过的文件

**周期本体**
- `.trellis/workflow.md`(1-709,全文)
- `.trellis/config.yaml`(1-166,全文)
- `.trellis/.gitignore`(1-32,全文)
- `.trellis/.version`

**Agent 定义**
- `.trellis/agents/plan.md`、`implement.md`、`check.md`、`research.md`、`architect.md`(全文)

**任务实例(2 个逐文件)**
- `.trellis/tasks/08-05-session-identity-propagation/`:`task.json`、`prd.md`(1-89)、`implement.jsonl`、`check.jsonl`、`research/platform-session-identity.md`(1-45)、`research/actionability.md`(1-30);另 `research/code-side-mechanics.md` 仅统计行数
- `.trellis/tasks/archive/2026-08/08-10-full-trellis-ablation/`(归档):`task.json`、`prd.md`(1-80)、`design.md`(1-45)、`implement.md`(全 51 行)、`implement.jsonl`、`check.jsonl`;`research/` 仅列目录
- 另:全部 11 个活动任务的 `task.json`(全文)、全部 22 个 jsonl 的 curated/seed 计数
- 另:`.trellis/tasks/archive/2026-04/04-16-skill-first-refactor/`:`task.json`(全文)、`HANDOFF.md`(1-90)

**Workspace**
- `.trellis/workspace/index.md`(1-125,全文)
- `.trellis/workspace/taosu/index.md`(1-219,全文)
- `.trellis/workspace/taosu/journal-5.md`(1-120)

**Spec**
- `.trellis/spec/guides/index.md`(1-109,全文)
- `.trellis/spec/cli/backend/workflow-state-contract.md`(1-406,全文)
- `.trellis/spec/cli/backend/index.md`(1-86,全文)

**机制代码**
- `.trellis/scripts/task.py`(1-130、171-420)
- `.trellis/scripts/common/task_store.py`(295-700、1223-1423)
- `.trellis/scripts/common/task_context.py`(128-215)
- `.trellis/scripts/common/active_task.py`(1-120、734-800)
- `.trellis/scripts/common/tasks.py`(100-122)
- `.trellis/scripts/add_session.py`(1-60)
- `.claude/settings.json`(全文)
- `.claude/hooks/session-start.py`(415-545、860-930)
- `.claude/hooks/inject-subagent-context.py`(1160-1210 及关键行 grep)
- `.claude/commands/trellis/finish-work.md`(全文)、`continue.md`(全文)
- `.claude/skills/trellis-brainstorm/SKILL.md`(1-70)、`trellis-update-spec/SKILL.md`(1-60)

## 附录 B:未核实项

1. `.trellis/.version`(0.6.14)与 HEAD commit message(0.6.16)不一致的原因 —— 未查发布流程。
2. `test/regression.test.ts` 的实际内容:本次只读到 `workflow.md:113-118` 和 `workflow-state-contract.md:63, 305-318` 对它的**引用**,没有打开测试文件本身,因此「回归测试确实覆盖了这些不变量」是引用而非实证。
3. `inject-workflow-state.py`(488 行)只做了行号 grep,未逐行读;其解析逻辑以 `workflow-state-contract.md` 的描述为准。
4. `get_context.py --mode phase/packages/record` 的实际输出未运行(硬约束禁止运行会写入仓库的命令,且未运行只读命令以免误触),其行为以 `workflow.md:89-95, 299-304` 与 `common/workflow_phase.py`(242 行,未读)的描述为准。
5. 11 个活动任务中 9 个 jsonl 为空的原因(gate 之前创建 vs 用了 `--allow-empty-context`)无法从磁盘状态区分。
6. `.trellis/agents/*.md`(channel runtime)与 `.claude/agents/trellis-*.md`(平台 sub-agent)两套 agent 定义的关系:前者头部声明「spawned by `trellis channel spawn --agent implement`」(`.trellis/agents/implement.md:11`),后者未读。两者是否有内容同步机制未核实。
7. `.trellis/.template-hashes.json` 只看了大小(30KB),未读内容。
