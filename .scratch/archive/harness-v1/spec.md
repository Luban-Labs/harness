Status: done

# 项目周期 harness v1

## Problem Statement(问题陈述)

owner 用 Claude Code 和 Codex 做项目。今天的痛点有三个:

1. 跨会话断档。做到一半去睡觉,第二天开新会话,agent 不知道项目在哪个阶段、当前在做哪件、做到哪一步;只能靠 owner 复述或靠 agent 自己翻文件猜。
2. 文档与规则失控。项目文档没人跟着代码更新;规则要么没沉淀,要么什么都往规则里塞,最后变成一座「石山」,每个会话都被灌一堆无关上下文。
3. 现成方案太重。Trellis 每个任务要 3 份规划文档加 2 份上下文清单、12 个编号步骤、Node 与 Python 双运行时、每轮注入,作者自己的仓库里 56% 的任务绕过了它的门禁(出处 `docs/research/01`、`07` §3.1、§3.4);owner 只想要周期管理这一件事。

## Solution(解法)

一套只管「干到哪了」的轻量约定,加两个共用脚本、一个已落地的 skill:

- 想做一件事,先说「采访我」。interview-me 一次只问一个真挡路的问题,对齐后自己判大小:大的沉淀 spec 并建成一个 Task,小的对完直接干。
- Task 就是一个文件夹 `.scratch/<功能名>/`,里面的 `spec.md` 第一行是状态,末尾是「进展」段。没有总清单,没有第二份真相。
- 每轮 agent 停下前,如果这轮动了代码却没记进展,Stop hook 拦一下让它补一行。
- 第二天开新会话,SessionStart hook 自动告诉 agent:当前 Task、状态、最后一行进展。没有活跃 Task 时一个字都不注入。
- 收件时 agent 过两问:路由表里的文档哪些过期了、这次有没有要沉淀的规则;然后改状态、把整个文件夹挪进 `.scratch/archive/`,桌面只剩在做的和排队的。
- 规则分三层:根 `AGENTS.md` 只放全项目通用的硬规则和一张「什么时候读什么」的路由表;`docs/rules/<主题>.md` 按主题存规则,被路由到才读;`docs/decisions.md` 是给人看的决策账本,任何时候都不注入。
- Claude Code 与 Codex 共用同一套文件和同一对 hook 脚本。

## User Stories(用户故事)

1. As owner, I want 说一句「采访我」就开始对需求, so that 不用先想清楚再开口。
2. As owner, I want agent 一次只问一个真挡路的问题、其余给默认值, so that 不被几十个问题轰炸。
3. As owner, I want agent 自己判断这件事要不要建 Task, so that 小事不走流程,大事不漏文档。
4. As owner, I want 大事的 spec 与状态在同一个文件夹里, so that 看一眼目录就知道桌上有几件事、各到哪了。
5. As owner, I want 小事对完直接干、不留任何文件, so that 桌面不被琐事占满。
6. As agent(新会话), I want 一开始就被告知当前 Task、状态、最后一行进展, so that 不用翻历史对话也能接着干。
7. As agent(新会话), I want 没有活跃 Task 时什么都不被注入, so that 做无关的事时上下文干净。
8. As owner, I want 有活跃 Task 但这次来做别的事时只多看 3 行、说一句「不管它」就完, so that 注入不会反复冒出来。
9. As agent, I want 每轮动了代码停下前被要求补一行进展, so that 进展不靠自觉。
10. As agent, I want 没动代码的轮次 Stop hook 零干扰, so that 不被无意义地拦。
11. As agent, I want 进展段只追加不改旧行, so that 历史可追溯、写起来没心理负担。
12. As owner, I want 收件时 agent 逐行过路由表答「已更新 / 不受影响」, so that 文档不会悄悄过期。
13. As owner, I want 收件时沉淀的规则写进对应主题文件、新主题才在路由表加一行, so that AGENTS.md 不长成说明书。
14. As owner, I want 收件后 Task 文件夹整个挪进 archive, so that 桌面越做越干净而不是越堆越多。
15. As owner, I want 根 AGENTS.md 只放全项目通用硬规则和路由表, so that 每个会话的常驻上下文有上限。
16. As agent, I want 改到某类文件或做某类事时,路由表告诉我去读哪一个规则文件, so that 只加载相关规则。
17. As owner, I want 决策记在 `docs/decisions.md` 里但不进任何路由和注入, so that 我能查账,agent 不被喂无关历史。
18. As owner, I want AGENTS.md 与每个规则文件有字节上限、满了先删再加, so that 石山在预算层被挡住。
19. As owner, I want 同一套文件和 hook 在 Codex 里也能用, so that 换工具不换流程。
20. As owner, I want 每个能往上下文塞东西的口子都登记条件与上限, so that 以后加东西有账可查。
21. As owner, I want 整套东西不依赖任何第三方包, so that 新项目零安装。

## Implementation Decisions(实现决策)

**Task 与状态**

- Task = `.scratch/<功能名>/` 目录,由 interview-me 的大出口创建(沿用 Matt 的本地 tracker 约定)。
- `spec.md` 第一行 `Status: <值>`,值域 `ready-for-agent | in-progress | done`,三次转换各有唯一写者,都是 agent 手改,没有专用写状态的脚本:
  - `ready-for-agent`:interview-me 大出口建 Task 时写。
  - `in-progress`:**开工动作**——agent 开始实现某个 Task 时,动代码前先把首行改成 `in-progress`,并在末尾建一个空的 `## 进展` 段(已有则不动)。触发:owner 说「开始做 X」,或 agent 在 interview-me 出口后经 owner 点头进入实现。
  - `done`:收件动作写,随即归档。
- 同一时刻至多一个 `in-progress`。开工前若已有别的 `in-progress`,先把它收件或改回 `ready-for-agent`(未做完也可以改回,进展段留着),再开工。
- `spec.md` 末尾一个 `## 进展` 段,每行一条、只追加:时间、done 了什么、next 是什么、别再试什么。这一行格式是决策本身,来自采访:

  ```
  - 09-10 23:40 done: <可验证的小步> | next: <下一步> | 别再试: <已验证走不通的路>
  ```

- 收件 = 改 `Status: done`,把整个目录移到 `.scratch/archive/<功能名>/`。归档是唯一的完成事件。
- 不建 tasks.json 或任何索引;要看全貌就列目录。

**两个 hook 脚本,Claude Code 与 Codex 共用**

- `session-start`:扫 `.scratch/*/spec.md` 首行。恰好一个 `in-progress` → 输出 3 行(Task 名、状态、最后一行进展)作为 additionalContext;零个 → 不输出;多于一个 → 只输出一行提示「有 N 个 in-progress,先收成一个」。
- `stop-guard`:四条件同时成立才拦——恰好一个 `in-progress`;本会话改过 spec 以外的文件;最后一次改代码晚于最后一次写该 spec;`stop_hook_active` 为假。拦 = 输出 `decision: block` 与一行原因;其余情况输出空。「本会话改过」与「晚于」的数据来源是**文件 mtime**:`session-start` 每次运行 touch 一个标记文件 `.scratch/.session`,`stop-guard` 把项目里 mtime 晚于标记的文件(排除 `.scratch/`、`.git/`、`.claude/`、`.codex/`、依赖与构建目录)视为本会话改动,取其中最新的 mtime 与该 spec 的 mtime 比较。不读会话记录,因为 agent 用 Bash heredoc 写文件时记录里没有 Edit/Write。任何读取失败都放行,绝不因 harness 自身出错而拦人。
- 两脚本 python3 标准库,零第三方依赖;读 hook 的 stdin JSON,写 stdout JSON。字段名两边一致,出处:Codex 源码 `codex-rs/hooks/src/schema.rs`——`SessionStartHookSpecificOutputWire.additional_context`、`StopCommandOutputWire.decision`(仅 block)+ `reason`、`StopCommandInput.stop_hook_active`;Codex 的 `HookEventName` 含 `SessionStart`、`Stop`(`codex-rs/protocol/src/protocol.rs`)。Claude 侧同名字段见 owner 的 `hooks/handoff-check.sh:66`。
- 脚本住在 harness 仓库里,项目只在各自的 hook 配置里按绝对路径引用,不复制进项目;改一次全项目生效。
- 与 owner 用户级已有 hook 的关系:SessionStart 与 handoff-check 并列;Stop 与 lint 链并列;都用 JSON 决策,不用 exit 2。

**规则与文档三层**

- 根 `AGENTS.md`,同目录 `CLAUDE.md` 是指向它的符号链接。内容只有两块:全项目通用硬规则;路由表。**路由表是 agent 该读的全部文档的登记处**,每行「做什么 / 改到哪 → 读哪个文件」,目标可以是 `docs/rules/<主题>.md`,也可以是 README、架构说明、接口文档等任何项目文档;不在表里的文档默认只给人看。路由表固定一行「开始做或收一个 Task → docs/rules/harness.md」,让 Codex 也能走开工与收件。
- `docs/rules/<主题>.md`:一个主题一个文件,只有被路由到才读。不写出处、不写为什么,一条一句。
- `docs/decisions.md`:只追加;每条 1 到 3 句——背景、决定、为什么。故意不出现在路由表和任何注入里。
- 字节上限:AGENTS.md 与每个规则文件各有上限,具体数值在第一个真实项目跑出来后定;超限时加一条必须先删一条。
- 不用 `.claude/rules/*.md`。

**开工与收件**(写在 `docs/rules/harness.md`,由路由表指到,开工或收件那一步才读)

- 开工:改 `in-progress`、建空进展段,见「Task 与状态」。
- 收件一问:逐行过路由表登记的每个文档,答「已更新 / 不受影响」;答「已更新」的必须真改过。
- 二问:这次有没有以后必须遵守的规矩;有就写进对应主题文件,新主题在路由表加一行。
- 两问过完才改状态、归档。

**上下文预算,作为不变量**

| 进入点 | 条件 | 上限 | 无活跃 Task 时 |
|---|---|---|---|
| SessionStart 注入 | 恰好一个 in-progress → 3 行(Task 名、状态、最后一行进展,无进展行时第三行写「进展:无」);多于一个 → 1 行提示 | 3 行 | 0 |
| Stop hook | 四条件同时成立 | 1 行原因 | 0 |
| 根 AGENTS.md | 每个会话 | 字节上限 | 同 |
| 路由表指到的文档(含 docs/rules/ 与 docs/rules/harness.md) | 被路由表指到 | 每文件上限 | 0 |
| spec 正文与进展段全文 | 从不自动加载;只有首行 Status 与最后一行进展经上面 SessionStart 那一行进入 | 0 | 0 |
| docs/decisions.md | 从不加载 | 0 | 0 |
| skill description | 常驻,Claude Code 机制 | interview-me 约 120 字 | 同 |

新增任何进入点必须先在这张表登记条件与上限,登不上的不加。

## Testing Decisions(测试决策)

- 什么算好测试:只测外部行为——给脚本一个目录状态和一段 stdin,断言 stdout;不测脚本内部函数。
- **seam 只有一个:两个 hook 脚本的 stdin/stdout 契约。** 用 fixture 目录构造 `.scratch/` 的各种状态(无 Task、一个 in-progress、两个 in-progress、有进展、无进展),用合成的会话记录构造「改过代码 / 没改 / 改完又写了 spec / stop_hook_active」的组合,逐个断言输出。这一层最高、最稳,与 Claude Code 和 Codex 的宿主无关。
- 先例:harness-creator 的 `run-benchmark.mjs` 先在临时目录造一套脚手架再验证自己,同一思路。
- 端到端只做人工验收:新项目里从「采访我」跑到收件一整圈,关会话,新会话空白起步,agent 自己报出 Task、状态、下一步;归档目录里有做完的文件夹;`docs/rules/` 里多了一条规则。
- 不做自动化的:模型有没有真按路由表去读规则文件、Stop 拦得烦不烦——这两条靠真实项目观察,见 Further Notes。

## Out of Scope(不做)

- 每轮一行注入(UserPromptSubmit)。
- tasks.json 或任何总清单;父子任务;依赖图。
- 规则或文档里带出处、带为什么。
- Claude Code 与 Codex 以外的平台;多人身份;会话日志与 journal。
- 子代理上下文清单与 start 门禁;spec 层自动注入;记忆检索。
- 审查代理、开工调研闸门、交接笔记格式:owner 用户级已有 adversarial-reviewer、kickoff、handoff,只接线不重写。
- 迁移 owner 已装 Trellis 的 9 个项目;v1 只在一个新项目上用。
- interview-me 移植到 Codex 侧;Codex 只通过共用文件、共用 hook 与 AGENTS.md 路由表参与。
- 任何脚本去写 Status 或进展;状态永远由 agent 手改。

## Further Notes(补充)

未知与验证动作(采访中留下的):

- SessionStart 注入与 owner 已有的 handoff-check 注入合计体积:量字节;≤2 KB 算支持;>4 KB 改为合并成一段。
- 挂满 12 个事件的 codeisland-hook 会不会吞掉或重复本 harness 的输出:装进一个项目跑 5 轮看;各出现一次算支持。
- 模型改到对应路径时是否真按路由表去读规则文件:跑 3 个 Task 记漏读次数;漏了给 Claude 侧补一个几行的 PreToolUse 提醒。
- Stop 每轮拦是否烦:跑 3 个 Task 记被拦次数与其中「不该拦」的次数;不该拦 >20% 就收紧条件二(只算非琐碎改动)。
- 字节上限的具体数值:第一个真实项目结束时按实际文件大小定。
- Codex 侧 hook 的配置文件格式与 trust 流程(源码见 `--dangerously-bypass-hook-trust` 标志,说明 hook 需先被信任):实测一次,记进 `docs/rules/harness.md`。字段名与事件名已核,见 Implementation Decisions。
- 三个 Status 值够不够:出现想记但记不了的状态即加,不预留。

AGENTS.md 加载方式出处:Codex 源码 `codex-rs/core/src/agents_md.rs`——以 `.git` 为根标记,从项目根到当前目录逐级收集 `AGENTS.md` 并按序拼接,不越过根,「Symlinks are allowed」,总预算 `project_doc_max_bytes` 默认 32 KiB;提示词 `gpt_5_1_prompt.md` 规定嵌套文件作用域为所在子树、更深者优先。推论:Codex 只自动拼「根到当前目录」这条线,别的子树靠模型按提示词自行查看,所以 Codex 要从项目根启动。

许可:Trellis 是 AGPL-3.0,本 harness 不复制其任何文件,只参考设计;Matt 的 skills 与 harness-creator 是 MIT,可直接改用。

命名:`.scratch/`、`docs/rules/`、`docs/decisions.md` 先按此,owner 可改;改名不影响任何决策。

## 进展
- 09-10 22:39 done: Astra 交付六项+12 测试,主会话亲跑通过并读完两脚本;Claude 侧 hook 加 10s 超时 | next: claude -p 空白会话验注入;Astra Delta 做实 Codex 侧 hook 注册 | 别再试: companion --model 传 luna/sol/astra 别名(要传 gpt-6-astra 等真实 ID)
- 09-10 22:42 done: Stop hook 实测 | next: 无 | 别再试: 无
- 09-10 22:43 done: Claude 侧端到端全部实测通过(空白 claude -p 报出 Task/状态/进展;Stop 拦下→补进展→放行) | next: 等 Astra 交 Codex 侧 hook 注册与实测;两边都通过后收件归档 | 别再试: codex 工人在跑时别在同目录起嵌套 claude -p(两次工人恰在此时成孤儿)
- 09-10 23:00 done: Codex Stop hook 实测 | next: 无 | 别再试: 无
- 09-10 23:01 done: Codex 侧端到端通过(.codex/hooks.json 落盘;空白 codex exec 报出 Task/状态/进展;Stop 拦下→补进展→放行);收件一问:docs/rules/harness.md 已更新(Codex 段实测替换待实测),tests/ 不受影响(脚本未再改);收件二问:无新增项目规则,两条跨项目结论记 INBOX | next: owner 在本项目 codex 交互界面跑一次 /hooks 完成持久信任;之后在一个新项目上用 templates/AGENTS.md 起第一个真实周期 | 别再试: Astra 的沙箱写不了 .codex/,项目级 hook 配置由主会话写
