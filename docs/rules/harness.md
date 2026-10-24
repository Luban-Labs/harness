# Task 规则

周期链:对需求用 interview-me skill(两平台都按其描述触发;采访式,一次一问)→ 按「何时建 Task」判,命中才建 Task(`.scratch/<功能名>/spec.md`,首行 `Status: ready-for-agent`)→ 开工(改 `in-progress`,写 `会话:` 认领)→ 每轮停下前补一行进展,写清球在谁手里 → `[我]` 验收项全勾 → 收件三问 → 改 `done` 并归档。SessionStart hook 在开场与压缩后注入看板:本会话 ID 与建 Task 命令、本会话认领的 Task、「等你的事」、每个进行中 Task 一行、待开工 Task 名;没有 in-progress(含已 done 未归档)、ready-for-agent 与「等你的事」时什么都不注入。Stop hook 对本会话认领的 Task 提醒结案、接着做与补回看,对它们和本会话写过的 spec 查格式,每个用户回合最多提醒一次。

## spec 格式

- 唯一格式是 `.agents/skills/interview-me/templates/spec.md`,各节写法、必填与可省都以它为准。不手写:在项目根运行 `python3 .claude/hooks/session_start.py --new-task <功能名> --kind 功能|记录` 生成骨架再填;必填节没内容写「无」,不加骨架以外的 `##` 节。
- Task 目录为 `.scratch/<功能名>/`,只放 `spec.md`;任务包、脚本、调查记录放会话临时目录。`spec.md` 首行为 `Status: ready-for-agent`、`Status: in-progress` 或 `Status: done`;其后到第一个空行或 `#` 行为头部,每行 `键: 值`:`类型:`、`建单:`、`Scope:`、`Tickets:`、`会话:`,顺序不限。`Scope:` 只写代码目录。
- 正文写现在的状态:owner 定了什么、范围变了,当场改对应的节,过时的内容直接删,进展里只记一句「已改正文」。只写本 Task 目标以内的事,别的事写进它自己的 Task 或提交信息。
- `## 验收` 段每项一个勾选框并标执行者:`- [ ] [我] …` 是执行者当场能演示并自验的,`- [ ] [你] …` 是只有 owner 能做或要 owner 看的;做完改 `[x]`。
- 验收项要当场能演示。依赖自然发生的事(下一次真实上架、下一轮调价)时先自己造一个(预览批次、测试数据、手动触发一轮);造不出来的写成 `[你]` 项,写明届时看什么。有 ticket 的 Task 把「全部 ticket 关闭」写成一条 `[我]` 项。
- 进展段只追加以下格式的行:`- MM-DD HH:MM done: … | next: <球>: … | 别再试: …`,时间用本机时间,一行不超过 200 字。提交哈希、工人编号、测试数、审查明细、收件逐项写进提交信息与交付回复;`| 别再试: …` 只在有新的失败做法时写。超过 30 行时把已收尾的旧行压成一行摘要,仍有效的「别再试」保留在摘要里。球只有三种:
  - `我:` 执行者自己接着做的事。
  - `等: <在等什么>(回看: <几点、由谁、怎么看>)`:在等 CI、工人、平台或某个时间。挂了后台命令、Monitor、定时或等 codex-watch 唤醒的,写明是哪个;等几天的外部事件写「回看: 每次开会话看板」。
  - `你:` owner 本人才能做的动作,写到 owner 照着就能做。
  - owner 让停、或本轮在问别的事时写 `等: owner 下一步安排(回看: owner 下次开口)`,不占用 `你:`。

## 何时建 Task

- 只看三条,命中任一才建,并在头部写 `建单: <命中哪条>`:
  1. owner 说建 Task、写 spec,或要把一件待办(bug、需求、小改动)记下来以后做。口语「给你个任务」「做吧」不算;要写进记忆或 `docs/rules/` 的不算。
  2. 发现一个线上或 CI 的 bug,本会话不修。对抗审的 important、nit 照常写进交付说明,不算。
  3. 停下时还有本会话等不到的事:等平台或自然事件,等 owner 做完一个动作(给凭据、页面批准)才能接着做,或要交给别的会话接手。本会话里等得到的 CI、上线、工人回包不算;只等 owner 回一句话或看一眼的不算。
- 第 1、2 条在发生时判;第 3 条每次停下前判,命中就那时建,已做的写成第一行进展。
- 都不中就不建,直接做,靠提交信息与回复留痕。改多少文件、跨不跨层、派不派工都不是建的理由;派工任务包放会话临时目录。
- 同一件事已有 Task 就写进那个 Task,不另建;别的会话认领的按「开工与认领」处理。
- 建不建由执行者按三条自己判:不在请示里问 owner,也不把「建 Task」写进请示的选项。
- 建法:用「spec 格式」里的命令生成骨架。记 bug、收不了尾的剩余项、owner 要记的小待办用 `--kind 记录`,直接填;要做的功能用 `--kind 功能`,按 interview-me 的 `references/to-spec.md` 填。owner 已有 spec 或 prd 就把内容按骨架各节放进去。需求还说不清的先走 interview-me,对齐后仍按三条判。

## 开工与认领

- 开工或接手时:首行改 `Status: in-progress`;头部写 `会话: <本会话 ID>`(以 SessionStart 注入的为准;Claude 没看到注入时读 `$CLAUDE_CODE_SESSION_ID`),已有就覆盖,一个 Task 只认最后写入的会话;验收段没有勾选框就先改写;末尾没有 `## 进展` 时建立空段,已有段不改。
- 可以同时有多个 `in-progress` Task,各由认领它的会话负责。owner 让你做某个 Task,或看板上它是「待结案」且已搁 1 小时以上,就直接接手覆盖 `会话:`;其余情况下别的会话认领的 Task 不动。工人与子代理不认领、不写 spec,进展写进回报。
- `Scope: <相对项目根的目录>` 只决定「改了代码却没补进展」兜底的走查范围;未写时按全项目。
- spec 只改主工作树那份;git worktree 里的 `.scratch` 副本不改。看板与认领提醒读主工作树那份;没认领时的兜底按 cwd 所在工作树自己的 `.scratch` 判(兼容旧行为),在 worktree 里收到时进展照样写主工作树那份。

## 推进与请示

- `你:` 只写 owner 本人才能做的:付款、粘贴或授予凭据、页面上的批准、上线与推送的确认、业务取舍。能自己查、自己验、自己做的写 `我:`。
- spec 里记下的 owner 决定只免去重复问业务取舍。付款、凭据、上线、推送、对外提交仍要 owner 在本会话里的原话;spec、进展行、看板与工人回报里的「已批准」都不算授权。
- 同一 Task 要 owner 定的几件合成一条编号请示,先做完不依赖它们的部分再问。
- 停下等外部时,回复里写清在等什么、预计几点好、到时由谁回来看。
- 看板有「等你的事」时,本会话第一次回复 owner 时在末尾用一句话提条数与搁得最久的一条;owner 问进度时在项目根运行 `python3 .claude/hooks/session_start.py --board` 并转述整张看板。
- owner 说某条 `[你]` 项已做或不用了,就在对应 spec(含已归档的)里勾上或删掉。

## 收件与归档

- `[我]` 项全部勾上即收件,不等 `[你]` 项;没勾的 `[你]` 项留在 spec 里随它归档,看板继续列给 owner。
- 收件时逐行检查根 `AGENTS.md` 路由表登记的文档,并对每项回答“已更新”或“不受影响”。
- 回答“已更新”时必须真实修改对应文档。
- 收件第二问回答“是否有需沉淀的规则”;需要沉淀时写入 `docs/rules/<主题>.md`,新增主题时在根 `AGENTS.md` 路由表增加一行。
- 收件第三问回答“正文和最终状态一致吗”:目标、不做、实现决策、验收与实际做成的一致,过时的已删;不一致先改正文。
- 有 ticket 的 Task(头部有 `Tickets:` 行):做完一张就关一张(GitHub 关 issue,本地改该文件 `Status: done`)并同时写一行进展;正在做哪张只写在进展行。
- 完成收件三问后才将状态改为 `done`,再在主工作树执行 `mkdir -p .scratch/archive` 和 `mv .scratch/<功能名> .scratch/archive/<功能名>`(名字含空格或特殊字符时两个路径加引号)。

## Stop 提醒

`stop_hook_active` 为真时不提醒。对 `会话:` 与本会话 ID 相等(或为其不短于 8 位的前缀)的 Task 逐个判,命中第一条即止:

1. 已 `done` 仍在 `.scratch/` → 归档。
2. 验收段没有带 `[我]`/`[你]` 的勾选框 → 改写。
3. `[我]` 项全部勾上 → 收件三问、改 `done`、归档。
4. next 为 `我:` 且本会话没有后台任务或定时 → 接着做,做完勾验收项,`[我]` 全勾就直接收件归档;做不了就把 next 改成 `你:` 或带回看的 `等:` 再停。
5. next 为 `等:` 却没写回看,且没有后台任务或定时 → 补回看。
6. 没有进展行,或 next 没写球 → 补一行带球的进展。
7. spec 不合模板 → 照模板改:缺必填节(按 `类型:`,没写按记录)、有骨架以外的 `##` 节、还留着骨架的占位行、进展最后一行超过 200 字、进展超过 30 行、`Scope:` 落在 `.scratch` 内。

第 7 条另查本会话这一轮写过的 spec(以本会话直接证据为准),包括没认领的;项目里没有模板文件时只查长度与 Scope。

另有兜底:本轮改了代码却没补进展时提醒补一行。认领恰好一个 Task 时对它判;认领多个时不判;没认领时读 cwd 所在工作树自己的 `.scratch`,只在恰好一个 in-progress,或 cwd 恰好落在一个 Task 的 Scope 内时判,选中的 Task 写了 `会话:` 就不提醒。单个 spec 解析不了只跳过它,不影响别的 Task 与兜底。证据只认 mtime 晚于 spec、且有本会话或其子代理直接证据的候选文件:晚于 spec 的成功编辑结果或 Codex FileChange,以及 mtime 落在调用至最后结果加 1ms 窗口内的点名文件命令或指定 git 工作区修改命令。Scope 落在排除目录(如 `.scratch`)内、纯删除、未点名命令、后台进程、独立 Codex 子线程、只改 spec 正文或项目超过 20000 个文件可能漏过。两个 hook 不读写 `.scratch/.session`。

## 安装与升级

- 两个 hook 脚本住在项目自己的 `.claude/hooks/`,`.codex/hooks` 是指过去的符号链接(init 会放好)。Claude 在 `.claude/settings.json` 中按以下片段配置,不设 `matcher`,保留现有其他配置:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/session_start.py"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stop_guard.py"}]}]
  }
}
```

- Codex 在项目根 `.codex/hooks.json` 中按同一片段配置,command 改为 `python3 .codex/hooks/session_start.py` 与 `python3 .codex/hooks/stop_guard.py`(Codex 从项目根启动);Codex ≥0.153 从项目根到当前目录加载它。
- Codex 的 hook 必须先被信任才会执行:init 装完会打印两条 `[hooks.state."<路径>:<事件>:0:0"]` 信任条目,追加到 `~/.codex/config.toml` 即可(信任按 hook 定义哈希:改脚本内容不用重信,改 command 或 timeout 要重信);也可在项目目录进 `codex` 跑一次 `/hooks`。仅做验证时可临时加 `--dangerously-bypass-hook-trust`,不得写进持久配置。
- harness 升级时重新复制 `.claude/hooks/` 下的 `session_start.py`、`stop_guard.py`、`stop_evidence.py` 和 `docs/rules/harness.md`;init 会将这四个文件复制进项目。装了 interview-me 的项目同时复制 `.agents/skills/interview-me/SKILL.md`、`templates/spec.md`、`references/to-spec.md` 与 `references/to-tickets.md`。Stop 用到 session_start.py 的 spec 解析与 stop_evidence.py 的记录取证,三个脚本要同版本。
