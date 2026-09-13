# 选材分析:Trellis 与 Matt skills,给「轻量项目级周期 harness」的取材依据

> 综合 6 份读者报告(`research/01`~`06`),对读者之间冲突的数字**逐条回源复核**(复核清单见 §7.2)。
> 溯源基准:Trellis = `scratchpad/trellis`(HEAD `88f4834`,`0.6.16`);Matt = `scratchpad/mattskills`(HEAD `3cca18b`,`package.json:3` = `1.2.3`);harness-creator = `/Users/sangba/Downloads/02-代码脚本/工具脚本/harness/harness-creator`;owner 现状 = `~/.claude/`。
> 本文只做选材,不写实现、不出目录、不出模板、不替 owner 拍板。

---

## 1. 一句话结论

**Trellis 的周期模型 = 磁盘状态机 + 每回合朗读。** 一个任务一个目录(`.trellis/tasks/<MM-DD-slug>/`),状态是 `task.json` 里的一个 `status` 字段,只有三个值 `planning → in_progress → completed`,全仓只有 7 个合法写者且被一张 spec 表锁死(`.trellis/spec/cli/backend/workflow-state-contract.md:251-270`);推进靠 `UserPromptSubmit` hook 每一轮从 `.trellis/workflow.md`(709 行,本次 `wc -l` 复核)里按当前 status 抠出对应的 `[workflow-state:*]` 文本块注入上下文。

**Matt 的周期模型 = 外部 issue tracker + 人手敲斜杠命令。** 状态寄生在你自己选的 tracker 里(GitHub / GitLab / 本地 markdown,选择记进 `docs/agents/issue-tracker.md`,`skills/engineering/setup-matt-pocock-skills/SKILL.md:38-49`),状态即标签(5 个 state role + 2 个 category role,`skills/engineering/triage/SKILL.md:31-41`),依赖关系即 tracker 的 native blocking 边;推进全靠人打 user-invoked 命令,周期链上 13 个技能带 `disable-model-invocation: true`,整条链**零 hook 零脚本**(`research/04` §4.6,本次复核 `skills/engineering/implement/SKILL.md:4` 确认)。

### 根本分歧,三条

| 分歧轴 | Trellis | Matt |
|---|---|---|
| **状态放哪** | 仓库内固定目录 + `task.json` 单字段,进 git;会话指针另存 `.trellis/.runtime/sessions/`,gitignored | 外部 issue tracker,靠一层 `docs/agents/issue-tracker.md` 间接寻址;技能本体零 per-repo 差异(`docs/engineering/setup-matt-pocock-skills.md:5`) |
| **谁驱动转换** | 脚本 + hook。`task.py create/start/archive` 是唯一合法写者;hook 每轮把「你现在该干什么」推进上下文,理由是生产事故——「强制步骤没在 breadcrumb 里提到,AI 就会静默跳过」(`.trellis/workflow.md:113-118`) | 人。路由器 `ask-matt` 只推荐不点火(`docs/engineering/ask-matt.md:5`);理论依据是 context load 记账——常驻材料每轮都在收税,而 cognitive load「不是要最小化的成本,它是人类能动性的价格」(`skills/productivity/writing-for-agents/SKILL.md:24-25`) |
| **验证靠机制还是靠文字** | 几乎全靠文字。`.claude/hooks/` 全树只有两处 `permissionDecision`,值都是 `"allow"`,零 `"deny"`(本次 grep 复核,`inject-subagent-context.py:1188,1197`)。唯一硬门是 `task.py start` 的 jsonl 非空校验(`task.py:194-215`),它检的是**上下文准备度**不是产出质量;没有任何「未 check 不能 finish」的门 | 全靠文字。唯一带机械性的一条是「结尾跑一次全量测试套件」(`skills/engineering/implement/SKILL.md:11`),而且**没说必须绿**;唯一真做验证动作的是 triage 的「先复现再 grilling」(`skills/engineering/triage/SKILL.md:74`) |

**两者共同的空白:验证这一环,谁都没有机制。** 这一点直接决定了 owner 不该向任何一方取材来补验证——owner 自己那侧反而更硬(Stop hook 的 ruff/mypy/biome 链 + `agents/adversarial-reviewer.md`)。

**两者共同的最大差异不是「重/轻」,是「谁当调度器」。** Trellis 把调度器做进了 hook(代价:每轮 0.4–0.9 KB 常驻税 + 14,163 行运行时 Python);Matt 把调度器留给人(代价:忘了敲命令这步就没做,而且链条在完成回写处**断了**——`implement` 没有完成步骤,不关票、不勾验收框,而 frontier 定义为「blocker 全部 closed」,于是没有票会变成可见的未阻塞,`docs/engineering/implement.md:53`,本次逐字复核)。

---

## 2. 周期链逐环对比表

列说明:**harness-creator** 是 owner 手里那份 MIT 的基准 skill(`harness-creator/SKILL.md:22-31` 的五子系统);**owner 现状**分「已有」与「空缺」。

| 环 | Trellis | Matt | harness-creator | owner 现状 |
|---|---|---|---|---|
| **开工** | SessionStart hook 一次性注入 ~7–8 KB 结构化 payload(`<current-state>`/`<task-status>`/`<ready>`,`.claude/hooks/session-start.py:866-916`);无任务时先分诊「这轮要不要建任务」——规则在 Phase 1 walkthrough 的 Request Triage(`.trellis/workflow.md:152-156`),同一条也写进 `[workflow-state:no_task]` breadcrumb 块每轮注入(`.trellis/workflow.md:176-180`) | 无开工动作。一次性的 `setup-matt-pocock-skills` 写三个 `docs/agents/*.md` 决定去哪发 issue(`setup-matt-pocock-skills/SKILL.md:38-49`),之后每次开工就是人打 `/grill-with-docs` | 一段可执行 Startup Workflow 写在指令文件里:`pwd` → 读本文件 → 读项目文档 → 跑 `./init.sh` → 读 `feature_list.json` → `git log -5`(`templates/agents.md:5-16`) | **已有**:SessionStart 上 `hooks/handoff-check.sh` 注入上次交接笔记(`:66` jq 输出 additionalContext,本次复核);`/kickoff` 调研闸门(`commands/kickoff.md:10-13`)。**空缺**:没有任何 Startup Workflow;注入的是「上次的笔记」不是「项目现在的状态」(`research/06` §1.5) |
| **需求澄清** | Phase 1.1,`trellis-brainstorm` skill 一次只问一个最高价值问题,带「Non-Negotiable Planning Contract」:build/fix/「go ahead」都不算离开 planning 的批准(`.claude/skills/trellis-brainstorm/SKILL.md:9-15`);产出必须落 `prd.md` | 主链第 1 步 `grill-with-docs`,本体只有一行「调两次 Skill 工具:grilling 和 domain-modeling」(`skills/engineering/grill-with-docs/SKILL.md:7`);`grilling` 按 design tree 的 frontier 一轮多问,**事实归 agent 查、决策归人定**,frontier 空且用户确认才算完(`skills/productivity/grilling/SKILL.md:8,26,28`) | 无澄清环。只在 Escalation 里说「需求不清就查产品文档,没有就问用户」(`templates/agents.md:66`) | **已有**:`CLAUDE.md:13` 一行「Brainstorm 先于代码」;`/pm` 模式内的问题塑形与双层 map(`commands/pm.md:17-22`);`rules/design-doc.md:13-18` 的五节写法。**空缺**:零 hook、无落盘要求、无「澄清完成」判据——全链两个零机械环之一(`research/06` §2) |
| **拆任务** | Phase 1.0 `task.py create` 建目录;复杂任务要 `prd.md`/`design.md`/`implement.md` 三件套齐才能 start(`.trellis/workflow.md:158-164`);父子任务双向链接 `parent`/`children`,但明写「父子结构不是依赖系统」(`:170`) | `to-spec` → `to-tickets`。核心是 **tracer bullet**:每票纵切所有层、完成即可演示、尺寸恰好塞进一个全新 context window(`to-tickets/SKILL.md:29-36`);**blocking edges + frontier**(`:38`,`:65`);wide refactor 例外走 expand–contract(`:40`) | `feature_list.json`:一条 feature 带 `id/name/description/dependencies/status(not-started\|in-progress\|blocked\|done)/evidence`,`required` 只有前四项(`templates/feature-list.schema.json:12-42`,本次逐行复核);规则「一次只做一个 feature」(`templates/agents.md:20`) | **已有**:`CLAUDE.md:14` 的 `[step] → 执行者 → verify: [check]`;`os/WORKERS.md:23` 的任务包字段集(含 Write scope / Do not touch)。**空缺**:全部不落盘,任务包是一次性提示词;无依赖边、无 done 判据落盘——全链另一个零机械环 |
| **实现** | Phase 2.1,主会话**派** `trellis-implement` 子代理,子代理自我豁免不得再派(`.trellis/workflow.md:228`);PreToolUse hook 在派工前把 jsonl 引用文件 + prd/design/implement 按固定顺序塞进子代理 prompt,128 KB 硬预算,超限降级为索引行(`inject-subagent-context.py:534-590`);子代理**禁 git commit/push/merge** | `/implement`,全文 15 行(本次 `cat -n` 复核):尽量用 `/tdd`、在**预先约定的 seam** 上、结尾跑一次全量套件、跑 `/code-review`、commit 到当前分支。一次一票,票间 `/clear`;并行已知会出事(`docs/engineering/implement.md:57`) | 「一次一个 feature」「不改与当前 feature 无关的文件」(`templates/agents.md:20-23`) | **已有(且是强项)**:`rules/*.md` 按 `paths:` 前置匹配注入编码规则;派工分流与档位(`os/MODELS.md`、`os/WORKERS.md`);硬闸 `hooks/subagent-model-guard.sh`、`hooks/file-size-budget.sh`、`hooks/workflow-agent-cap.sh`。**空缺**:无 |
| **验证/审查** | Phase 2.2,`trellis-check` 子代理**同模型自审自修**(`.claude/agents/trellis-check.md:36-40`);最后一次必须全量跑,按 `--mode packages` 列出受影响包逐个加载其 spec index 的 Quality Check 段(`.trellis/workflow.md:557`)。**没有任何代码级质量门禁** | `code-review` 两轴并行子代理(仓库标准 + Fowler 12 味道基线,`code-review/SKILL.md:44-56`);自认三条缺陷:不逐条回文件复核、无收敛保证、只看已提交 diff 而 `implement` 在 commit 前调它(`docs/engineering/code-review.md:68,72,76`) | `init.sh` = 一条命令跑完本项目全部验证(`templates/init.sh:1-78`,按 package.json/pyproject/go.mod/Cargo.toml 分支);Definition of Done 四条硬勾,含「证据记录进 `feature_list.json` 或 `progress.md`」(`templates/agents.md:35-40`) | **已有(强于两家)**:Stop hook 对本会话累计改动文件跑 ruff/mypy/biome(`settings.json#hooks.Stop`);终审外派、跨模型独立(`CLAUDE.md:23`);`agents/adversarial-reviewer.md` 的证据三态与 verdict 规则;完成必须给 owner 可核验产物(`CLAUDE.md:26`)。**空缺**:没有项目级验收命令登记处(`init.sh` 等价物)。owner 侧只有语言级/领域级的分散约定——`rules/python.md:9,11`(依赖与运行只走 `uv`、ruff 规则集)、`rules/reverse-api.md:26-27`(外部 API 改动必须抓真包 + live 测试)——以及各项目 CLAUDE.md 里的零散提及 |
| **收尾/交接** | Phase 3.3 spec 回写(即使结论是「没什么可写」也要走完判断,`.trellis/workflow.md:587`)→ 3.4 七步分批提交(禁 amend、禁 push、计划只弹一次窗,`:595-639`)→ `/trellis:finish-work` 跑 `task.py archive` + `add_session.py` 写 journal;git log 顺序被写死为 工作提交 → archive → journal(`finish-work.md:66`) | **断了**。`implement` 没有完成步骤:不关票、不勾 `- [ ]`、不处理 review findings(`docs/engineering/implement.md:53`)。`handoff` 只在四种情况用(换 harness/换目录/交同事/中途分叉),写 **OS 临时目录**、刻意不进 workspace(`skills/productivity/handoff/SKILL.md:8`) | End of Session 五步:更新 `progress.md` → 更新 `feature_list.json` → 记风险 → commit → 留下能立刻跑 `./init.sh` 的干净状态(`templates/agents.md:44-50`);可选 `session-handoff.md`(`templates/session-handoff.md:1-40`) | **已有(owner 最完整的一件,写入端+消费端互相点名)**:`commands/handoff.md` 全文(落盘三级、已存在时归档不覆盖、内容含「不要再试:X,因为已验证 Y」)⇄ `hooks/handoff-check.sh`(按 cwd 过滤 + 7/30 天分档)。**空缺**:无「未写交接就 Stop」兜底 |
| **续工** | 两条通道:SessionStart 注入 `<task-status>` 五态 Next-Action(`session-start.py:424-511`);`/trellis:continue` 的 **(status × 产物存在性) → 下一步** 路由表(`.claude/commands/trellis/continue.md:27-34`,本次逐行复核) | 没有断点续跑。恢复介质是 issue 评论(`triage/SKILL.md:110`);跨会话总纲是 phase boundary 五选一有序树,第一个 yes 胜,`Continue` 第一、`/compact` 垫底(`ask-matt/PHASE-BOUNDARIES.md:19-40`) | 下次会话读 `AGENTS.md` → `feature_list.json` + `progress.md` → handoff → 跑 `./init.sh`(`templates/session-handoff.md:31-36`) | **已有**:`handoff-check.sh` 的 SessionStart 注入;UserPromptSubmit 上 `hooks/pm-mode-state.py` 在 pm 模式激活的会话里每轮 `print(REMINDER)`(`:43-45` 的 `if marker.exists()` 守卫;未激活时该 hook 不输出)——**通道验证过能用,但只推一句固定文本**(本次复核 `:9` 的 REMINDER 内容)。**空缺**:无任务级 per-turn 内容;提醒本身在压缩后照常发,但它指向的 `commands/pm.md` 已掉出上下文,owner 为此在 `commands/pm.md:10` 写了「先重读本文件再干活」的补丁——同一个坑换到任务状态上就没有补丁 |

### 读这张表的四条结论

1. **owner 的空缺集中在两处,不是七处**:拆任务(状态不落盘)与续工(per-turn 通道空载)。其余五环 owner 已有等价物或更强。
2. **续工是成本最低的空缺**:机制位在跑、脚本形态有先例(`pm-mode-state.py`),补的是内容不是机制。
3. **Trellis 与 harness-creator 在「状态」这一格是同构的**,只是粒度不同:Trellis 一任务一目录+status,harness-creator 一 feature 一条 JSON+status+evidence。**harness-creator 多一个 Trellis 没有的字段:`evidence`**(`feature-list.schema.json:37-40`)——这一格恰好对上 owner `CLAUDE.md:26` 的「可观察产物」和 `os/WORKERS.md:31` 的证据优先序。
4. **Matt 在这张表里唯一无可替代的贡献在「拆任务」一格**(tracer bullet + blocking edges + frontier + 一票一 fresh session),其余各格要么断链要么空。

---

## 3. 重量拆解:Trellis 的重量从哪来

全部数字来自读者实测,标 ✔ 的是本次回源复核过的。

### 3.1 按来源分类

| 来源 | 数字 | 出处 | 属性 |
|---|---|---|---|
| **运行时 Python(装进你仓库的)** | 14,163 行 / 31 文件 = `.trellis/scripts` 11,514 行(28 个 .py)+ `.claude/hooks` 2,649 行(3 个 .py) | `research/02` §5.1 `wc -l` 实测;`research/03` §4.2 独立复算一致 | 混合:约 10% 是周期决策,其余是多平台/容错 |
| **CLI TypeScript** | 26,841 行 / 119 个非测试 .ts;core 10,473 行 | `research/03` §4.4 | 纯分发,与周期无关 |
| **周期相关的 TS** | core 10,473 行里只有 `src/task/` 的 **561 行**(5.4%),且它不做任何生命周期动作,只是 task.json 读写器 + 目录名校验 + status→phase 投影 | `packages/core/src/task/index.ts:1-31`、`schema.ts:1-11`(自述「TS 侧是 Python 侧的镜像」) | — |
| **平台适配** | **22** 个平台(`packages/cli/src/types/ai-tools.ts:10-32` ✔);configurators 25 个文件 = 22 平台 + index/shared/workflow ✔;`packages/cli/src/templates/` 下 **19** 个平台目录 ✔;仓库里 7 个平台目录共 385 个文件(不含 .backup);`.template-hashes.json` 记 228 个受管模板 | `research/02` §5.3、`research/03` §3.2;平台数与目录数本次 `ls` 复核 | **纯多平台税** |
| **双运行时** | Node ≥ 18.17 + Python ≥ 3.9,两个都硬失败(`packages/cli/src/commands/init.ts:147-157`);外部 npm runtime 依赖 7 个;**Python 第三方依赖 0**,连 YAML 都是自己写的 114 行解析器(`common/trellis_config.py:113-226`) | `research/03` §4.1-4.2、`research/02` §5.2 | 多平台税的后果(hook 要被 22 家 host 以 `python3 x.py` 直接调起) |
| **状态文件数** | 一个 Claude-only 新项目 init 后落盘约 **100 个文件**(`.trellis/` ≈52 + `.claude/` ≈52);长期运行后本仓 `.trellis/tasks/` 累计 **1,361 个文件**、242 个任务目录 ✔、单任务平均 5.6 个文件;`.trellis/spec/` 41 个 md;journal 10,437 行 | `research/02` §5.4-5.5;任务数本次 `find` 复核 | 混合 |
| **注入上下文量** | SessionStart 一次性 **7–8 KB**(其中 workflow.md 的 Phase Index 剥离后 5,632 字符);UserPromptSubmit 每轮 **0.4–0.9 KB**(`in_progress` 块最大 930 字符);PreToolUse 派子代理时按 **128 KB** 硬预算(单文件 32 KB / 单 artifact 64 KB) | `research/02` §2.1-2.3;`config.yaml:151-154` | 每轮那 0.4–0.9 KB 是**周期管理本身的必需成本**,另两项是子代理架构的成本 |
| **版本兼容机器** | 148 份 migration manifest / 395 条迁移 / 6 个 breaking,覆盖 0.1.9 → 0.7.0-beta.3 | `research/03` §3.3 | **纯产品化分发税**,自用为零 |

### 3.2 哪些重量是「多人多平台税」

按「单人 + 单平台(Claude Code)+ 项目级」这一条判据切:

| 税种 | 体量 | 判据 |
|---|---|---|
| **多平台条件块** | `workflow.md` 709 行里约 6 处平台条件块,2.1 一个步骤写了 4 个平台变体;22 个 configurator;19 个平台模板目录;`inject-workflow-state.py` 488 行里核心逻辑不到 80 行,其余是 Windows 流重配/stdin 超时/Gemini 事件名/Kiro 裸文本输出等分支 | 单平台全部归零(`research/02` §6.1) |
| **会话身份解析** | `common/active_task.py` 857 行,其中 21 个平台的 session 环境变量表约 200 行。**且这块的前提在多数平台不成立**——Trellis 自己的研究结论:「21 个平台里没有一个默认把 session id 导给 shell 子进程;14 个声明的环境变量名里 9 个是凭空造的」(`tasks/08-05-session-identity-propagation/research/platform-session-identity.md:12-17`) | 单窗口一个文件指针就够 |
| **多开发者身份 + journal 轮转 + 三级 index** | `add_session.py` 1,545 行、`common/developer.py` 192 行、`.developer` 文件、每人一套 `workspace/<dev>/`、2000 行轮转、三个 `@@@auto` 块。**反证**:全局 `workspace/index.md:28-31` 只记着一个开发者 12 次 session,而磁盘上有 7 个开发者目录、taosu 一人 175 次 session、最后活跃 2026-08——**全局 index 无自动写者,已陈旧 7 个月** | 它服务的场景(多人互看进度)在作者自己仓库里都没发生 |
| **monorepo package/layer 分层** | `config.yaml:56-85` 的 packages 声明、`--mode packages`、spec 的两级目录、`session-start.py` 的 `_resolve_spec_scope`(178 行) | 单包项目全部退化成一层目录 |
| **模板哈希 + migration 机器** | 228 条哈希 + 148 份 manifest | 自己的 harness 自己改,git 就够 |

### 3.3 哪些重量是「周期管理本身必需」

| 必需项 | 最小体量 | 为什么不能省 |
|---|---|---|
| **状态即文件** | 一个 `task.json` 的 status 字段 | 整套跨会话续工建立在「读目录里有哪些文件」之上,没有第二真相源(`.trellis/workflow.md:9`「Persist everything —— 对话会被压缩,文件不会」) |
| **每回合 breadcrumb** | 0.4–0.9 KB/轮 | 这是**用生产事故换来的**:`.trellis/workflow.md:113-118` 记着「breadcrumb 是任务活动期间唯一的 per-turn 通道,强制步骤没在里面提到,AI 就会静默跳过」,并点名 Phase 1 planning gate 与 Phase 3.4 commit 两次事故都是这个失效模式 |
| **单一文本真相源 + 一致性测试** | 一条断言 | v0.5.0-rc.0 后删掉了脚本里的 fallback 文本字典,解析不到就降级成显眼的「Refer to workflow.md」;配套用回归测试锁死「每个 `[required · once]` 步骤必须在对应 breadcrumb 块里被提到」。**没有后者,前者会慢慢腐烂**(`research/01` C4) |
| **原子写** | ~30 行 | 半写的 task.json 会让所有 hook 把任务显示成 status unknown 且无人报错(`research/02` §6.2) |
| **状态写者表** | 一张表 | 状态只有三个值不复杂,价值在于把「谁能改状态」变成可审计的有限集合(`workflow-state-contract.md:251-270`,还给了核验命令 `grep -rn '"status"' .trellis/scripts/`) |
| **archive 是唯一完成事件** | 语义约定 | `finish` 只清会话指针不改 status,任务可能在别的会话继续;想在外部系统标完成必须订阅 `after_archive`,这条被单列进 DON'T(`workflow-state-contract.md:273-289, 383-384`) |

### 3.4 一条最有说服力的反证:被硬门禁的东西,作者自己一半以上没做

本次**逐文件复核**了 242 个任务(`find .trellis/tasks -name task.json | wc -l` = 242),用 Trellis 自己 `curated_entry_count()` 的判定语义(`common/task_context.py:128-153`:一行 JSON 对象带 truthy `file` 或 legacy `path` 即算一条)统计:

| artifact | 数量 | 占比 |
|---|---|---|
| `prd.md` 存在 | 234 | **97%** |
| `design.md` 存在 | 35 | **14%** |
| `implement.md` 存在 | 35 | **14%** |
| `implement.jsonl` 有 curated 条目 | **107** | 44% |
| `implement.jsonl` 存在但 curated 数为 0 | 52 | 21% |
| `implement.jsonl` 根本不存在 | 83 | 34% |
| 仍残留 `_example` 种子行的 jsonl 文件 | 123 | — |

(`check.jsonl` 同口径:107→106,52→53。以上全部为本次复核实测。)

**解读三条:**
1. `task.py start` 对 jsonl 硬门禁(`task.py:194-215`,唯一逃生阀 `--allow-empty-context`),而 **135/242(56%)的任务这个文件是空的或不存在的**。一个「必经关卡」在作者自己的仓库里被绕过一半以上,说明它索取的准备成本高于交付的价值。
2. `design.md`/`implement.md` 被写成「复杂任务必须有」,实际只有 14% 的任务有——即 **86% 的真实任务是轻量任务**。
3. `prd.md` 是唯一被普遍使用的规划产物(97%)。**如果只保留一件规划产物,数据说应该是它。**

### 3.5 Trellis 的方向:表面变轻,实质变重

v0.5.0 那次是命令面的一次性整理(命令 8→3,清理 126 条 safe-file-delete + 12 条额外操作,`drafts/v0.5.0-beta-forum-post.md:107`),但同一份发帖稿承认 SessionStart payload 从 2.7 KB 增到 9.5 KB、`task.py` 命令表从 5 条扩到 16 条(`drafts/v0.5.0-beta-forum-post.md:118-123`)。之后 0.6 净增 `core/channel` 4,544 行 + `core/mem` 5,357 行;0.7-beta 的 manifest 已经写着「workflow 从一份变成 task / developer / team / global 四层解析链」(`migrations/manifests/0.7.0-beta.0.json`)。

**对 owner 的直接含义**:「Trellis 有多重」这个问题有两个不同的答案,取决于拿哪一版当参照物——v0.5.0 减重后的形态(3 命令 + 5 skill + workflow.md + task.py,`drafts/v0.5.0-beta-forum-post.md:25`)与当前 0.6.16(多 `core/channel` 4,544 行 + `core/mem` 5,357 行)。选哪一版是 owner 的判断,本文各处数字若未特别标注,取的是 0.6.16 的实测。

---

## 4. 轻量自建的候选取材清单

判据三条:① 这一点是不是在解决「周期语义」而不是「多平台/多人/容错」;② owner 现有机制是否已覆盖(覆盖就是「不取」,依据 `CLAUDE.md:7` 不重复造轮子 + `research/06` §6.2);③ 有没有实证支持(作者自己用不用)。

### 4.1 取(真空缺,要做)

| # | 设计点 | 来源 | 一句话理由 |
|---|---|---|---|
| T1 | **状态即文件系统**:任务状态是磁盘上的文件与其存在性,不是对话里的记忆 | Trellis `.trellis/workflow.md:9` | owner 侧全链只有会话末快照与一个布尔 marker,中途中断什么都不剩(`research/06` §6.1 空缺 1) |
| T2 | **(status × 产物存在性) → 下一步 的路由表** | Trellis `.claude/commands/trellis/continue.md:27-34` | 跨会话续工的本质就是这张表:新会话不读历史对话,只读「状态 + 哪些文件在」就能算出该干什么;比 Trellis 自己那 5,357 行的 mem 检索便宜几个数量级且更可靠(`research/03` §7.1) |
| T3 | **每回合 breadcrumb**:按当前状态从**单一 Markdown 源**抠出对应文本块注入 | Trellis `.trellis/workflow.md:99-142` + owner 已验证通道 `hooks/pm-mode-state.py:43-45` | 通道已在跑、脚本形态有先例,补的是内容不是机制;Trellis 用两次生产事故证明了不注入就会被跳过 |
| T4 | **强制步骤 ↔ breadcrumb 文本 的一致性断言** | Trellis `.trellis/workflow.md:113-118` | 没有它,T3 的单一真相源会随编辑慢慢腐烂。这是 owner `CLAUDE.md:10`「机制有真实消费者、链条走得通」的同一条自查 |
| T5 | **evidence 字段进状态文件** | harness-creator `templates/feature-list.schema.json:37-40` | Trellis 全套 24 字段里**没有**证据字段(本次复核 `packages/core/src/task/schema.ts:13-38`);而 owner `CLAUDE.md:26` 与 `os/WORKERS.md:31` 已经把「证据优先序」写成纪律,缺的正是它的落盘位 |
| T6 | **依赖边 + frontier**:每个单元声明「哪些必须先完成」,可开工集合 = blocker 全 done | Matt `to-tickets/SKILL.md:38,65`;harness-creator `feature-list.schema.json:25-31` 的 `dependencies` | owner 侧 `CLAUDE.md:14` 的多步计划只活在对话里,没有依赖概念;两家独立给出同一形状,可信 |
| T7 | **tracer bullet 切法**:每个单元纵切所有层、完成即可演示、尺寸恰好塞进一个全新 context window | Matt `to-tickets/SKILL.md:29-36`,wide refactor 的 expand–contract 例外在 `:40` | 这是「拆任务」环唯一可照做的判据,owner 侧完全没有等价物。**例外写清楚了,规则才敢硬** |
| T8 | **archive/finish 语义分离**:暂停(清指针)≠ 完成(写终态) | Trellis `workflow-state-contract.md:273-289` | 一个真实踩过的坑被固化成契约;任何有「暂停」和「完成」两个概念的系统都要区分 |
| T9 | **收尾必答一问:这次学到什么、写去哪**(即使答案是「没什么可写」也要走完判断) | Trellis `.trellis/workflow.md:587` + 3.4 的 spec-sync preamble `:591`(学习写入必须和代码在同一批提交里,不能变成被遗忘的后续项) | 这是整套周期唯一的学习闭环。owner 已有回写目的地(`CLAUDE.md:39` 的 INBOX.md),**缺的只是「收尾时必须问一次」这个动作** |
| T10 | **完成回写必须有执行者** | Matt 的反面教材:`docs/engineering/implement.md:53` | Matt 链条断在这里(frontier 靠 blocker closed 计算,而没有任何一环去 close)。owner 自建时这一笔必须补,否则依赖图 T6 是死的 |
| T11 | **项目级验收命令登记处** | harness-creator `templates/init.sh:1-78` + `templates/agents.md:52-60` | owner 侧最接近的是语言级/领域级分散约定(`rules/python.md:9,11` 的 uv 与 ruff、`rules/reverse-api.md:26-27` 的抓真包 + live 测试)与各项目 CLAUDE.md 的零散提及,新会话没有统一入口知道「本项目声称完成前该跑哪几条」(`research/06` §1.3) |

### 4.2 改(取其形,不取其量)

| # | 设计点 | 原形态 | 该改成什么方向(不是实现方案) |
|---|---|---|---|
| C1 | **规划产物分层** | Trellis 强制三件套 `prd.md`/`design.md`/`implement.md`,职责互斥(`.trellis/workflow.md:158-164`) | 实测只有 14% 的任务有后两件、97% 有 PRD(§3.4)。**保留职责边界的概念,取消「复杂任务必须有」的硬要求**,改为按需产出 |
| C2 | **双门授权**(建任务同意 ≠ 实现同意) | Trellis 三处独立强调 + 列为 fork 不可破不变量(`workflow.md:156,293,654`) | 概念要,但 owner 侧已有 `/kickoff` 闸门(`commands/kickoff.md:10-13`:未放行不产出实现物)与 `CLAUDE.md:13` 的 Brainstorm 先于代码——**是把双门接到新状态机上,不是再造一道门** |
| C3 | **父子任务** | Trellis 双向链接 + 两处派生显示逻辑 + 两代 schema 并存 | 收益是真需求(一个大请求多个可独立验证交付物),代价是一致性维护。**降级为父任务文档里的一张清单表**——依据是 Trellis 自己的父任务 PRD 就是这么写的(`tasks/08-05-session-identity-propagation/prd.md:69-81` 的验收标准就是一张勾选表) |
| C4 | **会话日志 / journal** | `add_session.py` 1,545 行 | 砍掉多人/多 worktree 的会话号收敛与幂等续跑,**只保留一条纪律**:每个 commit OID 必须能在本地对象库解析出真实 subject,否则命令失败(`add_session.py:23-28`)——它防的是 AI 编造提交记录 |
| C5 | **提交顺序契约** | Trellis 3.4 七步 SOP + 三条 Rules(禁 amend、禁 push、计划只弹一次窗,`workflow.md:595-639`) | 值得抄的是两条:**「不认识的脏文件不许静默纳入提交」**(`:611`)与「工作提交 → 归档 → 日志,绝不交错」(`:593`)。七步 SOP 本身可压缩 |
| C6 | **单入口路由器** | Matt `ask-matt`:user-invoked、零 context load、只推荐不点火、按情境六分区、每个岔路一个二值可观测测试、带反用法 | 形态可直接借(`research/05` §5.3 六条)。**必须继承的局限**:它是手写地图不扫描,技能增减时是持续人工负债;配套的维护不变量「路由器说谎」(`mattskills/CLAUDE.md:21`)是它能活下来的原因 |
| C7 | **phase boundary 决策树** | Matt 五选一有序树,第一个 yes 胜,Continue 第一、`/compact` 垫底(`ask-matt/PHASE-BOUNDARIES.md:19-40`) | 与 owner 的 `/handoff` 不冲突:owner 现在只有「写交接笔记」这一个选项,而这棵树告诉你**什么时候不该写**。可作为 `/handoff` 触发判据的上游补充 |
| C8 | **终态的数量** | Trellis 只有一个终态 `completed`,且它在正常流程里是死态(`workflow.md:250-257` 自认);harness-creator 的 feature 状态多一个 `blocked`(`feature-list.schema.json:34`);harness-creator 的运行时 reference 给的工作单元状态机是 `running → completed \| failed \| killed`(`references/lifecycle-bootstrap-pattern.md:126-129`) | 三家给了三种终态集合。**要不要区分「做失败了」与「主动放弃」是个真决策**:Trellis 的答案是不区分(归档即完成),代价是历史里看不出哪些活是黄了的;Matt 的答案是用 `wontfix` 标签(`triage/SKILL.md:82`,且只有 triage 会主动关闭) |

### 4.3 不取(与 owner 现有机制重复,或有实证反对)

| # | 设计点 | 不取的理由 | 依据 |
|---|---|---|---|
| N1 | **多平台适配层** | 单平台全部归零:22 个 configurator、19 个平台模板目录、`active_task.py` 里 200 行平台表、hook 里的 Gemini/Kiro/Codex 输出格式分支 | §3.2 |
| N2 | **会话身份解析层** | 前提在多数平台不成立(Trellis 自证 21 平台无一默认导出 session id);单窗口一个文件指针即可 | `research/01` H2 |
| N3 | **jsonl 上下文清单 + start 硬门禁** | 作者自己 56% 的任务绕过它;而且 `inject-subagent-context.py:483-506` 在 jsonl 为空时**已经**有降级路径(把「没有 spec 上下文」这件事本身写进 prompt,让子代理自己去读) | §3.4 |
| N4 | **`.trellis/spec/` 分层规范注入** | owner 已有更省的等价物:`rules/*.md` 的 frontmatter `paths:` 前置匹配,比「读 index 再读子文件」少一跳,且不占常驻上下文 | `research/06` §6.2 |
| N5 | **check/审查代理** | owner 的 `agents/adversarial-reviewer.md` 规格比 Trellis 的 check agent 细(验收标准逐条核对放第一位、证据三态、假阳性清单、verdict 只看 blocking),且 `CLAUDE.md:23` 额外要求跨模型独立;Trellis 的 2.2 是**同模型自审自修** | 同上 |
| N6 | **多 agent 编排运行时**(`core/channel` 4,544 行 + CLI 约 3,900 行) | owner 已有 `os/MODELS.md` + `os/WORKERS.md` 的通道与档位 + 两个硬闸(`subagent-model-guard.sh`、`workflow-agent-cap.sh`);而且 Trellis 自己在 v0.5.0 刚以「原生 worktree 够用了」为由删过同类东西,0.6 又造了个更大的回来 | `research/03` §6.3 |
| N7 | **mem 历史检索**(5,357 行 + 6 个会腐烂的平台适配器) | 「上次怎么解的」这个需求,用 T2 的路由表 + 交接笔记覆盖大部分;适配器腐烂已在发生(`trellis-session-insight/SKILL.md:14` 承认 OpenCode 尚不可索引) | 同上 |
| N8 | **多开发者身份 + journal 轮转 + 全局 index** | 单人无意义,且它服务的场景在作者自己仓库里都没发生(全局 index 陈旧 7 个月) | §3.2 |
| N9 | **模板哈希 + migration 机器**(228 条 + 148 份) | 「把模板发到别人仓库」这个分发模型的必然代价;自用为零 | `research/03` §3.3 |
| N10 | **项目指令文件模板** | owner 已有 `CLAUDE.md` + `rules/doc-writing.md` + `doc-filler-guard.sh`(尺寸预算)+ `institution-refcheck.py`(悬空引用体检)三层 | `research/06` §6.2 |
| N11 | **开工调研闸门** | owner 的 `/kickoff` 比 Trellis 强(Trellis 没有等价物);**反证**:owner 已经在拿 kickoff 补 Trellis(`dashboard/CLAUDE.md:14` 明写「kickoff 的调研职能写在 design.md 的对应节」) | 同上 |
| N12 | **交接笔记格式** | owner 的 `commands/handoff.md:24-35` ⇄ `hooks/handoff-check.sh:41-58` 是闭环,内容要求比 harness-creator 的 `session-handoff.md` 空表格详细得多。**新 harness 只需把它接到新状态文件上,不重写** | 同上 |
| N13 | **owner 汇报协议** | `commands/pm.md:24-27` 的固定汇报格式与「验收把握」三态,Trellis 与 Matt 都没有等价物 | 同上 |
| N14 | **prompt 库集成** | `pp.md` 是 prompt 收藏库,与周期链唯一接触点是澄清环挑工具;顶多在澄清环留一句指路 | `research/06` §4.3 |

### 4.4 三条与周期无关但会决定成败的横切纪律(可直接拿,与状态方案正交)

- **no-op 逐句测试**:一条模型默认就会遵守的指令,付了 load 什么都没说;不通过就**删整句,不修词**(`writing-for-agents/SKILL.md:81`)。这是压缩任何一份 harness 文档的通用工具。
- **两种 load 记账**:context load(常驻材料每轮收税)vs cognitive load(人当索引)。每加一行 always-loaded 内容前先问它属于哪个预算(`writing-for-agents/SKILL.md:24-27`)。这条直接对上 owner `CLAUDE.md` 只剩约 545 字节预算的现实(本次 `wc -c` 复核 5,599 字节 / 上限 6,144)。
- **规则要么可 grep/可脚本核验,要么别写进 CLAUDE.md**。依据是 Matt 仓库的自举实测:执行得住的恰好是「有唯一入口、有可核查清单、有 grep 得出来的硬规则」的部分(em-dash 在散文里 0 违规),没执行住的是「规则写在一处、落地在另一处不被读的地方」(CHANGELOG 有 104 个 em-dash;ADR 放在 `.agents/adr/` 而非自己规定的 `docs/adr/`)。owner 侧已有同构机制(`doc-filler-guard.sh`、`institution-refcheck.py`),这条是**支持继续走这条路**的外部佐证。

---

## 5. 必须 owner 二选一的分歧点

以下五个是互斥的,不能各取一半。每个给两边代价,不给推荐。

### 分歧 1:状态放外部 issue tracker,还是放仓库目录

- **A(Matt)**:状态住 issue tracker,靠一层 `docs/agents/issue-tracker.md` 间接寻址;技能本体零 per-repo 差异(`setup-matt-pocock-skills/SKILL.md:38-49`、`docs/engineering/setup-matt-pocock-skills.md:5`)。
  - 代价:依赖 `gh`/`glab` CLI 与登录态;GitHub native dependencies 要用数字 database id 走 `gh api` 原始端点(`issue-tracker-github.md:42`);GitLab 的 native blocking 是 Premium/Ultimate 功能(`issue-tracker-gitlab.md:43`);状态在仓库外,离线与本地脚本读不到;owner 的 9 个带 `.trellis` 的项目多数是私有本地项目,未必都有 tracker。
- **B(Trellis / harness-creator)**:状态住仓库内文件,进 git。
  - 代价:状态与代码同仓,分支切换会带着状态跑;需要自己写读写器与原子写(~30 行,`research/02` §6.2);多窗口并行时需要一个「当前任务」指针,而 Trellis 为此付了 857 行(单窗口可以只用一个文件,但要明确接受「同时只开一摊活」)。
- **不能各取一半的原因**:两者都想当「这一摊活干到哪了」的唯一真相源。同时上就有两份 status 且无对账机制(`research/05` 冲突 1)。

### 分歧 2:靠 hook 每轮注入推进,还是靠人打斜杠命令推进

- **A(Matt)**:零常驻,人不打命令什么都不发生。
  - 代价:忘了敲 = 这步没做,而且 Matt 的链条已经在完成回写处断了(`docs/engineering/implement.md:53`);cognitive load 全落 owner 身上。
- **B(Trellis)**:每轮 0.4–0.9 KB breadcrumb。
  - 代价:每轮 context 税;**且 UserPromptSubmit 上已有一位条件租客**——`pm-mode-state.py:43-45` 只在 pm 模式激活时 print,但 pm 模式与项目任务可能同时激活,那时就是两条并列噪音,要么合并成一条注入要么明确分工(`research/06` §5.2 第 1 点)。
- **不能各取一半的原因**:两家对同一个事实(常驻文本每轮都在花钱)给出了相反结论——Trellis 用两次生产事故证明「不注入就会被跳过」,Matt 用 context load 论证「常驻的东西要极度吝啬」。

### 分歧 3:状态转换靠脚本硬校验,还是靠 skill 文字

- **A(纯文字)**:所有闸门都是散文,靠模型自愿遵守。Trellis 除了 `task.py start` 的 jsonl 门与 create/archive 的输入校验之外**实际上就是这个方案**(全树零 `deny`,本次 grep 复核);Matt 完全是这个方案。
  - 代价:实证摆着——Trellis 自己被硬门禁的 jsonl,56% 的任务是空的;而没有门禁的 `design.md`/`implement.md` 只有 14% 的任务有。文字闸门的实际遵守率就是这个量级。
- **B(脚本硬校验)**:状态转换必须过命令,命令里做校验。
  - 代价:每加一道校验就要加一个逃生阀(Trellis 加了 `--allow-empty-context`、`--skip-branch-validation`、`--force`),否则会在真实场景里卡死;而逃生阀一旦存在,门禁就退化成提醒(§3.4 就是这个退化的实证)。且校验逻辑本身要维护。
- **判据线索(不代表推荐)**:owner 侧已经有三个 exit 2 的硬闸在跑(`public-push-guard.sh`、`subagent-model-guard.sh`、`workflow-agent-cap.sh`),说明 owner 对 B 不排斥;但那三个闸守的都是**不可逆动作**(公开推送、模型误用、代理超限),不是流程顺序。

### 分歧 4:项目知识的形态——纯词汇表,还是可注入的编码规范

- **A(Matt)**:`CONTEXT.md` 只是词汇表,**完全不能有实现细节**(`domain-modeling/SKILL.md:64`);实现决策去 ADR,ADR 有三条硬门槛(难逆转 / 无上下文会费解 / 是真实权衡的结果),缺一不写(`:66-72`)。目标是**让 agent 少说废话**。
  - 代价:「让 agent 照规矩写码」这件事它不管;而且 Matt 自己的学习回写链是空的——对应技能 `retro` 至今标 STUB(`skills/in-progress/README.md:18`)。
- **B(Trellis)**:`.trellis/spec/` 分层编码规范 + hook 注入 + 3.3 自动回写。目标是**让 agent 照规矩写码**。
  - 代价:spec 是活的、会被 agent 自动改写,这是一个不同的信任模型;而且 owner 侧 `rules/*.md` 的 paths 前置匹配已经在做同一件事(N4),再加就是两份会漂移的项目描述。
- **不能各取一半的原因**:同一个「项目知识」在两边的粒度和用途完全不同,两套并存 = 两份会漂移的项目描述(`research/05` 冲突 4)。

### 分歧 5:跨会话默认动作——默认 continue(推迟摘要),还是默认 persist(每次落盘)

- **A(Matt)**:五选一有序树,`Continue` 排第一,因为它是唯一保持会话为**一手来源**而非其摘要的动作;`/compact` 垫底,是「默认项不是第一反应」;`/handoff` 只在四种情况用,且写 OS 临时目录不进 workspace(`ask-matt/PHASE-BOUNDARIES.md:19-40`、`handoff/SKILL.md:8`)。
  - 代价:没有断点续跑、没有会话日志、没有步骤级状态(`research/04` §5.3);而且 handoff 自己承认两个缺陷——临时目录会被清,以及「它抓到了 what 没抓到 why」,更危险的是「下一个 agent 把这份文档当合同,不会去复核」,于是一个未经验证的信念被写成事实(`docs/productivity/handoff.md:48,60`)。
- **B(Trellis)**:每会话记 journal + finish-work 归档 + 学习回写,核心原则第 3 条「Persist everything」。
  - 代价:journal 的结构化字段实测基本没被填(`workspace/taosu/journal-5.md` 多处 `(Add details)` / `(Add test results)` 原样留着),退化成「带元数据的长摘要」;每次落盘都是一次有损摘要。
- **owner 现状偏向**:owner 已经是 B 的一个子集(`/handoff` ⇄ `handoff-check.sh` 闭环,且 `handoff.md:44` 规定「工作明显要跨会话时直接写一份,不等应答」)。选 A 意味着要给现有的 handoff 加一层「什么时候**不**该写」的前置判断。

---

## 6. 许可与复用边界

### 6.1 授权事实

| 项目 | 许可 | 出处(本次复核) |
|---|---|---|
| Trellis | **AGPL-3.0**,且元数据自相矛盾:`COPYRIGHT:4-7` 写 "either version 3 …, or (at your option) any later version"(= or-later),两个 package.json 都声明 `"license": "AGPL-3.0-only"`(`packages/cli/package.json:53`、`packages/core/package.json:62`) | ✔ 本次 grep + `sed` 复核 |
| mattpocock/skills | **MIT**,`LICENSE:1-3` = "MIT License / Copyright (c) 2026 Matt Pocock";`package.json:10` = `"license": "MIT"` | ✔ 本次复核 |
| harness-creator(owner 手里那份) | **MIT**,`harness/LICENSE:1-3` = "MIT License / Copyright (c) 2025 WalkingLab";`harness-creator/SKILL.md:11` frontmatter 也写 `license: MIT` | ✔ 本次复核 |

> 以下「这意味着什么」部分是基于许可证文本的解读,不是法律意见。真要商业化,找律师核。

### 6.2 三档复用边界

| 档位 | Trellis(AGPL-3.0) | Matt / harness-creator(MIT) |
|---|---|---|
| **① 看设计自写** | **安全**。AGPL 的义务全挂在 "covered work" 上,而 "modify" 定义是「copy from or adapt … in a fashion requiring copyright permission」(`LICENSE:36,38`)。版权保护表达不保护思想与方法。**边界**:抄机制、抄阶段划分逻辑、抄「status 只有两个真实值」这类结论是安全的;把 `workflow.md` 的段落顺序、小标题、示例句照搬后改几个词就落进 "adapt"。**读者给的实操建议**(未经法律核实,列出供参考):先读,合上文件,隔一段时间用自己的话重写,不要开着原文对照写 | 安全,且更宽松 |
| **② 抄 markdown 模板** | **是 covered work**,义务取决于是否 convey(分发)。`LICENSE:63` 明文:不分发的 covered work「without conditions」,内部自用**无任何义务**;一旦分发(开源、给客户、放公开仓、发 npm),`LICENSE:77-85` 四条全生效,其中 (c)「整个作品作为一个整体必须按本 License 授权」是杀手。aggregate 例外(`LICENSE:88`)救不了——一个把 Trellis 的 skill 改吧改吧当自己 harness 核心的项目,本质上就是 extension。AGPL §13 网络条款(`LICENSE:188`)对纯本地 CLI/skill 不触发,做成 SaaS 才触发 | **可以直接抄,保留许可与版权声明即可**。MIT 只要求在副本或实质部分中保留 license 与 copyright notice。harness-creator 的 `feature-list.schema.json`、`progress.md`、`agents.md`、`init.sh` 都在这一档 |
| **③ 抄脚本** | 与 ② 同法,风险更高三点:(a) 代码有变量名/函数名/注释/结构等强特征,更容易被逐行比对认定;(b) 脚本会被原样 commit 进你的仓库,仓库若公开即构成 convey(`LICENSE:42`:「any kind of propagation that enables other parties to make or receive copies」);(c) 这些脚本互相耦合(`task.py` 依赖 `common/` 下多个模块,合计 11,514 行),不存在「只抄一小段」的选项 | 同 ②。Matt 侧周期链上**没有脚本可抄**(整条链零脚本);harness-creator 的 `templates/init.sh` 与 `scripts/*.mjs` 可抄 |

### 6.3 三条可执行结论

1. 若新 harness 将来可能开源或 MIT/Apache 发布 → **Trellis 一行文件都别复制**,只读设计、合上文件重写;Matt 与 harness-creator 随便抄(保留 notice)。
2. 若确定永远只自用不分发 → `LICENSE:63` 兜底,抄什么都没义务;**但历史 commit 里的 AGPL 代码是定时炸弹**,哪天想开源就要清理历史。
3. 上面两条的分岔点只有一个:**新 harness 将来会不会 convey**。这个问题今天答与将来答,清理成本差一整段 git 历史(依据 §6.2 ③ 的 (b):仓库一旦公开即构成 convey,`LICENSE:42`)——什么时候答、答什么由 owner 定。

---

## 7. 未核实清单

### 7.1 读者标注的未核实项(汇总)

**Trellis 侧**
1. `.trellis/.version`(0.6.14)与 HEAD commit message(0.6.16)不一致的原因,未查发布流程。
2. `test/regression.test.ts` 的实际内容——「回归测试确实覆盖了 breadcrumb 不变量」这一条只读到 `workflow.md:113-118` 与 `workflow-state-contract.md:305-318` 的**引用**,未打开测试文件本身。**这一条重要**:§4.1 的 T4 就建立在它之上。
3. `inject-workflow-state.py`(488 行)只做了行号 grep,未逐行读;解析逻辑以 `workflow-state-contract.md` 的描述为准。
4. `get_context.py --mode phase/packages/record` 的实际输出未运行(只读约束),行为以文档描述为准。
5. 242 个任务中 jsonl 为空的原因(在 gate 之前创建 vs 用了 `--allow-empty-context`)无法从磁盘状态区分。
6. `.trellis/agents/*.md`(channel runtime)与 `.claude/agents/trellis-*.md`(平台 sub-agent)两套 agent 定义是否有同步机制。
7. `.trellis/.template-hashes.json` 只看了大小(30 KB),未读内容。
8. `docs-site/` 与 `marketplace/` 是 git submodule 且未 init,本地为空;官方文档站未联网访问。
9. 版本发布的真实日期与节奏——git 是 shallow clone 只有一个 commit,「约 8-9 个月 148 个版本 / 每两天一发」是用 `.trellis/tasks/archive/` 的月份目录范围反推的**估算**。
10. `add_session.py`(57 KB)与 `task_store.py`(73 KB)未逐行读;`update.ts`(2,924 行)的冲突处理未读;`.github/workflows/publish.yml` 未读。
11. `better-sqlite3` 被 mem 试用后回退的具体原因未展开。
12. 22 个平台 configurator 的逐个差异未读(只统计了文件数)。
13. `trellis update` / `trellis mem` / `trellis channel` 的实现细节未读;`.trellis/spec/**` 41 个 md 的具体内容未读。
14. 父子任务树在 242 个任务中的实际使用率未统计。

**Matt 侧**
15. `research/04` 明确声明:该次调查**没有读 Trellis 的任何文件**,其中「与 Trellis 的 journal/workspace 粒度对比」一节的 Trellis 侧为未核实(已由 `research/01`/`02`/`03` 补上,本文按后三份为准)。
16. `research/05` 的 Trellis 侧引用只基于 `README.md`、`.trellis/workflow.md` 前约 200 行、`config.yaml` 与技能行数统计,**hook 实现代码与 `packages/` 源码未读**——其「冲突 2、3」的结论基于自述而非代码级验证(本文已用 `research/01`/`02` 的代码级证据替换)。
17. `skills/engineering/` 下多个技能正文未读(`diagnosing-bugs`、`codebase-design`、`resolving-merge-conflicts`、`wizard` 等);`skills/misc/*`、`skills/in-progress/` 多数未读;`docs/` 下 18 个页面未读。
18. 「最近 30 条 CHANGELOG」按仓库内条目顺序取,**不等于 git 提交时间顺序**。
19. 这些技能的**实际效果**未核实(作者的效果声称属自述,非实测)。

**owner 侧**
20. `~/.codeisland/codeisland-hook.sh` 的实际行为——它挂在**全部 12 个事件**上(含 UserPromptSubmit、SessionStart、PreCompact),本次未读该脚本。**这一条重要**:任何新 hook 都要与它共存。
21. `~/.pi/agent/extensions/handoff-reminder.ts`(`commands/handoff.md:10` 提到的 Pi 侧消费端)未读。
22. `~/.claude/prompts/` 下 12 份 prompt 库正文未读;`~/.claude/pm/templates/` 四份模板正文未读。
23. `~/.claude/skills/` 下 36 个 skill 除 `skill-smith/SKILL.md` 外均未读。

### 7.2 本次回源复核的结果(含三处读者之间的分歧裁定)

| # | 争议点 | 裁定 | 复核方式 |
|---|---|---|---|
| 1 | `task.json` 字段数:`research/01` 说 25,`research/03` 说 24 | **24**。`research/01` 多算的是可选的 `hooks` 键,它不在默认写入里(生命周期 hook 的说明在 `.trellis/workflow.md:688-702`) | `sed -n '13,40p' packages/core/src/task/schema.ts` + `sed -n '494,520p' .trellis/scripts/common/task_store.py`,两处各 24 个字段且顺序一致 |
| 2 | 平台数:`research/01` 说「21 个平台目录」,`research/03` 说 22 平台 / 25 个 configurator | **22 个平台**(`ai-tools.ts` 的 `AITool` 联合类型 22 个成员);configurators 25 个文件 = 22 + index/shared/workflow;`packages/cli/src/templates/` 下 **19** 个平台目录(另有 common/markdown/shared-hooks/trellis 四个非平台目录 + 2 个 .ts)。`research/01` 的「21 个平台目录」本次未能复现 | `sed -n '8,35p' packages/cli/src/types/ai-tools.ts`、`ls packages/cli/src/configurators \| wc -l`、`ls packages/cli/src/templates/` |
| 3 | jsonl 实测数:`research/02` 说 242 任务 / 107 真填 / 52 空 / 83 无;`research/01` 说 11 个活动任务里 9 个空 | **两者都对,口径不同**。`research/01` 统计的是活动任务子集,`research/02` 是全量。全量数字本次用 Trellis 自己 `curated_entry_count()` 的语义(`common/task_context.py:128-153`)完全复现:242 / 107 / 52 / 83(`check.jsonl` 为 107→106、52→53)。补充一个新事实:仍有 **123** 个 jsonl 文件残留 `_example` 种子行,该行用的键是 `_example` 而非 `file`,故不计入 curated | `find … \| wc -l` + 按 `curated_entry_count` 语义写的一次性只读统计 |
| 4 | SessionStart 注入量:`research/02` 实测 7–8 KB,`research/03` 引 drafts 说 9.5 KB | **不冲突**。9.5 KB 是 v0.5.0-beta 发帖稿的自述数字(`drafts/v0.5.0-beta-forum-post.md:122`),7–8 KB 是 `research/02` 在 0.6.16 上的实测。本文采用实测值 | 读两份报告的口径说明 |
| 5 | hook 是否有阻断能力 | **确认无**。全树只有两处 `permissionDecision`,值都是 `"allow"`;`grep '"deny"'` 零命中 | `grep -rn permissionDecision .claude/hooks/` + `grep -rn '"deny"' .claude/hooks/` |
| 6 | Matt 的 `implement` 无完成步骤 | **确认**,逐字命中 | `cat -n skills/engineering/implement/SKILL.md`(全 15 行)+ `sed -n '50,58p' docs/engineering/implement.md` |
| 7 | `[workflow-state:completed]` 是死代码 | **确认**,代码注释自认 "Currently DEAD in normal flow" | `sed -n '248,258p' .trellis/workflow.md` |
| 8 | owner 的 CLAUDE.md 预算余量 | **确认**:实测 5,599 字节,`doc-filler-guard.sh:23` 的 charter 上限 6,144,余量约 545 字节 | `wc -c ~/.claude/CLAUDE.md` + `sed -n '20,30p' ~/.claude/hooks/doc-filler-guard.sh` |
| 9 | UserPromptSubmit 已有租客 | **确认**:`pm-mode-state.py:9` 的 REMINDER 是一句固定文本,`:45` 每轮 print | `sed -n '1,12p;40,48p' ~/.claude/hooks/pm-mode-state.py` |
| 10 | `/trellis:continue` 路由表 | **确认**,8 行映射逐字复核 | `sed -n '20,36p' .claude/commands/trellis/continue.md` |

### 7.3 本文自身的未核实项

- 本文**未运行** Trellis 或 Matt 的任何命令(只读约束),所有行为结论来自代码与文档文本。
- 本文未读 harness-creator 的 `references/` 其余 6 份与 `scripts/*.mjs`(4 个),§2 的 harness-creator 列基于 `SKILL.md`、`templates/` 五个文件与 `references/lifecycle-bootstrap-pattern.md`。
  **已补读并裁定**:`references/lifecycle-bootstrap-pattern.md`(264 行)按标题看像是「开工/续工」两环的增量,实际**与项目周期无关**——它讲的是 agent **运行时**的可扩展性:hook 信任门(工作区不受信则全部 hook 跳过,`:20`)、后台任务注册表的类型化 ID 与两阶段驱逐(`:46-56`)、四阶段依赖有序 bootstrap 与信任边界拐点(`:57-71`)。**这一档没有可取的周期设计点**;唯一擦边的一条是它的工作单元状态机 `running → completed | failed | killed`(`:126-129`),比 Trellis 的三态多了 `failed`/`killed` 两个终态——若 owner 的状态机要区分「做失败了」与「主动放弃」,这里有个现成的三终态形状可参照。
  由此可确认:**harness-creator 对项目周期的全部贡献就在 `SKILL.md:22-31` 的五子系统表 + `templates/` 五个文件里**,其余 6 份 reference 按标题(memory-persistence / skill-runtime / tool-registry / context-engineering / multi-agent / gotchas)判断属于 owner 已有等价物覆盖的范围(见 §4.3 N6、N10),未读。
- §6 的许可解读不是法律意见。

---

## 核验记录

对抗核验(证伪视角)于 2026-09-10 对本文全部带路径断言抽查回源,实际回源核过 40+ 处引用、并用只读脚本独立重算了 §3.4 的全部统计。核验基准与正文一致:Trellis = `scratchpad/trellis`(HEAD `88f4834`,`git log --oneline -1` 复核)、Matt = `scratchpad/mattskills`(HEAD `3cca18b`)、harness-creator = `/Users/sangba/Downloads/02-代码脚本/工具脚本/harness/harness-creator`、owner = `~/.claude/`。

### A. 已修正的 blocking(16 条)

| # | 位置 | 原文 | 改后 | 依据(本次回源) |
|---|---|---|---|---|
| B1 | §2 续工格 | `continue.md:26-33` | `continue.md:27-34` | `grep -n "status=" .claude/commands/trellis/continue.md`:8 行路由映射实际落在 27–34,26 行是空行 |
| B2 | §4.1 T2 | 同上 | 同上 | 同上 |
| B3 | §4 判据② | 「依据 `CLAUDE.md:8` 不重复造轮子」 | `CLAUDE.md:7` | `cat -n ~/.claude/CLAUDE.md`:`:7` 才是「不重复造轮子」,`:8` 是「功能设计按 rules/design-doc.md 写」 |
| B4 | §6.2 档位② | 「`LICENSE:61` 明文:不分发的 covered work『without conditions』」 | `LICENSE:63` | `grep -n "without conditions" trellis/LICENSE` → 63;`:61` 是 §2 首段「unlimited permission to run」 |
| B5 | §6.3 结论 2 | 「`LICENSE:61` 兜底」 | `LICENSE:63` | 同上 |
| B6 | §4.2 C4 | 「`add_session.py:26-32`」 | `add_session.py:23-28` | `grep -n "Commit evidence:" .trellis/scripts/add_session.py` → 23;该段止于 28,30 行起是「Retry convergence」另一主题 |
| B7 | §2 需求澄清格 | 「`grilling/SKILL.md:8,26,27`」 | `:8,26,28` | `grep -n "The session is done when"` → 28;27 是空行 |
| B8 | §4.3 N7 | 「`trellis-session-insight/SKILL.md:13`」 | `:14` | `sed -n '10,16p'`:OpenCode 不可索引的自述在 14,13 是空行 |
| B9 | §7.2 裁定 4 | 「`drafts/v0.5.0-beta-forum-post.md:118`」 | `:122` | `sed -n '115,125p'`:9.5 KB 那条在 122,118 是小节标题 |
| B10 | §3.5 | 「命令 8→3,138 条 safe-file-delete」 | 「清理 126 条 safe-file-delete + 12 条额外操作」并补出处 `:107` | 发帖稿第 107 行原文是「大规模清理(126 条 safe-file-delete + 12 额外)」;138 是两项相加,不是 safe-file-delete 的条数 |
| B11 | §3.2 会话身份格 | 「`platform-session-identity.md:12-16`」 | `:12-17` | 「9 of 14 declared env var names are invented」跨 16–17 两行,原范围截断了论据 |
| B12 | §2 开工格 | 「无任务时 breadcrumb 每轮要求先分诊(`workflow.md:152-156`)」 | 拆成两处:Request Triage 规则在 `:152-156`(Phase 1 walkthrough,不是 breadcrumb),同一条写进 `[workflow-state:no_task]` 块的是 `:176-180` | `awk 'NR>=174&&NR<=181'`:breadcrumb 块起止为 176/180;152-156 是 walkthrough 正文。原断言把两个不同载体混为一谈,而「载体是不是 per-turn 通道」正是 §4.1 T3 的立论前提 |
| B13 | §2 续工格 | 「`pm-mode-state.py:45` 每轮 `print(REMINDER)`」 | 「在 pm 模式激活的会话里每轮 print(`:43-45` 的 `if marker.exists()` 守卫;未激活时不输出)」 | `cat -n ~/.claude/hooks/pm-mode-state.py`:43 行 `if marker.exists():` 守卫住 45 行的 print。无条件「每轮 print」不成立,`research/06` §5.1 原表也写的是「激活中每轮 print」 |
| B14 | §5 分歧 2 | 「UserPromptSubmit 上已有一位租客——`pm-mode-state.py:45` 在 print」 | 「已有一位**条件**租客……只在 pm 模式激活时 print」 | 同 B13。租客是条件性的,直接影响「两条并列噪音」这个代价的发生频率 |
| B15 | §2 续工格 | 「压缩后不再提醒(owner 自己在 `commands/pm.md:10` 记了这个坑)」 | 「提醒本身在压缩后照常发,掉出上下文的是它指向的 `commands/pm.md`」 | `sed -n '8,12p' ~/.claude/commands/pm.md`:原文是「压缩后看到 [pm-mode] 提醒而本文件已不在上下文时,先重读本文件再干活」——出处说的恰是提醒**仍在发**。原断言与出处相反 |
| B16 | §2 验证格 + §4.1 T11 | 「owner 的验证命令散在 `rules/python.md:9`」 | 改为「语言级/领域级分散约定:`rules/python.md:9,11`(uv 与 ruff)、`rules/reverse-api.md:26-27`(抓真包 + live 测试)」 | `cat -n ~/.claude/rules/python.md`:`:9` 是依赖与运行入口约定(`uv add`/`uv run`),不是验收命令;真正带验证语义的是 `:11` 的 ruff 规则集与 `rules/reverse-api.md:26` 的「## 验证(真包优先)」小节 |

### B. 已删除/改写的越界表述(3 条)

| # | 位置 | 原文 | 改后 | 依据 |
|---|---|---|---|---|
| X1 | §6.3 结论 3 | 「现在就在新 harness 仓库里记一笔『本项目未复制 Trellis 任何文件,仅参考公开设计』,比事后自证清白便宜」 | 改为陈述分岔点(会不会 convey)与成本差,把「什么时候答、答什么」留给 owner | 本文开篇自设约束「不写实现、不替 owner 拍板」(`07-synthesis.md:5`)。原文是一条带时间要求的实施指令 |
| X2 | §3.5 | 「参照物**应锁定** v0.5.0 减重后的形态,而不是当前的 0.6.16」 | 改为并列给出两版参照物及其体量差,注明选哪版由 owner 定、本文数字默认取 0.6.16 实测 | 同上。「应锁定」是替 owner 做选材决策 |
| X3 | §6.2 档位① | 「**实操建议**(读者给的,**值得照做**)」 | 「**读者给的实操建议**(未经法律核实,列出供参考)」 | 同上,且 §6.1 已声明「不是法律意见」,「值得照做」与该声明自相矛盾 |

### C. 回源后确认无误的关键断言(抽查,未改动)

- §3.4 全部统计**独立重算完全复现**:242 个任务目录、`prd.md` 234(97%)、`design.md` 35(14%)、`implement.md` 35(14%)、`implement.jsonl` curated 107 / 空 52 / 缺 83、`check.jsonl` 106/53/83、残留 `_example` 的 jsonl 123 个。重算用 `curated_entry_count()` 同语义(`common/task_context.py:128-153`,`def` 在 128 行,函数体止于 153,行号准确)。
- 7 个 status 写者表 `workflow-state-contract.md:251-270` 准确(`## Status writer table` 在 251,「No other writer exists」在 267)。
- `.trellis/workflow.md` 709 行、INVARIANT 段 `:113-118`、`[workflow-state:completed]` 死态 `:250-257`、Planning Artifacts `:158-164`、父子非依赖系统 `:170`、子代理自我豁免 `:228`、全量 check `:557`、spec 回写必答 `:587`、spec-sync preamble `:591`、提交顺序 `:593`、七步 SOP+Rules `:595-639`、不认识的脏文件 `:611`、fork 不变量 `:654`、双门 `:156/:293/:654`——逐条命中。
- hook 无阻断能力:`grep -rn permissionDecision .claude/hooks/` 仅 `inject-subagent-context.py:1188,1197` 两处且值均为 `"allow"`,`grep -rn '"deny"'` 零命中。
- `task.py:194-215` 的 jsonl 门与逃生阀 `--allow-empty-context`、`inject-subagent-context.py:483-506` 的空 manifest 降级路径、`:534-590` 的 implement 注入顺序、`config.yaml:151-154` 的三档字节预算(注:该段是被注释掉的默认值文档,数值 32768/65536/131072 与正文一致)。
- 平台数 22(`ai-tools.ts:10-32` 逐个数)、configurators 25 个 .ts(= 22 平台 + index/shared/workflow)、`templates/` 下 19 个平台目录(另有 common/markdown/shared-hooks/trellis 四个非平台目录 + 2 个 .ts)、migration manifests 148 份、`0.7.0-beta.0.json` 确写「resolve task, developer, team, and global selections through one runtime chain」。
- 行数:`core/src/task/` 561、core 非测试 10,473、cli 非测试 119 文件 / 26,841 行、`core/channel` 4,544、`core/mem` 5,357、`.claude/hooks` 三个 py 合计 2,649(488+949+1212)、`add_session.py` 1,545、`active_task.py` 857、`developer.py` 192、journal 10,437 行、`.trellis/spec/` 41 个 md。
- `task.json` 24 字段且无 `evidence`(`schema.ts:13-38` 逐个数,注释自述「The 24-field shape ... mirror that writer exactly」)。
- 全局 index 陈旧的反证:`workspace/index.md:28-31` 只有 kleinhe / 2026-01-26 / 12 次;磁盘上 7 个开发者目录;`workspace/taosu/index.md:11` 记 175 次、最后活跃 2026-08-01。
- Matt 侧:`implement/SKILL.md` 全 15 行且第 4 行 `disable-model-invocation: true`、`docs/engineering/implement.md:53` 的「no completion step + frontier 因此永不解锁」逐字命中、`to-tickets/SKILL.md:29-36/38/40/65`、`grill-with-docs/SKILL.md:7`、`writing-for-agents/SKILL.md:24-27/81`、`PHASE-BOUNDARIES.md:19-40`、`handoff/SKILL.md:8`、`docs/productivity/handoff.md:48/60`、`code-review.md:68/72/76`、`domain-modeling/SKILL.md:64/66-72`、`triage/SKILL.md:31-41/74/82`、`in-progress/README.md:18`(retro STUB)、`CLAUDE.md:21`(路由器说谎)、`issue-tracker-github.md:42`、`issue-tracker-gitlab.md:43`——逐条命中。
- harness-creator:`SKILL.md:22-31` 五子系统表、`feature-list.schema.json:12-42`(required 四项)/`:25-31` dependencies/`:34` blocked/`:37-40` evidence、`templates/agents.md:5-16/20-23/35-40/44-50/52-60/66`、`init.sh` 78 行四分支、`session-handoff.md:31-36`、`lifecycle-bootstrap-pattern.md` 264 行 `:20/:46-56/:126-129`——逐条命中。
- owner 侧:`CLAUDE.md` 5,599 字节 vs `doc-filler-guard.sh:23` 的 charter 6144、`handoff-check.sh:66` 的 jq additionalContext、`commands/handoff.md:10/24-35/44`、`commands/kickoff.md:10-13`、`commands/pm.md:17-22/24-27`、`rules/design-doc.md:13-18`、`os/WORKERS.md:23/31`、`settings.json#hooks.Stop` 的 ruff/mypy/biome 链、codeisland 挂满 12 个事件、`dashboard/CLAUDE.md:14` 的 kickoff 反证——逐条命中。
- 许可事实:Trellis `COPYRIGHT:4-7` or-later vs `packages/cli/package.json:53` / `packages/core/package.json:62` 的 `AGPL-3.0-only`(矛盾属实);`LICENSE:36/38/42/77-85/88/188` 内容与引用一致;Matt `LICENSE:1-3` + `package.json:10`;harness-creator `LICENSE:1-3` + `SKILL.md:11`。

### D. 未修的 important(5 条,按处理约定只列不改)

1. **§2「读这张表的四条结论」第 1 条与同页表格自相矛盾。** 结论说「owner 的空缺集中在两处……其余五环 owner 已有等价物或更强」,而它上面那张表里带「**空缺**」字样的有 5 环:开工(无 Startup Workflow)、需求澄清(零 hook、无落盘、无完成判据)、拆任务、验证(无验收命令登记处)、收尾(无未写交接就 Stop 的兜底)、续工——只有「实现」一环写着「**空缺**:无」。`research/06` §6.1 也明确列了**三个**空缺而非两个。建议把「两处」改为「两处**严重**空缺 + 三处轻空缺」,或删掉这条结论。
2. **分歧 2 与分歧 3 不是互斥项,而 §5 开头声明「以下五个是互斥的,不能各取一半」。** 分歧 2:Trellis 自己同时有 breadcrumb hook 和 `/trellis:continue` 人工命令,两者并存运行;真正的取舍是「要不要付每轮 0.4–0.9 KB 常驻税」,是一个连续量而非二选一。分歧 3:本文自己写着「Trellis 除了 `task.py start` 的 jsonl 门与 create/archive 的输入校验之外实际上就是纯文字方案」——这句就是「脚本硬校验与文字闸门混用」的实证,自证不互斥。这两条应改写为「代价权衡」而非「二选一」,否则会误导 owner 以为必须放弃一边。
3. **`research/06` §3「层级」整节未进综合,而它是对项目级 harness 最有约束力的事实。** 该节实测:owner 有 **9 个项目带 `.trellis`**;抽查三个项目的 `.claude/` 逐字同构,项目级 `settings.json` 已把 `SessionStart`、`UserPromptSubmit`、`PreToolUse(Task|Agent)` 三个位子全占;项目根 CLAUDE.md 里还有 `<!-- TRELLIS:START -->` 托管块会被 `trellis update` 覆盖(`dashboard/CLAUDE.md:32-52`)。也就是说新 harness 不是「在空地上盖」,是「同位竞争」——这既是一个成本项,也可能本身就是一个该交给 owner 的分歧点(替换 Trellis / 与之共存 / 只在新项目用)。本文全篇未提。
4. **`research/06` §5.2 的另外两个共存冲突点未进综合。** (a) `PreToolUse` 的 `Agent` matcher 已被 `subagent-model-guard.sh` 占用且其 exit 2 语义是阻断——同一事件任一 hook exit 2 即阻断整个调用,新 hook 必须保证自身永不 exit 2;(b) `Stop` 位第一块内联 bash(ruff/mypy/biome)**没有设 timeout**,若新 harness 想在 Stop 做「完工前强制写状态」,会叠加在它之后。这两条直接约束 T3(breadcrumb 注入)与「收尾兜底」的可实现形态,遗漏会让下一步设计踩坑。
5. **`research/05` 冲突 6(收尾学习回写的信任模型)未进综合,且与 §4.1 T9 存在未挑明的张力。** Trellis 的 3.3 是 agent 自动改写 `.trellis/spec/`;Matt 的 ADR 有三条硬门槛且由人判定(`domain-modeling/SKILL.md:66-72`);owner 的 `CLAUDE.md:39` 是 append-only 到 INBOX.md、不改写、归档另交 vault 会话。本文在 §4.2 分歧 4 里点了「spec 会被 agent 自动改写,这是一个不同的信任模型」,却在 §4.1 把 T9 直接放进「取」,没说清取的是「必须问一次」还是「问完自动写」——这两者的信任模型不同。

### E. 未修的 nit(4 条)

1. §3.2 「全局 index 无自动写者,已陈旧 7 个月」:index 记的最后活跃是 2026-01-26,距**磁盘上最新活动**(taosu 2026-08-01)约 6 个月,距核验当日约 7.5 个月。两种口径都成立,但文中未说明按哪种算。
2. `code-review/SKILL.md:44-56` 里 44 是空行,12 条味道实际在 `:45-56`。范围包含结论,不影响可核查性。
3. `triage/SKILL.md:110` 是小节标题「## Resuming a previous session」,断言内容(读既有 triage notes)在 `:112`。
4. §4.3 N4–N14 的「依据」多为「`research/06` §6.2」或「同上」的二手链,未回落到一手路径;本次已代为回源确认其一手出处均存在(见上 C 段 owner 侧一行),但文中读者若要自查需多跳一层。

### F. 本次核验自身的边界

- 只读:未运行 Trellis / Matt 的任何命令,未修改被读仓库的任何文件;§3.4 的重算脚本只做 `read_text` 与计数,写入仅限本文件。
- 未回源的引用:`research/03` §7.1、`research/01` C4/H2、`research/05` §5.3 等纯读者报告内部编号的引用,只核到读者报告存在该编号,未再穿透到一手文件。
- §7.1 的 23 条未核实项本次未逐条推进,其中 owner 侧第 20 条(`~/.codeisland/codeisland-hook.sh` 挂满 12 个事件)已复核事件数属实(`settings.json` 逐个事件确认),脚本内容仍未读。
