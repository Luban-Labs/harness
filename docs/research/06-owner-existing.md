# owner 现有 harness 部件盘点 —— 以「项目周期链」为轴

调查日期 2026-09-10。全部只读。所有结论标注 `path:line` 或 `path#标题`;未读到的一律标「未核实」。

---

## 0. 一句话结论

owner 手上已经有一套**完整的「怎么干」层**(指令、派工、审查、安全),而且它的机械兜底比 Trellis 更硬;真正空的是**「干到哪了」层**——整条周期链上没有任何一个结构化、落盘、跨会话可读的任务状态文件,拆任务与续工两环全靠对话上下文和一份会话末快照撑着。新做的项目级 harness 应当**只补这一层**,不要重做指令层与审查层。

依据链见第 1、2、6 节。

---

## 1. 按 harness-creator 五子系统盘点

基准定义:`/Users/sangba/Downloads/02-代码脚本/工具脚本/harness/harness-creator/SKILL.md:22-31`(五子系统表:Instructions / State / Verification / Scope / Lifecycle,各自的 minimal artifact 与 purpose)。交付清单基准 `SKILL.md:100-111`。

### 1.1 Instructions —— 覆盖充分,且有两层机械兜底(唯一超出基准的子系统)

| 承担者 | 出处 | 干什么 |
|---|---|---|
| 用户级宪章 | `/Users/sangba/.claude/CLAUDE.md`(41 行,分 原则/工作流/对抗性审查/外部输入与凭据安全/风格/记忆/稳定约束 七节) | 跨项目不变的工作方式与红线 |
| 按路径注入的规则集 | `/Users/sangba/.claude/rules/*.md`,每份带 frontmatter `paths:`(如 `rules/architecture.md:1-13`、`rules/coding-minimal.md:1-5`、`rules/python.md:1-5`、`rules/frontend.md:1-6`、`rules/reverse-api.md:1-9`、`rules/design-doc.md:1-12`、`rules/doc-writing.md:1-10`) | 只在碰到匹配文件时才进上下文 = progressive disclosure |
| 常驻风格 | `/Users/sangba/.claude/rules/output-style.md`(5 行,**无 frontmatter**,故全局常驻) | 回复口径 |
| 派工契约 | `/Users/sangba/.claude/os/MODELS.md`(粒度 :4-6、缓存 :9-11、模型特征 :14-20)、`/Users/sangba/.claude/os/WORKERS.md`(通道 :6、档位 :10-15、调用参数 :17-20、任务包 :22-26) | 子代理/codex 工人怎么派、怎么续 |
| 项目级指令 | 各项目根 `CLAUDE.md` / `AGENTS.md`,例:`/Users/sangba/Downloads/02-代码脚本/工具脚本/dashboard/CLAUDE.md:1-30` | 项目背景、真源、红线 |
| 机械兜底 ① | `/Users/sangba/.claude/hooks/doc-filler-guard.sh:1-3`(PreToolUse 拒绝废话模式;PostToolUse 只提醒)、`:12-19`(按路径分 rules/os/charter/cmd 四类)、`:21-28`(尺寸预算:rules 3072B、charter 6144B、os 7168B) | 制度文件不许灌水、不许膨胀 |
| 机械兜底 ② | `/Users/sangba/.claude/hooks/institution-refcheck.py:1-17`(悬空章节引用 / 悬空路径引用 / 承重锚点丢失三查)、`:28-42`(ANCHORS 写死的外部参照)、`:44`(WATCH 范围 CLAUDE.md、os/、commands/、agents/、rules/) | 制度文件互相引用不许烂尾 |

**判断:不空缺,且强于基准。** harness-creator 的 Instructions 只要求一个 `AGENTS.md`/`CLAUDE.md`(`SKILL.md:26`),owner 的 rules `paths:` 前置匹配 + 两个 hook 兜底,比单文件方案更省上下文也更抗漂移。

**唯一的洞:没有「Startup Workflow」。** 基准模板 `harness-creator/templates/agents.md:5-16` 要求一段可执行开场序列(`pwd` → 读本文件 → 读项目文档 → 跑 `./init.sh` → 读 `feature_list.json` → `git log -5`)。owner 的 `CLAUDE.md` 通篇是判据与红线,没有任何「开工先做这 N 步」;`dashboard/CLAUDE.md:12-16` 有「阶段与闸门」,但那是 Trellis 在管(见 1.5 与第 3 节)。

### 1.2 State —— **空缺(最大的一个)**

基准要求 `feature_list.json` + `progress.md`:当前功能、状态、证据、下一步(`harness-creator/SKILL.md:27`;字段定义 `templates/feature-list.schema.json:25-40` 的 `dependencies` / `status`(not-started|in-progress|blocked|done) / `evidence`;日志形态 `templates/progress.md:1-51`)。

owner 侧只有两种持久物,都不是任务状态:

1. **会话末交接笔记** —— `/Users/sangba/.claude/commands/handoff.md:12-16`(落盘位置三级:用户点名 > 仓库主工作树根 `HANDOFF.md` > `~/.claude/handoffs/YYYY-MM-DD-<主题>.md`);实际存在两份 `/Users/sangba/.claude/handoffs/2026-08-24-website-publish-topic-research.md`、`2026-09-02-aio-workbench.md` 加一个 `archive/`。它是**会话末快照**,不是持续台账:`handoff.md:8` 明写「本轮只写交接笔记,不开新活」。
2. **pm 模式布尔 marker** —— `/Users/sangba/.claude/hooks/pm-mode-state.py:7`(`~/.claude/pm/state/`)、`:37`(见到 `/pm` 就 `marker.touch()`)。只记「在不在 pm 模式」,不记任何任务内容,且 `:24-25` 在 SessionEnd 直接删除、`:8` TTL 72 小时。

另外 `~/.claude/pm/reports/` 下有 19 个文件(如 `2026-09-06-harness-audit/A7-pm-ledger.md`),但那是某次审计的一次性产物,`commands/pm.md` 与 `pm/TEMPLATES.md` 里都没有任何条文规定要维护它 —— 不是常设机制。

项目侧唯一像台账的是人手约定:`dashboard/CLAUDE.md:9`「进度真源是 `HANDOFF.md`(交接)与 `进度.md`(派工台账)」—— 靠一句项目 CLAUDE.md 的话维系,没有 schema、没有校验、没有注入。

**判断:空缺。** 没有 `feature_list.json` 等价物,没有 `progress.md` 等价物,没有「当前任务指针」。

### 1.3 Verification —— 覆盖厚,但全在「派人审」侧;「跑命令」侧空缺

已有(制度层):

- 终审外派、不自己审自己:`CLAUDE.md:23`(代码改动派 codex `adversarial-review`,文档/制度/方案派 `adversarial-reviewer`;只有 blocking 必修,verdict 只看 blocking 数)。
- 只审一轮:`CLAUDE.md:24`。
- 文档定稿也审,但只限跨层设计与制度文件,任务级规划文档不审:`CLAUDE.md:25`。
- 完成的定义:`CLAUDE.md:26`「凡声称完成,交付 owner 能亲自核验的可观察产物(真实跑通截图/抓包数字/GUI 演示/端到端 live 结果),不以『另一个 agent 说没问题』结案」。
- 证据契约:`os/WORKERS.md:31`(Verification 为真实输出、Evidence 绑定最终候选、证据优先序「可复跑输出 > diff/快照 > 截图/抓包 > 自述」)、`:34`(验后再改 = 证据作废重跑)。

已有(执行者规格):`/Users/sangba/.claude/agents/adversarial-reviewer.md` 是这套里最精密的一件——`:1-8` 只读工具集(Read/Grep/Glob/Bash)+ opus/high + `memory: false`;`:16-20` 审查顺序把「验收标准逐条核对(防假完成)」放第一;`:31` 证据三态 CONFIRMED/PLAUSIBLE/⚠️;`:32` blocking 三件套;`:36-43` 假阳性清单;`:45-50` 输出格式与 verdict 规则。

已有(机械层,`/Users/sangba/.claude/settings.json#hooks`):

- `PostToolUse(Edit|Write|MultiEdit)` 第一块内联 bash:把改过的文件追加进 `~/.claude/state/edited/<SID>.touched`;`Stop` 第一块内联 bash:对累计文件按后缀跑 `ruff check --fix` / `ruff format` / `mypy`(.py)与 `biome format --write`(.ts/.tsx/.js/.jsx),跑完清空累计文件。这是一条**真实存在的「停下之前先过一遍静态检查」链路**。
- `/Users/sangba/.claude/hooks/file-size-budget.sh:1-4`(行数预算,exit 2 非破坏回喂模型)、`:19-21`(500 行,测试目录 800 行)。

**空缺:项目级验证命令登记处(`init.sh` 等价物)。** 基准 `harness-creator/templates/init.sh:1-78` 是「一条命令跑完这个项目全部验证」,并在 `templates/agents.md:52-60` 被写进指令文件。owner 侧的验证命令是散的:`rules/python.md:9`(依赖只走 `uv`、`uv run`)、`rules/reverse-api.md:27`(外部 API 改动必须 playwright-cli 抓真包 + live 测试)、各项目 CLAUDE.md 里零散提及。新会话没有统一入口知道「这个项目声称完成前该跑哪几条」。

### 1.4 Scope —— 规则层与安全层覆盖,任务层空缺

已有:

- **开工闸门**:`/Users/sangba/.claude/commands/kickoff.md:10-13`(未放行禁止产出实现物,调研手段例外:scratchpad 笔记、只读 clone、≤50 行用完即弃 spike)、`:15-19`(「组件」按结构判不按名字判;用户没敲命令但命中触发也执行)、`:23-26`(调研深度分级)、`:36-41`(交付格式,末尾列「确认后要做的前 3 步」`[step] → verify: [check]`)。触发行在 `CLAUDE.md:7`。
- **不做项前置**:`rules/design-doc.md:13`(只写五节:目标一句、最短验收演示、范围与不做项、最小路径、未知与验证动作)、`:14`(每个功能后面跟出处)、`:18`(审查设计文档只报多余,不报缺失)。
- **派工写域**:`os/WORKERS.md:23` 任务包首包字段含 `Write scope` / `Do not touch` / `越写域即 BLOCKED`;`:25` 受托编排时「一文件一 owner」。
- **物理隔离**:`CLAUDE.md:19` Worktree 隔离;`os/WORKERS.md:34`「写域可能碰撞或主树有未提交改动 → 开 worktree」。
- **机械闸**:`hooks/public-push-guard.sh:1-4`(PreToolUse Bash,拦公开仓 push,`PUBLIC_PUSH_OK=1` 知情放行)、`hooks/subagent-model-guard.sh:3`(子代理禁 fable 与 fork)、`hooks/workflow-agent-cap.sh:1-11` + `hooks/workflow-cap`(内容 `8`,Workflow 脚本不带 `agentCapped` 前奏即 exit 2 拒收)。

**空缺:任务级 scope 不落盘。** 基准 `harness-creator/SKILL.md:29` 的 Scope = 「feature dependencies and done criteria」,即 `feature-list.schema.json:25-31` 的 `dependencies` 数组与逐条 done 判据。owner 的 Write scope 只在派工那一刻活在提示词里(`WORKERS.md:23`),任务做完就消失,下个会话拿不到;`CLAUDE.md:14` 的「多步任务列计划 `[step] → 执行者 → verify: [check]`」也只活在对话里。

### 1.5 Lifecycle —— 收尾/续工有闭环,开工侧半空

已有(**owner 这套里最完整的一件**,写入端与消费端都在,且互相点名):

- 写入端 `/Users/sangba/.claude/commands/handoff.md`:`:9` 无可交接的判据;`:12-16` 落盘位置;`:18` 目标文件已存在时的归档规则(不许直接覆盖丢状态);`:20` 落仓库根时确认 `HANDOFF.md` 进 `.gitignore` 且任何情况下不 commit;`:24-35` 内容要求(读者是零前情新会话,含「当前判断」「卡点」「坑」「下一步 `[step] → verify: [check]`」「脱敏优先于照抄」);`:39` 笔记末尾固定归档提示行;`:43-45` 触发细则(用户没敲命令但表达等价意图也执行;工作明显要跨会话时直接写一份,不等应答)。
- 消费端 `/Users/sangba/.claude/hooks/handoff-check.sh`:`:1-4` 声明(SessionStart 发现 `HANDOFF.md` / `~/.claude/handoffs/*.md`,按首部 `<!-- cwd: ... -->` 过滤,只给同目录会话列详情);`:41-56` 按笔记年龄分档(≤7 天列详情、≤30 天只提一句、>30 天只计数);`:58` 拼出的提示语明确要求「开工前先判断它与本次任务是否同一摊活」;`:66` 用 `jq -n` 输出 `hookSpecificOutput.additionalContext` 注入上下文。
- 两端闭环在 `handoff.md:10` 被明写(还带 Pi 侧的 `~/.pi/agent/extensions/handoff-reminder.ts`,未核实)。
- 会话级清理:`settings.json#hooks.SessionEnd` 第一块内联 bash 删 `~/.claude/state/edited/<SID>*`;`handoff-check.sh:6` 顺手清 7 天前残留。
- 跨会话知识回写:`CLAUDE.md:39`(可复用结论 append 一行进 `~/Documents/Obsidian Vault/INBOX.md`);与交接笔记的分界在 `handoff.md:45`(「可复用的长期结论进 memory,一次性的『干到哪了』进交接笔记」)。

**空缺 ①:开工侧没有内容。** SessionStart 位上只有 `handoff-check.sh`,它注入的是「上次留下的笔记」,不是「这个项目现在的任务、阶段、验证基线」。等价于基准 `templates/agents.md:5-16` 的 Startup Workflow 缺位。

**空缺 ②:没有承载任务状态的 per-turn 通道。** 通道本身**已经存在并验证可用**——`hooks/pm-mode-state.py:43-45` 在 UserPromptSubmit 上 `print(REMINDER)` 把一句话推进每一轮上下文——但它只推 `:9` 那一句固定文本(「PM 模式:不亲自实现,派工/验收/汇报按 ~/.claude/commands/pm.md」)。owner 自己在 `commands/pm.md:10` 承认了这个坑:「压缩后看到 [pm-mode] 提醒而本文件已不在上下文时,先重读本文件再干活」。也就是说 owner 已经踩过「压缩丢状态」,只给「模式」做了 breadcrumb,没给「任务」做。

### 1.6 五子系统小结表

| 子系统 | owner 现状 | 承担者 | 缺口 |
|---|---|---|---|
| Instructions | **强于基准** | CLAUDE.md + rules/(paths 前置匹配)+ os/ + doc-filler-guard.sh + institution-refcheck.py | 无 Startup Workflow |
| State | **空缺** | 仅交接笔记(会话末快照)+ pm 布尔 marker | 无任务台账、无当前任务指针、无 evidence 字段 |
| Verification | 制度与审查强,机械层有 lint;**命令登记空缺** | CLAUDE.md:23-26 + adversarial-reviewer.md + Stop hook lint 链 + file-size-budget.sh | 无 `init.sh` 等价物 |
| Scope | 规则/安全层强;**任务层空缺** | kickoff.md + design-doc.md:13 + WORKERS.md:23 + 三个 guard hook | dependencies / done criteria 不落盘 |
| Lifecycle | 收尾+续工有闭环;**开工侧半空** | handoff.md ⇄ handoff-check.sh(闭环)+ pm-mode-state.py(通道空载) | 无开工注入、无任务级 per-turn breadcrumb |

**旁证:`~/.claude/os/scripts/` 与周期链无关。** 该目录只有三个文件:`t1_event_gate.py:1-2`(「Reject stale or unsorted T1 event cards before Feishu delivery」,飞书晨报业务闸)、其单测 `test_t1_event_gate_green.py:1-2`、卡片模板 `t1_card_template.json:1-9`。不是 harness 部件。

---

## 2. 按周期链逐环盘点

图例:**制度** = 靠 CLAUDE.md/命令文件的文字约束;**机械** = 有 hook/脚本强制;**外派** = 有专门的执行者规格。

| 环 | 现成机制 | 类型 | 出处 | 缺什么 |
|---|---|---|---|---|
| 开工 | `/kickoff` 调研闸门(四选一:复用/二开/引用契约/自建) | 制度(闸门语义靠模型自觉,无 hook) | `commands/kickoff.md:10-13`、触发行 `CLAUDE.md:7` | 只在「新组件/新依赖」时触发(`kickoff.md:15-19`),不是每次开工都走;窄改动明确不过闸(`CLAUDE.md:7`) |
| 开工 | SessionStart 注入旧交接笔记 | **机械** | `hooks/handoff-check.sh:1-4`、`:66` | 注入的是上次的笔记,不是项目当前状态 |
| 开工 | Brainstorm 先于代码 | 制度 | `CLAUDE.md:13` | 无落盘要求 |
| 需求澄清 | 问题塑形 + 双层 map(owner 方向 map / 内部交付图) | 制度 | `commands/pm.md:17-22` | 只在 `/pm` 模式内生效;map 不落盘 |
| 需求澄清 | `/pp` 装备库挑澄清工具(01 苏格拉底式提问) | 制度(纯手动) | `commands/pm.md:18` 指向 `/pp`;`commands/pp.md:18` | 手动触发,`pp.md:5` `disable-model-invocation: true` |
| 需求澄清 | 设计文档五节写法 | 制度 + **半机械** | `rules/design-doc.md:13-18`;paths 里含 `**/.trellis/tasks/**/*.md`(`rules/design-doc.md:10`)故编辑 Trellis 任务文档时自动注入 | 无「澄清完成」判据 |
| 拆任务 | 多步任务列计划 `[step] → 执行者 → verify: [check]` | 制度 | `CLAUDE.md:14` | **不落盘**;`kickoff.md:40`、`handoff.md:31` 用同一格式但也只在文档里 |
| 拆任务 | 任务包字段集(Task ID / Write scope / Verification / Result format) | 制度 | `os/WORKERS.md:23`;派工模板 `pm/TEMPLATES.md:9-16`(plan/implement/governance/research 四类) | 任务包是**一次性提示词**,不是可查询的任务对象;无父子任务、无依赖 |
| 拆任务 | Workflow 代理上限 | **机械** | `hooks/workflow-agent-cap.sh:1-11`、`hooks/workflow-cap`=8;制度行 `CLAUDE.md:15` | 管的是并发预算,不是任务分解 |
| 实现 | 按路径注入的编码规则 | **机械**(paths 匹配) | `rules/coding-minimal.md:1-5`、`rules/architecture.md:1-13`、`rules/python.md`、`rules/frontend.md`、`rules/reverse-api.md` | — |
| 实现 | 派工分流(codex luna/sol/astra、子代理 opus/sonnet) | 制度 + **机械** | `os/MODELS.md:14-20`、`os/WORKERS.md:10-20`;硬闸 `hooks/subagent-model-guard.sh:3` | — |
| 实现 | Worktree 隔离 | 制度 | `CLAUDE.md:19`、`os/WORKERS.md:34` | 无 hook 强制 |
| 实现 | 文件行数预算 | **机械** | `hooks/file-size-budget.sh:19-21` | — |
| 实现 | Debug 两轮外派 | 制度 | `CLAUDE.md:20` | 「按请求累计」的计数无人维护(无状态文件) |
| 验证/审查 | 对抗审终审外派 | **外派** + 制度 | `CLAUDE.md:23-25`、`agents/adversarial-reviewer.md` 全文、`os/WORKERS.md:14`(codex `adversarial-review` 子命令) | 触发靠自觉,无 Stop hook 强制 |
| 验证/审查 | Stop 时 ruff/mypy/biome | **机械** | `settings.json#hooks.Stop` 第一块 + `#hooks.PostToolUse` 第一块(累计文件) | 只有 lint/type,没有项目自定验收命令 |
| 验证/审查 | 完成必须给 owner 可核验产物 | 制度 | `CLAUDE.md:26`、`os/WORKERS.md:31`(证据优先序) | 无机械核对 |
| 验证/审查 | 公开推送闸 | **机械** | `hooks/public-push-guard.sh:1-4`;制度行 `CLAUDE.md:43` | — |
| 收尾/交接 | `/handoff` 写笔记 | 制度(触发细则含「不等用户应答直接写」`handoff.md:44`) | `commands/handoff.md` 全文 | 无「未写交接就 Stop」的兜底 |
| 收尾/交接 | 跨项目知识回写 INBOX | 制度 | `CLAUDE.md:39` | — |
| 续工 | SessionStart 发现笔记并注入 | **机械** | `hooks/handoff-check.sh:41-58`(按 7/30 天分档)、`:66` | 只在 SessionStart 一次;压缩后不再提醒 |
| 续工 | pm 模式跨轮提醒 | **机械** | `hooks/pm-mode-state.py:43-45` | 只承载一句固定文本,不含任务状态 |

**两处「靠文字撑着、没有兜底」的环:需求澄清、拆任务。** 这两环是全链上唯一没有任何 hook 参与的:澄清全在 `pm.md:17-22` 和 `pp.md`,拆任务全在 `CLAUDE.md:14` 一行 + `WORKERS.md:23` 的提示词字段集。

---

## 3. 层级:什么在用户级,什么在项目级

### 3.1 用户级(`~/.claude/`,所有项目生效)

`CLAUDE.md`、`rules/`(8 份)、`os/`(MODELS.md、WORKERS.md、scripts/)、`commands/`(handoff、kickoff、pm、pp)、`agents/`(仅 `adversarial-reviewer.md`)、`hooks/`(8 个脚本 + `workflow-cap` + `public-repos.list` + `tests/` 四份用例)、`skills/`(36 个,含 `skill-smith`)、`settings.json`、`pm/`(TEMPLATES.md + templates/ 四份 + state/ + reports/)、`handoffs/`。

即:**周期链上的机制,今天 100% 在用户级。**

### 3.2 项目级现状 —— 这一层今天几乎全被 Trellis 占着

抽查三个项目,`.claude/` 内容**完全同构**:

- `/Users/sangba/Downloads/02-代码脚本/工具脚本/news/.claude/`、`/Users/sangba/Downloads/02-代码脚本/工具脚本/dashboard/.claude/`、`/Users/sangba/Downloads/06-自媒体/.claude/` 三处都有:`agents/trellis-implement.md`、`agents/trellis-check.md`、`agents/trellis-research.md`;`hooks/session-start.py`、`hooks/inject-workflow-state.py`、`hooks/inject-subagent-context.py`;`commands/trellis/`;`skills/trellis-*`(spec-bootstrap、before-dev、brainstorm、break-loop、session-insight、check、meta、channel、update-spec 等)。
- 项目 `settings.json` 三处逐字相同:`news/.claude/settings.json:5-70` = `dashboard/.claude/settings.json:5-70`,挂 `SessionStart`(startup/clear/compact 三个 matcher 各跑 `session-start.py`)、`PreToolUse`(matcher `Task` 与 `Agent` 各跑 `inject-subagent-context.py`)、`UserPromptSubmit`(跑 `inject-workflow-state.py`)。
- 项目根 `CLAUDE.md` 里有 Trellis 托管块:`dashboard/CLAUDE.md:32-52`(`<!-- TRELLIS:START -->` … `<!-- TRELLIS:END -->`,`:50` 明写「edits inside may be overwritten by a future `trellis update`」)。
- 项目级 owner 自写内容只有两类:`dashboard/CLAUDE.md:1-30`(项目背景、五层结构、阶段与闸门、红线、脱敏口径)和 `06-自媒体/.claude/rules/*.md`(共享惯例、发布合规、视频、平台-小红书、封面、稿件 六份业务规则)。

`.trellis/` 覆盖面很广:`find` 到 9 个项目带 `.trellis`(ai-content-factory、06-自媒体、speach_coach、anything-analyzer、dashboard、news、ai-cognitive-radar-plan、ai-cognitive-radar-Loop_exp、price_fatcher)。

### 3.3 结论:新 harness 该放哪一层

**放项目级,并且是「替换 Trellis 那套目录」,不是「在它旁边再加一层」。** 三条依据:

1. **用户级已经装满「怎么干」,再加就撞尺寸预算。** `hooks/doc-filler-guard.sh:21-28` 给 CLAUDE.md 定死 6144 字节、rules 3072、os 7168,当前 `CLAUDE.md` 5599 字节(仅剩 ~545 字节余量)。`rules/doc-writing.md:17` 同一条口径,`:14`「入一条先删一条」。用户级没有空间承载项目状态语义。
2. **周期状态天然按项目变。** 用户级件全是跨项目不变量(派工契约、审查纪律、安全红线);「当前任务是什么、验收怎么跑、范围到哪」每个项目都不同,放用户级必然要参数化,违反 `rules/doc-writing.md:15`「不为可能的未来加条款,不给单一实现分档位」。
3. **项目级这个位子已经有占用者,同位竞争而非叠加。** Trellis 已经把 `SessionStart` / `UserPromptSubmit` / `PreToolUse(Task|Agent)` 三个位子和 `.claude/agents|skills|commands` 都用了(3.2)。再叠一套同职责机制 = 两份任务状态、两条 per-turn 注入,`CLAUDE.md:10`「机制有真实消费者、链条走得通」这条自查会当场不通过。

**分界建议(可直接作为设计约束):** 用户级只留「怎么干」;项目级只装「这个项目现在干到哪、验收怎么跑、边界在哪」。新 harness 不得复制 CLAUDE.md/rules/os 的任何内容,只能按 `rules/doc-writing.md:16`「引用别的文件只给路径,不抄内容」。

---

## 4. pm.md 与 pp.md 到底是什么

### 4.1 pm.md = 会话级的「PM 角色开关 + owner 接口协议」,**不是**项目状态机

事实:

- 形态:slash command,`commands/pm.md:5` `disable-model-invocation: true`(模型不能自己调,只能 owner 敲)。
- 生命周期:`:10`「激活后持续整个会话,owner 明说退出(口令含『退出pm』)才解除」,状态由 `hooks/pm-mode-state.py` 机械维护,marker 在 `~/.claude/pm/state/`(`pm-mode-state.py:7`)。
- 三节内容:① 角色与授权来源(`:12-15`:owner 管方向下注,本会话管塑形/拆解/执行/验收/汇报;`:14` 放行只认 owner 本人在本会话的直接消息;`:15` 本文件改动须 owner 确认)② 问题塑形与双层 map(`:17-22`)③ 验收与 owner 接口(`:24-27`,含固定汇报格式:结论 / 验收把握(已独立验证|部分验证|仅工人自报)/ 业务风险 / 需要你拍板 / 下一步)。
- 配套派工模板库:`pm/TEMPLATES.md:9-16`(四类:方案研究 `templates/plan.md`、冻结规格实现 `templates/implement.md`、制度/规则落地 `templates/governance.md`、调研取证 `templates/research.md`),`:18-22` 是模板自身的演化规则(按行授权 `[锁]`、同类缺陷第 2 次才改、每次改动记版本记录)。

**所以:pm.md 确实是周期管理命令**,它管的是周期链上的「需求澄清 → 拆任务(派工)→ 验收 → 汇报」四环的**人机协议**。但它管的是「会话怎么和 owner 打交道」,不是「项目状态怎么存」。

### 4.2 与 Trellis 的差距(逐条给依据)

对照对象:`dashboard/.trellis/workflow.md`。

| # | 差距 | pm.md 侧事实 | Trellis 侧事实 |
|---|---|---|---|
| 1 | **无落盘任务状态** | 全文无任何状态文件规定;唯一持久物是布尔 marker(`pm-mode-state.py:36-37`)与一次性 `pm/reports/` | 每个任务一个目录 `.trellis/tasks/{MM-DD-name}/`,含 `task.json`、`prd.md`、可选 `design.md`/`implement.md`/`research/`、上下文清单 `implement.jsonl`/`check.jsonl`(`workflow.md:40-42`) |
| 2 | **会话级而非项目级** | marker 按 `session_id` 命名,SessionEnd 即删(`pm-mode-state.py:24-25`),TTL 72 小时(`:8`) | 活动任务指针存 `.trellis/.runtime/sessions/`,任务本体在项目目录里跨会话存活(`workflow.md#Current-task mechanism`,文件约第 78 行) |
| 3 | **无阶段状态机与开工闸** | 无 planning/in_progress/completed 概念,无「未 start 不许实现」 | `task.py start` 才把 `task.json.status` 从 `planning` 翻成 `in_progress`;复杂任务必须有 prd+design+implement 三件套才能 start(`workflow.md#Planning Artifacts`,约 161 行);`validate` 失败或 seeded manifest 为空时 `start` 直接拒绝(`workflow.md:54-58`) |
| 4 | **per-turn 注入是空载的** | breadcrumb 只推一句固定文本(`pm-mode-state.py:9` + `:45`) | UserPromptSubmit 每轮按当前状态从 `workflow.md` 的 `[workflow-state:*]` 块取正文注入,块本身是 single source of truth(`workflow.md:101-145` 的契约注释;`no_task` 块见 `:120-124`);hook 在 `dashboard/.claude/settings.json:60-70` |
| 5 | **无任务树 / 无子任务** | 只有「内部交付图」这个口头概念(`pm.md:20`),不落盘 | 父子任务 + `add-subtask`/`remove-subtask`(`workflow.md#Parent / Child Task Trees`,约 169 行;命令见 `:68-71`) |
| 6 | **无跨会话工作日志** | 无 | `.trellis/workspace/<developer>/journal-N.md` + `index.md`,`add_session.py` 追加,2000 行自动轮转(`workflow.md#Workspace System`,约 80 行) |
| 7 | **无子代理上下文注入** | 派工靠人写任务包(`WORKERS.md:23`),每次手写 | `PreToolUse(Task|Agent)` 跑 `inject-subagent-context.py` 自动把任务上下文塞进子代理(`dashboard/.claude/settings.json:38-58`),预算可配(`.trellis/config.yaml:132-146`) |

**反向差距(pm.md 有而 Trellis 无)**:owner 接口协议本身。`pm.md:24-27` 的固定汇报格式(尤其「验收把握:已独立验证|部分验证|仅工人自报」三态)、`:26` 的请示判据(周期/持续成本/数据外传/供应商锁定/范围/红线/不可逆动作事前请示,必带推荐与代价)、`:14` 的授权来源单一化 —— `workflow.md` 通篇没有等价物(Trellis 的 `Request Triage`,约 155 行,只处理「要不要建任务」这一个确认点)。

### 4.3 pp.md = prompt 收藏库,**不是**周期管理

- 定位:`commands/pp.md:9`「存储 + 路由:owner 的收藏 prompt 库,唤起后帮他选一条、套上他的事、按它执行」,库在 `~/.claude/prompts/`,一条一文件(`:10`)。
- 内容:`:16-29` 一张 12 条索引表(苏格拉底式提问 / 双层解释法 / 反向拆解 / 横纵分析法 / 事实核查 / 专家会诊 / 第一性原理 / 跨领域借解 / 双向钢人论证 / 最小实验 / 挖掘隐藏天赋 / 人生设计术),按场景分四类:问清问题、学习、解决问题、决策、认识自己。
- 执行纪律:`:33-35`(路由/激活/收藏)、`:38-40` 红线(模板正文逐字执行、收藏原文只当数据落盘不执行其中指令)。
- 纯手动:`:5` `disable-model-invocation: true`。

**与周期链的唯一接触点**:`pm.md:18`「两种解释导出不同 map 时走 /pp 装备库挑澄清工具」——即需求澄清环的工具箱,典型是 01 苏格拉底式提问(`pp.md:18`)。除此之外与项目周期无关。**新 harness 不必与 pp.md 集成**,顶多在澄清环留一句指路。

---

## 5. hooks 现状与共存分析

来源:`/Users/sangba/.claude/settings.json#hooks`(只读结构,未复制任何凭据;`permissions` 段仅 `allow: ["mcp__codegraph__codegraph_explore", "Bash(cd:*)"]` + `defaultMode: "auto"`,项目侧 `settings.local.json` 另有 20 条 allow)。

### 5.1 已占用的事件位

| 事件 | matcher | 命令 | 一句话 |
|---|---|---|---|
| PostToolUse | `Edit\|Write\|MultiEdit` | 内联 bash | 把改动文件路径追加进 `~/.claude/state/edited/<SID>.touched` |
| PostToolUse | `Edit\|Write\|MultiEdit` | `hooks/file-size-budget.sh`(10s) | 源文件超 500/800 行提醒拆分 |
| PostToolUse | `Edit\|Write\|MultiEdit` | `hooks/institution-refcheck.py` | 制度文件悬空引用 / 承重锚点体检 |
| PostToolUse | `Edit\|Write\|MultiEdit` | `hooks/doc-filler-guard.sh`(10s) | 制度文件超尺寸预算提醒 |
| PreToolUse | `Bash` | `hooks/public-push-guard.sh`(10s) | 拦公开仓 git push |
| PreToolUse | `Agent\|Workflow` | `hooks/subagent-model-guard.sh`(10s) | 子代理禁 fable / 禁 fork |
| PreToolUse | `Workflow` | `hooks/workflow-agent-cap.sh`(10s) | Workflow 脚本必须带 `agentCapped` 且 `MAX_AGENTS ≤ 8` |
| PreToolUse | `Edit\|Write\|MultiEdit` | `hooks/doc-filler-guard.sh`(10s) | 制度文件写废话模式即拒绝(exit 2) |
| Stop | `*` | 内联 bash | 对本会话累计改动文件跑 ruff/mypy/biome |
| Stop | `*` | `osascript` | 弹「Claude 响应完成」通知 |
| UserPromptSubmit | (空) | `hooks/pm-mode-state.py`(10s) | 维护 pm 模式 marker,激活中每轮 print 一句提醒 |
| SessionStart | (空) | `hooks/handoff-check.sh`(10s) | 发现交接笔记并注入 additionalContext |
| SessionEnd | (空) | 内联 bash | 清 `state/edited/<SID>*` |
| SessionEnd | (空) | `hooks/pm-mode-state.py`(10s) | 删 pm marker |
| PostToolUseFailure / SubagentStart / SubagentStop / Notification / PermissionRequest / PreCompact | (空) | `~/.codeisland/codeisland-hook.sh` | 第三方(codeisland)统一挂在**每一个**事件上;Notification 与 PermissionRequest 的 timeout 是 300s |

`~/.codeisland/codeisland-hook.sh` 挂满 12 个事件(PostToolUse/PreToolUse/Stop/PostToolUseFailure/UserPromptSubmit/SubagentStart/SubagentStop/SessionStart/Notification/PermissionRequest/PreCompact/SessionEnd),其行为未核实(脚本在 `~/.codeisland/` 下,本次未读)。

**空着没人用的事件位:无。** 但 SubagentStart / SubagentStop / PreCompact / PostToolUseFailure 这四个位上只有 codeisland 一家,是新 harness 最省事的落点。

### 5.2 共存规则与三个真实冲突点

**共存是可行的,且 owner 已经在四个事件上并列多条**(PostToolUse 4 块、PreToolUse 4 块 + codeisland、SessionEnd 3 块、UserPromptSubmit 2 块)。同一事件可挂多个 matcher block,同一 block 可挂多个 command;项目级 `.claude/settings.json` 是独立文件,与用户级合并生效 —— `news/.claude/settings.json:5-70` 与用户级同时在跑就是现成证据。

新 harness 若要加 hook,三处必须写进设计:

1. **UserPromptSubmit 的 stdout 会拼进上下文,已有一位租客。** `pm-mode-state.py:45` 用 `print(REMINDER)` 输出。新 hook 再 print 就是两条并列噪音,且 pm 模式与项目任务状态可能同时激活。要么合并成一条注入,要么明确分工(pm 说角色、harness 说任务),不要各喊各的。
2. **PreToolUse 的 `Agent` matcher 已被 `subagent-model-guard.sh` 占,且 exit 2 语义是阻断。** 新 hook 若也拦 `Agent`(比如注入任务上下文),必须确保自身**永不** exit 2 —— 同一事件任一 hook exit 2 即阻断整个调用。注意用户级用的是 `Agent|Workflow`,而 Trellis 项目级用的是 `Task` 与 `Agent` 两个独立 matcher(`news/.claude/settings.json:38-58`),命名不一致,新 harness 要按实测确定当前版本的工具名,别照抄。
3. **Stop 位已有一个无 timeout 的重活。** `settings.json#hooks.Stop` 第一块内联 bash 会对本会话所有改动文件顺序跑 ruff+mypy(或 biome),没有设 timeout。若新 harness 想在 Stop 做「完工前强制验证/强制写状态」,它排在这条之后,会叠加每轮结束的等待时间;建议改用轻量检查(只读状态文件 + 提醒),重活留给已有那条。

另外两条约束:

- 用 Workflow 编排必须自带 `agentCapped` 前奏,否则 `hooks/workflow-agent-cap.sh:1-11` 直接 exit 2 拒收;闸值在 `hooks/workflow-cap`(现为 `8`),改闸值要先请示 owner 并记账(`CLAUDE.md:15`)。
- 新 harness 自己的 hook 若要改 `settings.json`,注意 `CLAUDE.md:38`「CLAUDE.md 本身的修改永远人工确认」只约束 CLAUDE.md;但 hooks 属于「共享基建」,`CLAUDE.md:34` 要求危险操作前确认。
- 已有 hook 都配了用例:`~/.claude/hooks/tests/` 下 `doc-filler-cases.sh`、`model-guard-cases.sh`、`push-guard-cases.sh`、`workflow-cap-cases.sh` —— 新 hook 按同惯例补一份用例,是这套里的既定做法。

---

## 6. 判断:最大空缺 与 已有等价物

### 6.1 最大空缺(按「Trellis 有而 owner 没有」的视角,按严重度排序)

**空缺 1 —— 任务状态没有落盘真源(拆任务环 + 续工环同时失守)**

- 依据(owner 侧无):全链只有两种持久物,`commands/handoff.md:12-16` 的会话末笔记与 `hooks/pm-mode-state.py:36-37` 的布尔 marker;`CLAUDE.md:14` 的「多步任务列计划」和 `os/WORKERS.md:23` 的任务包字段集都只活在对话/一次性提示词里。
- 依据(Trellis 有):`workflow.md:40-42` 每任务一目录 + `task.json`;`workflow.md#Current-task mechanism` 的 per-session 活动任务指针;`workflow.md:5-12` 的核心原则第 3 条明写「Persist everything — conversations get compacted, files don't」。
- 后果具体化:会话被压缩或崩掉时,「这摊活拆成了哪几步、哪几步做完了、证据在哪」全部丢失,只能等到会话末才由 `/handoff` 补一次快照;中途中断就什么都没有。`commands/pm.md:10` 对压缩失忆的补丁(「先重读本文件」)只覆盖模式,不覆盖任务。
- 这一项同时解释了为什么周期链第 3 环(拆任务)是全链唯一零机械的环。

**空缺 2 —— 状态注入只有半边:开工侧空,per-turn 通道空载**

- 依据(owner 侧半有):SessionStart 上确有 `hooks/handoff-check.sh:66`(注入 `additionalContext`),但注入的是「上次的笔记」;UserPromptSubmit 上确有 `hooks/pm-mode-state.py:45` 的每轮 print,但只推 `:9` 那一句固定文本。**通道验证过能用,内容是空的。**
- 依据(Trellis 有):`session-start.py` + `inject-workflow-state.py` 双钩(`dashboard/.claude/settings.json:5-70`),per-turn 内容按状态从 `workflow.md` 的 `[workflow-state:*]` 块取(`workflow.md:101-145` 契约注释,里面还记了教训:「if a mandatory step isn't mentioned there, the AI silently skips it — Phase 1 planning gate skip and Phase 3.4 commit skip both manifested via this gap」)。
- 这是**成本最低的空缺**:机制位已经在跑、脚本形态已有先例,补的是内容不是机制。

**空缺 3 —— 验证是「派人审」不是「跑命令」,缺项目级验收命令登记处**

- 依据(owner 侧有的是审查):`agents/adversarial-reviewer.md` 全文、`CLAUDE.md:23-26`、Stop hook 的 lint 链。缺的是 `harness-creator/templates/init.sh:1-78` 那种「一条命令跑完本项目验证」并被指令文件点名(`templates/agents.md:52-60`)的登记处;现在命令散在 `rules/python.md:9`、`rules/reverse-api.md:27` 和各项目 CLAUDE.md。
- 依据(Trellis 有):`implement.md` 里带 ordered checklist + validation commands + review gates(`workflow.md#Planning Artifacts`),外加 `.trellis/agents/check.md` 专职检查代理。
- 严重度低于 1、2:`CLAUDE.md:26` + `os/WORKERS.md:31` 已经从纪律上要求「真实输出、证据绑定候选」,缺的只是「命令登记 + 机械核对」,不是缺概念。

### 6.2 已有等价物,**不要**再做

| Trellis 的东西 | owner 的等价物 | 依据 |
|---|---|---|
| `.trellis/spec/` 分层规则注入 | `rules/*.md` 的 frontmatter `paths:` 前置匹配 | `rules/architecture.md:1-13`、`rules/coding-minimal.md:1-5` 等 7 份带 paths;比 spec 的「读 index 再读子文件」少一跳,且不占常驻上下文 |
| `.trellis/agents/check.md` 检查代理 | `agents/adversarial-reviewer.md` | `:16-20` 验收标准逐条核对放第一位、`:31` 证据三态、`:32` blocking 三件套、`:36-43` 假阳性清单、`:45-50` verdict 只看 blocking —— 规格比 check agent 细;`CLAUDE.md:23` 还额外要求跨模型独立(派 codex 审代码) |
| `trellis channel` 多 worker 编排与预算 | `os/MODELS.md:4-6`(粒度)+ `:9-11`(缓存)+ `os/WORKERS.md:6-20`(通道与档位)+ 两个硬闸 | `hooks/subagent-model-guard.sh:3`、`hooks/workflow-agent-cap.sh:1-11` + `hooks/workflow-cap`;对位 `harness-creator` 的 multi-agent 与 tool-registry 两个 reference 面 |
| 项目指令文件模板 | `CLAUDE.md` + `rules/doc-writing.md` + 两个 hook | `rules/doc-writing.md:1-17`(祈使句、一条一行、≤3KB/6KB/7KB)、`hooks/doc-filler-guard.sh:21-28`、`hooks/institution-refcheck.py:28-42` |
| (Trellis 没有的)开工调研闸门 | `/kickoff` | `commands/kickoff.md:10-13` 未放行不产出实现物、`:30-33` 四选一(复用/二开/引用契约/自建)、`:33` 自建必须论证「上游确无等价物」+ 至少一次实测佐证。**反证 owner 是拿 kickoff 去补 Trellis 的**:`dashboard/CLAUDE.md:14` 明写「kickoff 的调研职能写在 design.md 的对应节,不再单开 kickoff 文档」 |
| (Trellis 弱的)会话交接 | `/handoff` ⇄ `handoff-check.sh` 闭环 | 写入端 `commands/handoff.md:24-35` 的内容要求(含「当前判断」「已排除的假设」「不要再试:X,因为已验证 Y」)比 `harness-creator/templates/session-handoff.md:1-40` 的空表格详细得多;消费端 `hooks/handoff-check.sh:41-58` 还带年龄分档与 cwd 过滤。**新 harness 只需把它接到新状态文件上,不重写** |
| (Trellis 没有的)owner 汇报协议 | `commands/pm.md:24-27` | 固定汇报格式 + 「验收把握」三态 + 请示判据;`pm/TEMPLATES.md:9-16` 四类派工模板 |

### 6.3 由此收敛的「新 harness 该装什么」

按上面的空缺,项目级 harness 的最小件应当只有三样(不做项一并列出,依据 `rules/design-doc.md:13`):

1. 一个**任务状态文件**(当前任务 / 状态 / 拆解步骤 / 每步 verify / 证据),放项目内、跨会话可读 —— 补空缺 1。
2. 两个**注入钩子**:SessionStart 读状态文件 + UserPromptSubmit 按状态推一行 breadcrumb —— 补空缺 2,且必须与 `pm-mode-state.py` 的 print 合并或分工(见 5.2 第 1 点)。
3. 一份**验收命令登记**(项目级,几行即可) —— 补空缺 3。

不做项(有等价物,做了就是重复):项目指令文件模板、检查/审查代理、派工与并发预算、开工调研闸门、交接笔记格式、prompt 库集成。

---

## 附:未核实项

- `~/.codeisland/codeisland-hook.sh` 的实际行为(挂在全部 12 个事件上,本次未读该脚本)。
- `~/.pi/agent/extensions/handoff-reminder.ts`(`commands/handoff.md:10` 提到的 Pi 侧消费端,本次未读)。
- `~/.claude/prompts/` 下 12 份 prompt 库文件的正文(只读了 `pp.md:16-29` 的索引表)。
- `~/.claude/pm/templates/` 四份模板正文(只读了 `pm/TEMPLATES.md` 索引)。
- `.trellis/scripts/task.py` 等实现细节(只读了 `dashboard/.trellis/workflow.md` 与 `config.yaml`;Trellis 深度分析属另一份报告的范围)。
- `~/.claude/skills/` 下 36 个 skill 中,除 `skill-smith/SKILL.md` 外均未读;`skill-smith` 本身是「做 skill 的元技能」(`skills/skill-smith/SKILL.md:14-20` 三条路由:create / consolidate / maintain;`:22-28` 铁律,含「没有 RED 记录不许写 skill」),与项目周期链无直接关系,只在新 harness 要以 skill 形态落地时用得上。
