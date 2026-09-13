# mattpocock/skills 的「项目周期链」拆解

**读取对象**:`/private/tmp/claude-501/-Users-sangba-Downloads-02-----------harness/c38a95e8-724a-458f-a564-59ac3a323ca8/scratchpad/mattskills`,HEAD = `3cca18b`(Merge PR #1025)。
**溯源约定**:本文所有 `path:line` 均相对上述仓库根。凡本次没读到的,一律标「未核实」。
**受众提示**:结论在每节开头,证据在后。

---

## 0. 一句话结论

这是一条 **「人手动敲 slash command 推进、把 issue tracker 当唯一状态库、全部由 markdown prompt 构成、没有任何运行时兜底」** 的周期链。它的「轻」来自三个「没有」:没有自己的状态存储、没有调度器/运行时、没有确定性校验;代价是链条的调度器其实是人,而完成态回写这一环**在链条里断了**(见 §4.2)。

---

## 1. 周期链:输入 → 产出 → 如何接上

### 1.1 主链(作者自称 main flow)

作者自己给出的主链是 `grill-with-docs → to-spec → to-tickets → implement → code-review`,这句话在三处独立出现:`docs/engineering/implement.md:90`、`docs/engineering/code-review.md:88`、`docs/engineering/to-tickets.md:96`;路由技能里的长版本在 `skills/engineering/ask-matt/SKILL.md:13-32`。

| # | 技能 | 输入 | 产出物(落到哪) | 下一步怎么接上 |
|---|---|---|---|---|
| 0 | `setup-matt-pocock-skills`(前置,一次性) | 仓库现状:`git remote`、`CLAUDE.md`/`AGENTS.md`、`CONTEXT.md`、`docs/adr/`、`.scratch/`(`skills/engineering/setup-matt-pocock-skills/SKILL.md:21-30`) | **仓库文件**:`docs/agents/issue-tracker.md`、`docs/agents/domain.md`、`docs/agents/triage-labels.md`(仅当装了 triage),外加往 `CLAUDE.md`/`AGENTS.md` 追加一个 `## Agent skills` 块(同上 `:86-102`、`:104-110`) | 下游技能**运行时读**这三个文件决定去哪发 issue。`docs/engineering/setup-matt-pocock-skills.md:5`:「skills 本身各处相同;它们运行时读 `docs/agents/issue-tracker.md` 并照做」 |
| 1 | `grill-with-docs` | 一个粗想法 + 工作目录 | **对话** + 顺带写 `CONTEXT.md` 与 `docs/adr/NNNN-*.md` | 本体只有一行:`Call the Skill tool twice, for "grilling" and "domain-modeling".`(`skills/engineering/grill-with-docs/SKILL.md:7`)。落盘那部分由 domain-modeling 做(`skills/engineering/domain-modeling/SKILL.md:60-64`) |
| 2 | `to-spec` | **当前对话上下文**,明确禁止再采访(`skills/engineering/to-spec/SKILL.md:7`) | 一份 spec,**发布到 issue tracker**,并打 `ready-for-agent` 标签(`:19`) | 产物是 tracker 上的一条 issue(或本地 `.scratch/<feature>/spec.md`),to-tickets 用引用参数取它 |
| 3 | `to-tickets` | plan / spec / 当前对话;也可传 spec 路径、issue 号或 URL 作参数(`skills/engineering/to-tickets/SKILL.md:17`) | **每票一条 issue** 或 **每票一个文件** `.scratch/<feature-slug>/issues/<NN>-<slug>.md`,自 `01` 起按依赖序编号,带 blocking 边(`:62-63`) | 「工作 frontier:所有 blocker 都已完成的票」(`:65`)。**下一步是人自己去敲 `/implement`** |
| 4 | `implement` | 一张票或一份 spec | **当前分支上的一个 commit**(`skills/engineering/implement/SKILL.md:15`) | 内部调 `/tdd`(`:9`),收尾调 `/code-review`(`:13`)。整个 SKILL.md 只有 15 行 |
| 5 | `code-review` | 一个固定点(commit/branch/tag/merge-base)+ 找到的 spec 源(`skills/engineering/code-review/SKILL.md:17-32`) | **只有对话里的两段报告**(`## Standards` / `## Spec`),不写文件、不发评论、不改标签(`:74-78`) | 无自动下一步 |

### 1.2 两条 on-ramp(汇入主链)

| 技能 | 输入 | 产出物 | 汇入点 |
|---|---|---|---|
| `triage` | 别人提的 issue / 外部 PR(`skills/engineering/triage/SKILL.md:11`) | tracker 上的**标签变更 + 评论**(agent brief),外加仓库文件 `.out-of-scope/<concept>.md`(`:85`) | 产出「带 brief 的 `ready-for-agent` issue」,`implement` 像接 to-tickets 的票一样接它(`docs/engineering/triage.md:99`)。**明确规定 to-tickets 产的票不要再 triage**(`skills/engineering/ask-matt/SKILL.md:40`) |
| `wayfinder` | 一个大到一个 session 装不下的模糊想法(`skills/engineering/wayfinder/SKILL.md:7`) | tracker 上一条打 `wayfinder:map` 标签的 **map issue** + 一批 **decision ticket 子 issue** + 每票的 resolution comment + map 的 `Decisions so far` 索引(`:21-23`、`:125`) | 地图清空后**交棒不建造**:汇入点是 `to-spec` 而不是 `implement`(`skills/engineering/ask-matt/SKILL.md:46`) |

### 1.3 插入型(被主链或 on-ramp 调用)

| 技能 | 输入 | 产出物 | 接法 |
|---|---|---|---|
| `grilling` | 计划/决策/想法 | **纯对话**,按 round 提问,每题带推荐答案(`skills/productivity/grilling/SKILL.md:8-22`) | 是 `grill-me`、`grill-with-docs`、`triage`、`wayfinder` 共用的原语 |
| `grill-me` | 同上,但**无工作目录** | 纯对话,不落盘 | 本体一行:`Call the Skill tool with "grilling".`(`skills/productivity/grill-me/SKILL.md:7`) |
| `research` | 一个待查问题 | **仓库里一个带引用的 markdown 文件**,位置「按仓库既有惯例,没惯例就自己找个合理的地方并说明」(`skills/engineering/research/SKILL.md:11-13`) | 后台 agent 跑;产物「拿进主链的 `/grill-with-docs`」(`skills/engineering/ask-matt/SKILL.md:81`) |
| `prototype` | 一个设计问题 | 抛弃型代码;**验证过的决策折进正式代码,原型本身提交到 `prototype/<name>` 抛弃分支,并在实现 issue 上留一个 context pointer**(`skills/engineering/prototype/SKILL.md:26`) | 主链第 2 步的绕道,进出各用一次 `/handoff`(`skills/engineering/ask-matt/SKILL.md:18-21`) |
| `tdd` | 一条待建行为 | 测试 + 实现 | 只在**预先确认过的 seam** 上写测试,未确认的 seam 一个测试都不写(`skills/engineering/tdd/SKILL.md:22`) |
| `domain-modeling` | 对话中冒出的术语/决策 | `CONTEXT.md`(纯词汇表)、`docs/adr/NNNN-slug.md`(`skills/engineering/domain-modeling/SKILL.md:60-74`) | 「懒创建:有东西写的时候才建文件」(`:40`) |

### 1.4 收尾 / 跨会话

| 技能 | 输入 | 产出物 | 接法 |
|---|---|---|---|
| `handoff` | 当前对话 | **一个 markdown 文件,写到操作系统临时目录,明确「不是当前 workspace」**(`skills/productivity/handoff/SKILL.md:8`) | 人开新会话,指向那个路径(`docs/productivity/handoff.md:51`) |
| `claude-handoff`(beta) | 当前对话 | **不落盘**,摘要直接当 prompt 启动后台 agent:`claude --bg --name "<name>" "<summary>"`(`skills/in-progress/claude-handoff/SKILL.md:8`) | 用 `claude agents` 管理 |
| `implement-spec`(beta) | 一份 spec + 它的票 | **一条分支 + 一个 draft PR**,PR 声明 closing spec issue 与各票(`skills/in-progress/implement-spec/SKILL.md:23`) | 把票当任务图跑并发 implementer 子代理,每个独立 worktree 独立分支(`:25`),完成后 merger 子代理合入(`:27`) |
| `loop-me`(beta) | 用户的生活/工作循环 | 有状态工作区:`workflows/*.md`(一 loop 一 spec)+ `NOTES.md`(`skills/in-progress/loop-me/SKILL.md:29-32`) | 与代码周期链**不相接**,它管的是个人 workflow 规格,不是项目票 |
| `retro`(beta) | 一次 session 的日志 | **只有对话里的候选清单**,按严重度排序(`skills/in-progress/retro/SKILL.md:25`) | README 自标 `STUB: design notes only, not functional yet`(`skills/in-progress/README.md:18`) |

### 1.5 链条推进的真实动力:人

这条链**没有自动流转**。周期链上几乎每一环都带 `disable-model-invocation: true`,即只有人打字才能触发:
`setup`(`SKILL.md:4`)、`triage`(`:4`)、`grill-with-docs`(`:4`)、`to-spec`(`:4`)、`to-tickets`(`:4`)、`implement`(`:4`)、`wayfinder`(`:4`)、`grill-me`(`:4`)、`handoff`(`:5`)、`claude-handoff`(`:5`)、`implement-spec`(`:4`)、`loop-me`(`:4`)、`retro`(`:4`)。

文档把这点讲死了:「凡是 `ask-matt` 或 `to-tickets` 说『然后每票 `/implement`』,那是给你的指令,不是 agent 会自己做的事」(`docs/engineering/implement.md:9`)。

模型可自主触发的只有 `grilling`、`code-review`、`research`、`prototype`、`tdd`、`domain-modeling`(各自 frontmatter 无该字段)。

---

## 2. 状态存在哪里

### 2.1 是的,它把 issue tracker 当状态库

三条硬证据:

1. **setup 的第一个决策就是选状态库。** Section A 让用户在 GitHub / GitLab / 本地 markdown / 其他 之间选,并把选择记进 `docs/agents/issue-tracker.md`(`skills/engineering/setup-matt-pocock-skills/SKILL.md:38-49`)。
2. **状态就是标签。** triage 的五个 state role 是 `needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`,再加两个 category role `bug` / `enhancement`;「每条已 triage 的 issue 应恰好带一个 category 和一个 state」(`skills/engineering/triage/SKILL.md:31-41`)。canonical role → 真实标签字符串的映射表在 `docs/agents/triage-labels.md`(`skills/engineering/setup-matt-pocock-skills/triage-labels.md:5-11`)。
3. **依赖关系也存在 tracker 里。** GitHub 走 native issue dependencies:`gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`,而且特别强调要用数字 **database id** 而非 `#number` 或 `node_id`(`skills/engineering/setup-matt-pocock-skills/issue-tracker-github.md:42`)。

**没有 tracker 时的降级路径是本地 markdown 约定,不是另一套存储**:`.scratch/<feature-slug>/` 一目录一 feature、`spec.md`、`issues/<NN>-<slug>.md`、状态写成文件顶部的 `Status:` 行、评论追加到 `## Comments` 段(`skills/engineering/setup-matt-pocock-skills/issue-tracker-local.md:7-11`)。

**它自己划了红线**:只支持主流 tracker,新的 agent 向 tracker 一律拒收,理由是「每个后端都把一套 CLI 形状硬编码进 skills,是永久维护面」(`.out-of-scope/mainstream-issue-trackers-only.md:7`)。

### 2.2 落到仓库里的全部文件与位置约定

| 文件 / 目录 | 谁写 | 出处 |
|---|---|---|
| `docs/agents/issue-tracker.md` | setup | `setup-matt-pocock-skills/SKILL.md:49`、`:106-108` |
| `docs/agents/domain.md` | setup | `SKILL.md:110` |
| `docs/agents/triage-labels.md` | setup(仅当装了 triage) | `SKILL.md:102`、`:109` |
| `CLAUDE.md` 或 `AGENTS.md` 里的 `## Agent skills` 块 | setup(改已存在的那个,绝不新建另一个) | `SKILL.md:74-82`、`:86-100` |
| `CONTEXT.md`(根,单上下文) | domain-modeling,懒创建 | `domain-modeling/SKILL.md:12-22`、`:40` |
| `CONTEXT-MAP.md` + `src/<context>/CONTEXT.md`(多上下文) | 同上,仅 monorepo | `domain-modeling/SKILL.md:24-38`;setup 只在探测到 monorepo 信号时才提议(`SKILL.md:59-61`) |
| `docs/adr/NNNN-slug.md`(顺序编号) | domain-modeling,三条件全满足才建 | `domain-modeling/ADR-FORMAT.md:3`、`:29-37` |
| `src/<context>/docs/adr/` | 同上,多上下文时的上下文级决策 | `setup-matt-pocock-skills/domain.md:36-38` |
| `.out-of-scope/<concept>.md` | triage,**仅当 enhancement 被拒**;因「已实现」而关闭的不写 | `triage/OUT-OF-SCOPE.md:86-88` |
| `.scratch/<feature-slug>/spec.md` | to-spec(本地 tracker 模式) | `issue-tracker-local.md:8` |
| `.scratch/<feature-slug>/issues/<NN>-<slug>.md` | to-tickets(本地模式),**绝不合并成一个文件** | `to-tickets/SKILL.md:62`、`issue-tracker-local.md:9` |
| `.scratch/<effort>/map.md` + `.scratch/<effort>/issues/NN-*.md` | wayfinder(本地模式) | `issue-tracker-local.md:25-26` |
| research 笔记 markdown | research,位置「按仓库既有惯例」 | `research/SKILL.md:13` |
| `prototype/<name>` 抛弃分支 | prototype | `prototype/SKILL.md:26`、`ask-matt/SKILL.md:80` |
| `research/<name>` 抛弃分支 | wayfinder 派出的 research 子代理 | `wayfinder/SKILL.md:115` |
| **OS 临时目录**里的 handoff 文件 | handoff,**刻意不进 workspace** | `handoff/SKILL.md:8` |

### 2.3 四个值得注意的状态设计取舍

- **状态机只覆盖「入口分诊」,不覆盖「执行中 / 已完成」。** 五个 state role 里没有 `in-progress`,也没有 `done`(`triage/SKILL.md:31-37`)。唯一的完成位是 issue 的 open/closed,而 triage 只在 `wontfix` 时主动关闭(`:82`)。
- **wayfinder 反而有「认领」态,主链没有。** wayfinder 用 assignee 当 claim,「开着且无 assignee 即未认领」,且必须在任何工作之前先认领(`wayfinder/SKILL.md:67`);本地模式下是 `Status: claimed` / `resolved`(`issue-tracker-local.md:26`)。
- **map 是索引不是仓库**:「一个决策只活在一个地方,即它的票;map 从不复述,只给一行摘要加链接」(`wayfinder/SKILL.md:23`)。
- **仓库自己没完全按自己的约定走**:本仓库根有 `CONTEXT.md`、有 `.out-of-scope/`,但 ADR 放在 `.agents/adr/` 而不是 `docs/adr/`(`.agents/adr/0001-*.md`、`.agents/adr/0002-*.md`),也没有 `docs/agents/`。属于「自举不完整」的观察点。

---

## 3. 四个关键概念

### 3.1 tracer-bullet ticket(曳光弹票)

**是什么**:一条**纵向**穿透所有层的窄路径,而不是某一层的横切。规则原文四条(`to-tickets/SKILL.md:29-36`):

- 每片切穿 schema / API / UI / tests 每一层,窄但完整;
- 完成后**自身可演示或可验证**;
- **尺寸恰好塞进一个全新的 context window**;
- prefactoring 排在最前面。

**怎么落地**:`to-tickets` 第 3 步产出;第 4 步先把编号清单交给人过一遍(粒度对不对、blocking 边对不对、要不要拆合),批准后第 5 步才发布(`:42-56`)。验收口径见 `docs/engineering/to-tickets.md:84`:「每张票都能回答『做完能演示什么』,答案是行为不是层」。

**唯一例外是 wide refactor**:blast radius 铺满全仓的机械改动(改列名、改共享符号类型)不做纵切,改用 **expand–contract**:先 expand(新旧并存)→ 按 blast radius 分批迁移调用点,每批一票且都被 expand 阻塞,靠旧形式还在来保持 CI 绿 → 最后 contract 删旧形式,被所有迁移批次阻塞(`to-tickets/SKILL.md:40`)。批次自身都保不了绿时,共用一条集成分支,绿只在最后的 integrate-and-verify 票上承诺(同行)。

`tdd` 里用的是同一个词的另一面:「每个测试是一发曳光弹,响应上一轮学到的东西」,对立面叫 horizontal slicing(先写全部测试再写全部实现)(`tdd/SKILL.md:32`)。

### 3.2 blocking edges(阻塞边)

**是什么**:每张票声明「哪些票必须先完成」;无 blocker 的票可立即开始(`to-tickets/SKILL.md:38`)。**frontier** = 所有 blocker 都已完成的票(`:65`)。

**怎么落地,三种物理表示**(由 setup 选的 tracker 决定;票本身不变,只有边的形状变,`:60-63`):

| tracker | 表示 | 出处 |
|---|---|---|
| GitHub | native issue dependencies;`gh api ... /dependencies/blocked_by -F issue_id=<database id>`;读回 `issue_dependencies_summary.blocked_by`(只算未关闭的 blocker,是活的闸门);不可用时降级为正文顶部 `Blocked by: #n, #n` 行 | `issue-tracker-github.md:42` |
| GitLab | native blocking link,用 `/blocked_by #<n>` quick action 发成一条 note;**native blocking 是 Premium/Ultimate 功能**,免费层降级为 `Blocked by:` 行 | `issue-tracker-gitlab.md:43` |
| 本地 markdown | 文件顶部 `Blocked by: NN, NN` 行;所列文件全部 `resolved` 即解除 | `issue-tracker-local.md:27` |

**为什么坚持用 native**:wayfinder 给了理由 —— native 依赖关系「把 frontier **视觉化**渲染在 tracker 自己的 UI 里,人不打开 map 就能看到哪些可取」(`wayfinder/SKILL.md:69`)。验收口径同源:`docs/engineering/wayfinder.md:93`。

**发布顺序有讲究**:必须按依赖序(blocker 先)发布,因为票要引用真实 id(`to-tickets/SKILL.md:63`);wayfinder 更明确 —— 先建票再第二遍连边,「issue 得先有 id 才能互相引用」(`wayfinder/SKILL.md:114`)。

### 3.3 decision tickets(决策票)

**是什么**:wayfinder 专用单位。仓库自己的词汇表定义得最干净:「一个 `wayfinder:map` 的子 issue,装的是一个**问题**,它的解决产出一个**决策**,而不是一片待执行的构建切片」(`CONTEXT.md:15-16`)。

**为什么存在**:「Wayfinder 默认是**规划**,不是执行……想直接动手做的冲动通常正是你已经走到地图边缘、该交棒的信号」(`wayfinder/SKILL.md:13`)。

**怎么落地**:

- 票体只有一段 `## Question`,尺寸按「一个 100K token 的 agent session」定(`:57-63`);
- 每票带 `wayfinder:<type>` 标签,四型(`:65`、`:73-80`):
  - **research**(AFK):子代理调 research 技能;
  - **prototype**(HITL):调 prototype 技能,把原型作为 asset 链接;
  - **grilling**(HITL,默认):同时调 grilling 与 domain-modeling;
  - **task**(HITL 或 AFK):唯一「做事而非决策」的类型,靠「解锁一个决策」赢得存在资格,比如注册某服务以便评估其 API;
- HITL 票只能通过真人对话解决,「agent 永不代替人回答自己的问题(grilling agent 自问自答就是破坏了这条)」(`:75`);
- 解决流程:发 resolution comment → 关闭 issue → 在 map 的 `Decisions so far` 追加一行 context pointer(`:125`);
- **每个 session 最多解决一张票**,research 票除外(`:105`)。

配套两个概念也值得注意:**fog of war**(能感觉到但还说不清的问题,写进 map 的 `Not yet specified`,判据是「现在能不能**精确陈述这个问题**」而不是「能不能回答」,`:88-91`)与 **out of scope**(超出 destination 的,单独一节,永不毕业,`:95-101`)。

### 3.4 fresh-session implementation(全新会话实现)

**是什么**:一票一个全新上下文窗口,票与票之间 `/clear`。

**怎么落地**:

- 尺寸约束在上游:票「恰好塞进一个 fresh context window」(`to-tickets/SKILL.md:33`);
- 节奏在路由里写死:「每票 kick off 一次 `/implement`,**票与票之间 `/clear` 上下文**。每张票自包含,所以上一张的上下文是可丢弃的」(`ask-matt/SKILL.md:23`);
- 反过来,**第 1–3 步(grill → spec → tickets)必须在一个不间断的窗口里**,不许 compact 或 clear,「让 grilling、spec、票建立在同一份思考上」(`ask-matt/SKILL.md:30`);上限是 smart zone,约 150k token,逼近就在最近的 phase boundary 处 `/compact`(`:32`);
- 现实约束:一次调用一张票,**不支持批量或并行**。文档记了一次事故 —— 同一个 checkout 里并行跑多个 `/implement`,一个 session 的 `git commit --amend` 落到另一个 session 的 commit 上、stash 从 `refs/stash` 消失、commit 落错分支,一个下午三起;worktree 是社区变通,但 `refs/stash` 在 worktree 间也是共享的(`docs/engineering/implement.md:57`);
- 已知坑:fresh session 里 `/implement #2` 的 `#2` 会被解析成 agent 能看见的任意编号列表(todo 文件、checklist),而且是**自信解析而非 fail-closed**,建议传完整 URL 或 `owner/repo#2` 并让它复述标题(`docs/engineering/implement.md:75`)。

`implement-spec`(beta)是这条约束的对立面:它把票当任务图,在 ready frontier 上跑并发 implementer 子代理,每个独立 worktree 独立分支,再由 merger 子代理合入 PR 分支(`skills/in-progress/implement-spec/SKILL.md:11-29`)。也就是说,**并发实现在这套体系里还是未毕业的 beta**。

---

## 4. 验证与完成定义:纯文字,几乎没有兜底

### 4.1 `implement` 怎么判「做完了」

SKILL.md 全文 15 行,完成判据只有三句(`skills/engineering/implement/SKILL.md:9-15`):

- 尽量用 `/tdd`,在**预先约定的 seam** 上;
- 「频繁跑类型检查、频繁跑单个测试文件、**结尾跑一次全量测试套件**」;
- 跑完 `/code-review`,然后 commit 到当前分支。

**唯一带机械性的门是「全量测试套件跑一次」**,而且没有说「必须全绿才能 commit」。其余全是行为描述。

**「预先约定的 seam」是这个技能自己承认的最弱关节**:「`implement` 里面没有任何东西去约定 seam。`tdd` 才是会问的那个,它拒绝在未确认的 seam 上写测试。所以实际约定要么发生在上游的 spec 里,要么在本次运行的第一次交互里。**如果哪儿都没发生,这个前置条件就不会触发,运行悄悄退化成『就把代码写了』**」(`docs/engineering/implement.md:47`)。

### 4.2 最关键的断点:完成态不回写

原文(`docs/engineering/implement.md:53`):

> 「`implement` **没有完成步骤**。它止于 commit,从不碰工作项,在 GitHub Issues 和本地 markdown tracker 上都确认过,所以这不是 tracker 集成问题。它也**不处理 `code-review` 产出的发现**,**不勾掉原始 issue 上的 `- [ ]` 复选框**。票请你自己关、验收标准请你自己对。**这在依赖链上咬得最狠,因为 `to-tickets` 把 frontier 定义成 blocker 全部关闭的票。如果什么都不被关闭,就永远没有票会变成可见的未阻塞。**」

这一条把 §2、§3.2、§4 串起来了:**状态库是 tracker,frontier 由「blocker 已 closed」计算,而链条里没有任何一环会去 close**。闭环缺的就是这一笔,且必须人手动补。

### 4.3 `code-review` 怎么判「做完了」

两轴、两个并行子代理、互不污染上下文,最后聚合(`skills/engineering/code-review/SKILL.md:6-11`):

- **Standards 轴**:仓库自己文档化的标准 + 一个固定的 **Fowler 12 味道基线**(Mysterious Name / Duplicated Code / Feature Envy / Data Clumps / Primitive Obsession / Repeated Switches / Shotgun Surgery / Divergent Change / Speculative Generality / Message Chains / Middle Man / Refused Bequest,`:44-56`)。两条绑定规则:**仓库覆盖基线**;**基线永远是判断题不是硬违规**;工具已强制的一律跳过(`:39-41`)。
- **Spec 轴**:缺失/部分实现的需求、没要求却做了的(scope creep)、看起来实现了但实现错了(`:70`)。

**有确定性的部分只有三处**:

1. 开跑前要 `git rev-parse <fixed-point>` 验引用能解析、diff 非空,「坏引用或空 diff 应当在这里失败,而不是在两个并行子代理里面失败」(`:23`);
2. 每条 finding **必须带引用**:标准文件+规则,或味道名+被引用的 hunk,或 spec 的某一行(`:64`、`:70`);
3. 结尾只报每轴各自的最严重项,**明确禁止跨轴排名**(`:76-78`)。

**没有兜底的部分(文档自己承认)**:

- 「子代理输出是假设不是证据……本技能是逐字或轻度整理地聚合两份报告,**并不逐条回文件核实**,所以一条 finding 可能引错位置或夸大影响」(`docs/engineering/code-review.md:68`);
- 「**没有收敛保证**……把一趟当成线索清单,处理有明确规则支撑的那些然后停下,**不要循环跑到它返回干净为止,因为它不会**」(`:72`);
- 只看已提交的 diff(三点式 `<fixed-point>...HEAD`),而 `implement` 是在 commit **之前**跑它,所以「除非已有中间 commit,那份 diff 里根本没有东西可审」—— 两边都未修(`:76`、`skills/engineering/implement/SKILL.md:13`);
- 自己审自己有偏见,建议换新会话跑(`docs/engineering/code-review.md:60`);
- 已知 bug:子代理会重新发现 `/code-review` 并再度扇出,「一份报告到了 50+ 个 agent」,修法(在两个子代理 brief 里加一句禁止委派)**尚未进入发布版**(`:56`)。

### 4.4 唯一带真实机制的验证在 triage,不在 implement

triage 第 3 步 **Verify the claim**:「在任何 grilling 之前,先检查断言是否成立。bug 就按报告者的步骤复现;PR 就 check out 下来跑相关测试或命令。报告结果:已确认(附代码路径)、失败、或细节不足(强 `needs-info` 信号)」(`skills/engineering/triage/SKILL.md:74`)。验收口径:「bug 被复现过,或 PR 被 check out 跑过,**才**有东西到得了 `ready-for-agent`」(`docs/engineering/triage.md:92`)。

另外 triage 有一条真正确定性的格式规则:每条发到 tracker 的评论**必须**以 `> *This was generated by AI during triage.*` 开头(`skills/engineering/triage/SKILL.md:13-17`)。

### 4.5 验收标准本身是什么形态

就是 markdown 复选框文本。`to-tickets` 本地模板 `- [ ] Acceptance criterion 1`(`to-tickets/SKILL.md:79-81`),issue 模板同形(`:94-96`)。triage 的 agent brief 要求「每条独立可验证」并给了正反例(`triage/AGENT-BRIEF.md:28-37`、`:60-64`)。**没有任何机制去勾它们**(见 §4.2)。

### 4.6 整仓有没有 hook / 脚本兜底

**周期链上一个都没有。** 仓库里全部可执行脚本只有六个,没有一个参与周期:
`scripts/link-skills.sh`、`scripts/list-skills.sh`、`scripts/sync-plugin-version.mjs`(仓库自身维护)、`skills/engineering/wizard/template.sh`(生成给人用的向导)、`skills/engineering/diagnosing-bugs/scripts/hitl-loop.template.sh`、`skills/misc/git-guardrails-claude-code/scripts/block-dangerous-git.sh`(危险 git 命令拦截,在 `misc/` 桶,不在 plugin 发布集内,见 `.claude-plugin/plugin.json:21-47`)。

连标签都不自动建:「`docs/agents/triage-labels.md` 是一份**映射**……它不跑 `gh label create`。在全新的 GitHub 仓上这些标签确实还不存在,这被当 bug 报过不止一次」(`docs/engineering/setup-matt-pocock-skills.md:67`)。

---

## 5. 跨会话续工

### 5.1 三个技能各自怎么做

| | `handoff` | `claude-handoff`(beta) | `loop-me`(beta) |
|---|---|---|---|
| 产出落点 | **OS 临时目录**的一个 md 文件,明确不写 workspace(`handoff/SKILL.md:8`) | **不落盘**,摘要直接当 `claude --bg` 的 prompt(`claude-handoff/SKILL.md:8`) | 工作目录里的 `workflows/*.md` + `NOTES.md`(`loop-me/SKILL.md:29-32`) |
| 必含内容 | 「suggested skills」段,点名下一个 agent 该调哪些技能(`:10`) | 同(`:12`) | 词汇表:Trigger / Checkpoint / Push right / Brief(`:20-24`) |
| 去重原则 | **不复制**已在 spec/plan/ADR/issue/commit/diff 里的内容,只留路径或 URL(`:12`) | 同(`:14`) | 不适用 |
| 安全 | 脱敏 key/密码/PII(`:14`) | 同,且强调「摘要会变成 agent 的 prompt」(`:16`) | 不适用 |
| 接续方式 | 人开新会话,指向那个路径(`docs/productivity/handoff.md:51`) | 后台 agent 立刻开跑,`claude agents` 管理 | 同一目录下次继续 grilling |
| 完成定义 | 「冷读就知道下一步做什么」(`docs/productivity/handoff.md:68`) | 同 handoff | 「implementer agent 不用问一个问题就能建出来;还剩一个问题就没做完」(`loop-me/SKILL.md:27`) |

**`handoff` 的适用面被刻意压得很窄**:只有四种情况用它 —— 换 harness(Claude→Codex)、换目录/仓库、交给同事、phase 中途 fork 一个支线(`ask-matt/SKILL.md:67`、`ask-matt/PHASE-BOUNDARIES.md:27-34`)。「它买到的是**可移植性**,不是压缩。没有东西要旅行,就不需要它」(`docs/productivity/handoff.md:5`)。

**它自己承认的两个缺陷**:

- 临时目录会被清:「有些环境在 session 之间清 temp(Codex 是有报告的案例),`/private/tmp` 重启即没。下个 session 不在一小时内开始、或换 harness 开始的话,写完就自己拷到持久位置」(`docs/productivity/handoff.md:48`);
- 「它抓到了 what,没抓到 why」是「公允且反复出现的批评」;更危险的是「留意本次 session 从未实际验证过的自信断言:『X 没建』『Y 做完了』。**下一个 agent 把这份文档当合同,不会去复核**,于是一个信念被写成事实,就成了后面一切的假前提」(`:60`)。

### 5.2 phase boundary 决策树(跨会话的总纲)

五个选项按序判,第一个 yes 胜(`ask-matt/PHASE-BOUNDARIES.md:19-40`):

1. **能不能就在本 session 继续?** 两种情况为是:下一 phase 需要本 phase 作为**一手来源**;或 smart zone(~150k token)还够。grilling → implementation 是标准的「是」,因为实现要的是逐字的推理而不是它的摘要。
2. **上下文与下一步无关?** → `/clear`。最便宜,且不是终态(旧 session 仍可 resume)。判错的代价是单向的:清掉相关上下文就丢了**为什么**,回读 diff 也换不回来。
3. **需要交接吗?** → `/handoff`,四种情况见上。
4. **能 AFK 吗?** → 子代理。自动 review 是标准场景。
5. **否则 `/compact`。** 是**默认但不是首选**,排在最底,因为上面四问更便宜或更精确。

底层原理:「除 Continue 外的每一步都把**一手来源**变成**二手来源**」,并给了一张信息量 / 噪声 / 腾挪空间的权衡表(`PHASE-BOUNDARIES.md:42-51`)。

### 5.3 与 Trellis 的 journal / workspace 的粒度对比

⚠️ **本次只读了 mattpocock/skills,没有读 Trellis 的任何文件,Trellis 侧的 journal/workspace 具体形态未核实。** 下面只客观陈述 matt 侧的状态粒度,以及**它明确没有的东西**,供与 Trellis 侧做差集。

matt 侧**有**的状态粒度:

- 工作项级(issue / `.scratch/issues/NN-*.md`):标签、正文、评论、blocking 边、assignee(仅 wayfinder 用)。
- 知识级(`CONTEXT.md` 词汇表、`docs/adr/`、`.out-of-scope/`)。
- 决策索引级(wayfinder map 的 `Decisions so far`,一决策一行 + 链接)。
- 一次性交接级(handoff 文件,写在 temp,是「transit document,不是你要维护的 artifact」,`docs/productivity/handoff.md:45`)。

matt 侧**没有**的:

- **没有会话 / 运行日志。** 全链条没有任何「append-only 记录本次 session 干了什么」的文件;`retro` 需要这类状态时得去「翻这台机器上的 session 日志」(`retro/SKILL.md:13`),说明它认定这类记录在 harness 里、不在项目里。
- **没有步骤级 / 进度级状态。** 票只有 open/closed;实现过程中的中间态、部分完成、失败重试,一律无处可记。
- **没有给代码周期用的跨 session workspace 目录约定。** `loop-me` 有 workspace 概念,但它管的是个人 workflow 规格(`workflows/*.md` + `NOTES.md`),不接代码周期链。
- **没有断点续跑。** 唯一带「恢复」语义的是 triage 的 Resuming a previous session:去读 issue 上的历史 triage notes,看报告者答没答,别重问已解决的问题(`triage/SKILL.md:110`)—— **恢复的介质是 issue 评论,不是日志**。

因此,如果 Trellis 的 journal 是「每次 session/step 追加一条」的量级,matt 侧对应位置是**空的**;它把等价功能推给了两处外部物:issue 的评论区,和 harness 自己的 `/compact` / session resume。

---

## 6. 判断:骨架 / 插件 / 轻在哪 / 代价

### 6.1 骨架(去掉链条就断)

判据:**是否产出下一环必须消费的持久状态**。

| 技能 | 为什么是骨架 |
|---|---|
| `setup-matt-pocock-skills` | 它写的 `docs/agents/*.md` 是 tracker 的**唯一定位方式**;三个下游技能对它是**硬依赖**:`to-tickets`、`to-spec`、`triage` 都写「没提供就叫用户去跑 setup」,ADR 明文把这三个划为 hard-dependency、其余为 soft-dependency(`.agents/adr/0001-explicit-setup-pointer-only-for-hard-dependencies.md:7-8`) |
| `to-tickets` | 唯一产出**状态单元 + 依赖边**的技能(`to-tickets/SKILL.md:38`、`:62-63`);frontier 概念的定义者(`:65`)。没有它就没有可调度的对象 |
| `implement` | 唯一产出代码变更的环节(`implement/SKILL.md:15`) |
| `triage` | 状态机本体(五个 state role,`triage/SKILL.md:31-37`),也是外来工作进入链条的唯一合法入口(`docs/engineering/triage.md:99`) |
| `to-spec` | 半骨架。它产出的 spec 是 `code-review` 的 Spec 轴要比对的那份文档(`code-review/SKILL.md:26-32`),也是 wayfinder 的汇入点(`ask-matt/SKILL.md:46`);但小活可以跳过它直接 `/implement`(`ask-matt/SKILL.md:24`) |
| `code-review` | **在骨架位置上,但不承重。** `implement` 会调它(`implement/SKILL.md:13`),可它不写任何持久物、不改状态、findings 也不被执行(`docs/engineering/implement.md:53`)。结构上是骨架,功能上是建议 |

### 6.2 可选插件(拿掉链条照转)

| 技能 | 为什么可选 |
|---|---|
| `grill-with-docs` / `grill-me` | 两者本体都只有一行转调(`grill-with-docs/SKILL.md:7`、`grill-me/SKILL.md:7`),是 `grilling` 原语的命名入口。产出是对话;落盘那部分是 `domain-modeling` 干的 |
| `grilling` | 被复用的原语(triage、wayfinder、improve-codebase-architecture 内部都跑它,`ask-matt/SKILL.md:78`),但不产出任何状态 |
| `domain-modeling` | 产 `CONTEXT.md`/ADR,但**懒创建**,且下游对缺失文件的处理是「静默继续,不要提示缺失、不要建议预先创建」(`setup-matt-pocock-skills/domain.md:11`)。设计上就是可缺席的 |
| `research` / `prototype` | 是 wayfinder 的两种票型和主链的绕道(`wayfinder/SKILL.md:77-78`、`ask-matt/SKILL.md:18-21`),按需触发 |
| `tdd` | `implement` 说「尽量用」(`implement/SKILL.md:9`),不是必经 |
| `wayfinder` | 作者自称「情境化 on-ramp,不是默认前门」,只在「一个 session 装不下的想法」时用(`docs/engineering/wayfinder.md:101`) |
| `handoff` / `claude-handoff` | 五选一的 phase boundary 选项里排第 3,且被说成「你会用得比另外四个都少」(`docs/productivity/handoff.md:74`) |
| `loop-me` / `retro` / `implement-spec` | 全在 `in-progress/`,「不进 plugin、不进顶层 README、无文档页、可能随时改动或消失」(`skills/in-progress/README.md:3`);`retro` 自标 STUB(`:18`) |

### 6.3 它「轻」在哪:七个「没有」

1. **没有运行时,全是 markdown prompt。** setup 自称「这是 prompt 驱动的技能,不是确定性脚本」(`setup-matt-pocock-skills/SKILL.md:15`);周期链上零脚本(§4.6)。
2. **没有自己的状态库。** 状态寄生在 issue tracker,并明文拒绝为新 tracker 写适配(`.out-of-scope/mainstream-issue-trackers-only.md:7`)。
3. **没有 session/run 日志、没有 journal。**(§5.3)
4. **没有完成回写。** `implement` 无完成步骤(`docs/engineering/implement.md:53`)。
5. **没有并发编排。** 一次一票,并行是已知会出事的(`docs/engineering/implement.md:57`);任务图并发还在 beta(`implement-spec`)。
6. **没有确定性校验 / hook。** 连 triage 标签都不自动创建(`docs/engineering/setup-matt-pocock-skills.md:67`)。
7. **没有用户级配置。** 「每个 repo 各自带一份 `docs/agents/`」,跨多仓的用户级模式不存在,有 open request(`docs/engineering/setup-matt-pocock-skills.md:78`)。

配套的架构自觉写在同一处:「这些文件是仓库之间**唯一**变化的东西。技能本身各处相同」(`docs/engineering/setup-matt-pocock-skills.md:5`)。这是它轻的根源 —— 把所有 per-repo 差异挤进三个 markdown 文件。

### 6.4 代价:依赖什么外部系统

| 依赖 | 具体形态 | 出处 |
|---|---|---|
| **人** | 周期链上 13 个技能带 `disable-model-invocation: true`,链条的调度器就是人手动敲 slash command;`/clear`、关票、勾验收标准、处理 review findings,全是人的动作 | §1.5、`docs/engineering/implement.md:9`、`:53` |
| **`gh` / `glab` CLI 及其登录态** | 全部 tracker 操作是 CLI 命令拼装 | `issue-tracker-github.md:7-12`、`issue-tracker-gitlab.md:7-13` |
| **GitHub native issue dependencies** | 必须用数字 database id 而非 `#number`,且要走 `gh api` 原始端点;不可用时降级为正文文本行(frontier 就不再视觉化) | `issue-tracker-github.md:42` |
| **GitLab 付费层** | native blocking link 是 Premium/Ultimate 功能,免费层只能退回文本 `Blocked by:` 行 | `issue-tracker-gitlab.md:43` |
| **模型自觉** | 所有 gate 是文字:「结尾跑一次全量套件」「预先约定 seam」「每条 finding 带引用」,无一被强制 | §4 |
| **harness 自身** | `/clear` `/compact` 语义、`claude --bg` 子命令(`claude-handoff/SKILL.md:8`)、后台 agent(`research/SKILL.md:7`)、session 日志(`retro/SKILL.md:13`)、OS 临时目录(`handoff/SKILL.md:8`) |
| **命名空间** | `code-review` 与 Claude Code 内置同名冲突,谁赢取决于安装方式,**未修**;社区解法是 fork 改名 | `docs/engineering/code-review.md:52` |
| **子代理不失控** | `code-review` 的子代理会重新发现自己并扇出,报告过 50+ agent,修法未进发布版 | `docs/engineering/code-review.md:56` |

### 6.5 给「自建轻 harness」的三条可搬 / 两条别搬

**值得搬**:

1. **per-repo 配置只有三个 markdown、技能本体零差异**这个切法(`docs/engineering/setup-matt-pocock-skills.md:5`),是这套体系最干净的一处设计。
2. **blocking edges + frontier + 一票一 fresh session** 这组约束(`to-tickets/SKILL.md:33`、`:38`、`:65`),外加 wide refactor 的 expand–contract 例外(`:40`)—— 例外写清楚了,规则才敢硬。
3. **phase boundary 五选一决策树**(`ask-matt/PHASE-BOUNDARIES.md:19-40`)与「一手来源 vs 二手来源」的权衡表(`:42-51`),是跨会话这件事上少见的能照做的判据。

**别照搬**:

1. **完成态不回写。** frontier 靠「blocker 已 closed」计算,而没有任何一环去 close(`docs/engineering/implement.md:53`)。自建时这一笔必须补,否则依赖图是死的。
2. **审查无兜底。** `code-review` 自己承认不逐条复核、无收敛保证、只看已提交 diff 而 `implement` 在 commit 前调它(`docs/engineering/code-review.md:68`、`:72`、`:76`)。要么让 review 在 commit 之后跑,要么给 findings 一个必须处理的落点。

---

## 附录:本次实际读过的文件

**技能本体**:`skills/engineering/{setup-matt-pocock-skills,triage,grill-with-docs,to-spec,to-tickets,wayfinder,implement,code-review,research,prototype,tdd,domain-modeling,ask-matt}/SKILL.md`、`skills/productivity/{grill-me,grilling,handoff}/SKILL.md`、`skills/in-progress/{claude-handoff,implement-spec,loop-me,retro}/SKILL.md`

**子文件**:`setup-matt-pocock-skills/{domain,issue-tracker-github,issue-tracker-gitlab,issue-tracker-local,triage-labels}.md`、`triage/{AGENT-BRIEF,OUT-OF-SCOPE}.md`、`prototype/{LOGIC,UI}.md`、`domain-modeling/{CONTEXT-FORMAT,ADR-FORMAT}.md`、`ask-matt/PHASE-BOUNDARIES.md`

**桶 README 与仓库级**:`skills/{engineering,productivity,in-progress}/README.md`、`CLAUDE.md`、`CONTEXT.md`、`.claude-plugin/plugin.json`、`.gitignore`、`.agents/adr/0001-*.md`、`.out-of-scope/mainstream-issue-trackers-only.md`

**文档页**:`docs/engineering/{implement,code-review,to-tickets,triage,wayfinder,setup-matt-pocock-skills}.md`、`docs/productivity/handoff.md`

**未读**(故未在本文出现):`skills/engineering/{diagnosing-bugs,codebase-design,improve-codebase-architecture,resolving-merge-conflicts,wizard}`、`skills/productivity/{teach,to-questionnaire,wait-what,writing-for-agents}`、`skills/misc/*`、`skills/in-progress/{writing-*,setup-ts-deep-modules}`、`.agents/adr/0002`、`CHANGELOG.md`、Trellis 仓库(**未核实**)。
