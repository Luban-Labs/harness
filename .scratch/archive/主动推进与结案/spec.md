Status: done
会话: cb260c48-3465-481c-9e57-cea155732e77

# 主动推进与结案:球在谁手里、结案触发、看板

## 目标

装了 harness 的项目里,验收做完就自己收件归档,自己的事做完一步接着做下一步,等外部时说清怎么回看,owner 开新会话或问一句就能看到每个 Task 到哪了、哪几件在等他(owner 10-22「harness 结案不积极,主动性不高,很多进度都得靠我催」「结案不会主动归档,进度需要我一直跟」;方案回「改」,并定「先改原项目,改完再给现在用的项目更新」「Codex 部分让 Codex 自己改」)。

出处(ticket-seller-tools 10-02–10-22 会话记录与 30 个 Task 的 git 史):owner 催进度、催收尾、叫继续 96 次;验收达成到改 done 拖 45–77 小时;10-20 以来 7 次归档有 6 次在 owner 催之后;进展行 next 47% 指向 owner 却没有汇总;Stop 兜底自 10-11 起一次没拦过(Scope 写成 `.scratch/<名>` 被排除,多 Task 匹配不上)。

## 验收

- [x] [我] `python3 -m unittest discover -s tests -v` 全过,新用例覆盖下文每条判定的拦与不拦
- [x] [我] 用 ticket-seller-tools 当前 `.scratch` 的副本跑 `session_start.py --board`:每个 in-progress Task 一行,next 带「你:」的进「等你的事」
- [x] [我] Stop 回放(副本上):本会话认领的 Task [我] 项全勾 → 结案提醒;next「我:」且无后台任务 → 接着做;有后台任务 → 放行;`stop_hook_active` 为真 → 无输出;未认领的会话 → 只走旧兜底
- [x] [我] Codex 实测:同一提醒在 Codex 里能让会话接着跑(Codex 自己改、自己验)
- [x] [我] 合入 harness main 后同步到 ticket-seller-tools,三个 harness 文件与模板 `cmp` 一致,现役 Task 完成迁移或已通知认领它的会话
- [ ] [你] 下次开新会话看一眼开场看板与「等你的事」是否看得懂

## 范围与不做项

做:

- **spec 格式**(docs/rules/harness.md 与 interview-me 的 spec 模板):
  - 头部:第 1 行 `Status:`,其后到第一个空行或 `#` 行之间都是头部字段 `键: 值`(半角或全角冒号)。已有 `Scope:`、`Tickets:`,新增 `会话: <会话 ID>`;`Scope` 不再限定在第 2 行。
  - `## 验收` 段(标题以「## 验收」开头即可):每项 `- [x] [我] …` 或 `- [ ] [你] …`,勾上写 `[x]`(大小写均可)。`[我]` = 执行者当场能演示并自验;`[你]` = 只有 owner 能做或要 owner 看的。
  - 进展行改为 `- MM-DD HH:MM done: … | next: <球>: … | 别再试: …`,球为 `我`、`等`、`你` 之一;`等:` 要带 `回看: <几点、由谁、怎么看>`,在跑后台命令、Monitor、定时或等 codex-watch 唤醒时写明是哪个。
- **规则**(docs/rules/harness.md):
  - 废除「同一时刻只保留一个 in-progress」与 Scope 并行例外:可以同时开多个;开工或接手时把本会话 ID 写进 `会话:`(SessionStart 会注入;Claude 也可读 `$CLAUDE_CODE_SESSION_ID`),一个 Task 只认最后写入的会话。`Scope` 只剩代码改动兜底的走查范围。
  - spec 只改主工作树那份;worktree 里的 `.scratch` 副本不改。
  - 结案触发:`[我]` 项全部勾上即做收件两问、改 done、归档,不等 `[你]` 项;没勾的 `[你]` 项留在归档的 spec 里,看板继续列给 owner,owner 说做了或不用了就勾上或删掉。
  - 验收项要当场能演示:依赖自然发生的事(下一次真实上架、下一轮调价),先自己造一个(预览批次、测试数据、手动触发一轮);造不出来的写成 `[你]` 项并说明届时看什么。有 ticket 的 Task 把「全部 ticket 关闭」写成一条 `[我]` 项。开工或接手时验收段没有勾选框,先改写。
  - `你:` 只写 owner 本人才能做的(付款、粘贴或授予凭据、页面上的批准、业务取舍);能自己查、自己验、自己做的写 `我:`;owner 在 spec 或原话里批过的不再问。同一 Task 待 owner 定的几件合成一条编号请示,先做完不依赖它的部分。
  - 停下等外部时,回复里写清在等什么、预计几点好、到时由谁回来看。
  - 看板有「等你的事」时,本会话第一次回复 owner 时在末尾用一句话提条数与最久的一条;owner 问进度时转述整张看板(`python3 .claude/hooks/session_start.py --board`)。
- **SessionStart**(session_start.py):开场与压缩后注入看板;同一脚本带 `--board` 时打印同一张看板(无 JSON、无本会话两行)给 owner 问进度用。见下方「看板」。
- **Stop**(stop_guard.py):对本会话认领的 Task 加结案、接着做、补回看三类提醒;未认领时只走旧兜底。见下方「Stop 判定」。
- **主工作树**:两个 hook 读 Task 状态、头部、验收、进展时,cwd 在 git 链接工作树里且主工作树有 `.scratch/` 目录(非符号链接)→ 读主工作树那份;判法是 cwd 向上第一个 `.git` 若是文件且 `gitdir:` 指向 `<主>/.git/worktrees/<名>`,主 = 该路径上三级。旧兜底的代码走查根不变(cwd 向上最近含 `.scratch` 的目录)。
- **Codex**:输出格式、输入差异、实测由 Codex 自己定。已知:Codex 0.163 的 Stop 输出 schema 只有 continue/decision/reason/stopReason/suppressOutput/systemMessage,没有 hookSpecificOutput;Stop 输入有 session_id、turn_id、stop_hook_active、last_assistant_message,没有 background_tasks、session_crons;SessionStart 输入有 session_id、source。
- **文档**:docs/decisions.md 追加一条;同步 ticket-seller-tools。

不做:

- 独立判官钩子(prompt 型 Stop 判「把能自己做的推给 owner」):会把代理推向被权限分类器拦的动作,判官与续跑上限配合可能停不下来;先看本版效果。
- spec 里记「授权」行:文件里的授权声明不能扩权(WORKERS.md),反而是注入口。
- hook 写任何文件、自动归档、自动删 worktree:hook 只读,动作交给代理;worktree 清理由现有全局规则管。
- 用 git 历史或 mtime 算「搁了多久」:合并与检出会改 mtime;用进展行时间,解析不了才退回 spec mtime。
- dashboard 同步:它这次不在「现在用的项目」里,另行同步。
- 每轮注入(UserPromptSubmit):先看开场看板加 Stop 提醒够不够。

## 看板

注入顺序,每段没有内容就整段不出;in-progress、ready-for-agent、「等你的事」三者都没有时零字节(含本会话两行):

```
[harness] 本会话 ID: <session_id>;开工或接手 Task 时写进它 spec 头部「会话:」行
[harness] 本会话认领: <名>(.scratch/<名>/spec.md) 最近进展: <进展末行全文>
[harness] 等你的事 <N> 条:
- <名>: <next 去掉「你:」的正文>(<多久>前)
- <名>(已归档): <未勾 [你] 项正文>
[harness] 进行中 Task <N> 个:
- <名> · 会话 <ID 前 8 位>|无人认领 · <多久>前|无进展 · <球>: <next 正文前 80 字>
[harness] 待开工 Task: <名>, …;需求相关时先读 .scratch/<名>/spec.md
```

- 「本会话认领」:payload 的 session_id 与某 in-progress Task 的 `会话:` 匹配时出(压缩、续接后接得上);可多行。
- 「等你的事」:in-progress Task 进展末行 next 球为「你」的那条,加 `.scratch/archive/*/spec.md` 验收段里未勾的 `[你]` 项;最多 8 条,超出写「等 N 条」;归档扫描最多 1000 个 spec。
- 「进行中」:每个 in-progress Task 一行,最多 10 行,超出写「等 N 个」;next 没有球前缀时球写「?」;`Status: done` 但仍在 `.scratch/` 的也列,球写「待归档」;in-progress 且 `[我]` 项全勾的球写「待结案」(认领会话丢了也看得出该收件)。
- 「多久」:进展末行 `MM-DD HH:MM` 按本机时区解析,年份取不晚于现在 + 1 天的最近一年;解析不了用 spec mtime;不到 1 小时写分钟,不到 48 小时写小时,其余写天。
- 会话匹配:`会话:` 值与 session_id 相等,或值不短于 8 位且是 session_id 的前缀。
- 单个 spec 读不了、头部坏、Scope 非法:只跳过该 Task,不让整张看板消失;`.scratch` 是符号链接仍整体放行。

## Stop 判定

`stop_hook_active` 为真 → 无输出(每个用户回合最多提醒一次,不会循环)。

本会话认领的 Task(`会话:` 匹配 session_id,状态 in-progress 或 done 未归档)逐个判,命中第一条即止,各 Task 的提醒合成一段输出:

1. `Status: done` 仍在 `.scratch/` → 「[harness] Task <名> 已是 done 但还在 .scratch/:在主工作树执行 mkdir -p .scratch/archive && mv .scratch/<名> .scratch/archive/<名>。」
2. 验收段没有带 `[我]`/`[你]` 的勾选框 → 「[harness] Task <名> 的「## 验收」还没有带执行者的勾选框:改写成 - [x] [我] … / - [ ] [你] …;[我] 是你当场能演示并自验的,[你] 是只有 owner 能做或要 owner 看的。」
3. 至少一项 `[我]` 且全部勾上 → 「[harness] Task <名> 的 [我] 验收项已全部勾上:现在做收件两问,改 Status: done 并归档;没勾的 [你] 项留在 spec 里,看板会继续列给 owner。」
4. 进展末行 next 球为「我」,且 `background_tasks`、`session_crons` 都为空或缺失 → 「[harness] Task <名> 的 next 是你自己的事(<next 正文前 60 字>):接着做,做完勾上对应的验收项;[我] 项全勾就直接收件两问、改 done、归档,不要把核验或关闭写成「你:」。做不了就先追加一行进展,把 next 改成「你: <owner 要做的具体动作>」或「等: <在等什么>(回看: <几点、由谁、怎么看>)」再停;owner 让停或本轮在问别的事时写「等: owner 下一步安排(回看: owner 下次开口)」。」
5. 球为「等」、正文没有「回看:」(或全角冒号),且两个数组都为空或缺失 → 「[harness] Task <名> 在等外部但没写怎么回看:挂后台命令或 Monitor 等结果,或在 next 里补「回看: <几点、由谁、怎么看>」再停。」
6. 没有进展行,或末行 next 没有球前缀 → 「[harness] Task <名> 的进展末行没写球在谁手里:追加一行进展,next 以「我:」「等:」「你:」开头。」

球为「你」→ 不提醒。

旧兜底(本轮改了代码却没补进展)照旧:认领恰好一个 Task 时对它判,认领多个时不判,没认领时按原规则选 Task(唯一 in-progress 或唯一 Scope 匹配)。

输出:Claude 用 `hookSpecificOutput.additionalContext`(hookEventName Stop,记录里显示为 hook 反馈而不是 hook 错误,同样受 stop_hook_active 与连续 8 次上限保护);Codex 由 Codex 定(其 Stop 输出没有 hookSpecificOutput)。

## 最小路径

1. 开 worktree `harness-proactive`(分支 `feat/proactive`)。
2. Codex 改两个 hook 与 tests(含 Codex 侧兼容与实测);主会话同时改 docs/rules/harness.md、spec 模板、docs/decisions.md。
3. 主会话亲验:单测全过,验收 2、3 用 ticket-seller-tools 副本回放。
4. 累计 diff 终审一次(代码派 codex 只读对抗审,规则文档派 adversarial-reviewer),修 blocking。
5. 合入 harness main,删 worktree 与分支;复制三个 hook、docs/rules/harness.md、interview-me 的 spec 模板与 to-tickets 到 ticket-seller-tools 提交推送(`.agents/` 不在 CI 忽略清单里,会跑一次 CI);迁移或通知现役 Task。

## 进展
- 10-22 18:10 done: spec 定稿；worktree harness-proactive 里改完 docs/rules/harness.md、spec 模板、to-tickets、decisions；用户级 output-style 改为同一 Task 合并编号请示；ticket-seller-tools 记忆加上线点名句；两个 hook 派 Astra task-mvj6jtav-wnij6q；回放环境 scratchpad/harness/replay 备好 | next: 等: Astra 交回(回看: 后台等待任务 b7z4o0rcm 结束即唤醒本会话) | 别再试: -
- 10-22 18:20 done: Astra 首轮交回(102 测试,Codex 真实续跑被其沙箱挡);主会话亲验:macOS 默认 TMPDIR 下 2 个测试因 /var 软链失败,发现未认领的工人在 worktree 里会被提醒改主工作树 spec,两条打成续包 D1 派回同一线程;ticket-seller-tools 副本回放看板与 9 种 Stop 输入全符合;沙箱外实测 codex exec(gpt-6-sol)与 claude -p(sonnet):开场注入 ID、认领、Stop 提醒后都接着写完 hello.txt;Claude 那次做完把「核验并关闭」写成 你:,接着做提醒要补「[我] 全勾就直接收件归档」 | next: 等: D1 交回(回看: 后台任务 bkarifgj8 结束即唤醒) | 别再试: 在 codex 沙箱里跑 codex exec(sandbox_apply 被拒)
- 10-22 18:45 done: D1 亲验 104 过(默认 TMPDIR)、哈希对上;接着做提醒补「[我] 全勾就直接收件归档」;stop_guard 超 500 行预算,记录取证整块拆到 stop_evidence.py(与 main 旧版逐字一致),init/migrate_trellis 改装三个 hook,harness.md 与决策同步;终审两路已起:codex 只读审 task-mvj7r7kl-aajx70、adversarial-reviewer 审规则 | next: 等: 两路终审结果(回看: 完成通知唤醒本会话) | 别再试: -
- 10-22 19:05 done: 终审两路回:codex 代码 3 blocking(伪造 .git 读外部 Task、归档命令未加引号、主工作树坏 spec 让未认领兜底失效)派 sol 修 task-mvj82jc6-8lgb8e;规则审 1 blocking(spec 里的「已批准」会被当授权)与 10 important,改了 harness.md、to-tickets、decisions、output-style、上线点名句记忆;实测 Claude/Codex 每回合只提醒一次、真实项目两个 hook 各约 0.07 秒 | next: 等: sol 修复交回(回看: 后台任务 bi9rbijd0 结束即唤醒),之后续派看板「待结案」与 owner 出口措辞 | 别再试: -
- 10-22 19:40 done: D2(看板「待结案」、owner 出口改「等:」)亲验 109 过;harness main 合入 f4403b5、1a50b17 并删 worktree;同步 ticket-seller-tools dec77ff(三个 hook、harness.md、spec 模板、to-tickets,cmp 一致),合入前两端全量:后端 3071 passed/3 skipped、前端 352/352,已推送;通知 ticket-seller-tools-41/-74/-6c 认领迁移各自 Task;收件两问:路由表文档 docs/rules/harness.md 已更新、tests 已更新、init --help 已更新为三个 hook、migrate_trellis --help 不受影响;无需沉淀新规则 | next: 你: 下次开新会话看一眼开场看板与「等你的事」是否看得懂 | 别再试: -
