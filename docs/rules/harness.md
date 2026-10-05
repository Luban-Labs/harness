# Task 规则

周期链:对需求用 interview-me skill(两平台都按其描述触发;采访式,一次一问,判大才建 Task)→ 建 Task(`.scratch/<功能名>/spec.md`,首行 `Status: ready-for-agent`)→ 开工(改 `in-progress`)→ 每轮停下前补一行进展(Stop hook 兜底)→ 收件两问 → 改 `done` 并归档。新会话由 SessionStart hook 注入当前 Task;没有活跃 Task 时什么都不注入。

- Task 目录为 `.scratch/<功能名>/`，`spec.md` 首行为 `Status: ready-for-agent`、`Status: in-progress` 或 `Status: done`。
- 直接建 Task，不采访：owner 说「建个 Task」、要记一个 bug、或一个自己已确定但想留记录的小改动 → 直接建 `.scratch/<功能名>/spec.md`，首行 `Status: ready-for-agent`，正文只写目标一句与验收演示；owner 已有 spec 或 prd 就原样放进去补首行。需求还说不清的才走 interview-me。
- 开工前将 `spec.md` 首行改为 `Status: in-progress`；末尾没有 `## 进展` 时建立空段，已有段不改。
- 同一时刻只保留一个 `in-progress` Task；发现其他活跃 Task 时先收件或改回 `ready-for-agent`。
- 并行开工例外：在各 Task 的 `spec.md` 第二行写 `Scope: <相对项目根的目录>`，允许多个 `in-progress`；进入仅匹配一个 Scope 的目录开工，Stop 只统计该 Scope 内的改动；未写 Scope 时按全项目处理且不参与多 Task 匹配。
- 进展段只追加以下格式的行：`- MM-DD HH:MM done: … | next: … | 别再试: …`。
- 收件时逐行检查根 `AGENTS.md` 路由表登记的文档，并对每项回答“已更新”或“不受影响”。
- 回答“已更新”时必须真实修改对应文档。
- 收件第二问回答“是否有需沉淀的规则”；需要沉淀时写入 `docs/rules/<主题>.md`，新增主题时在根 `AGENTS.md` 路由表增加一行。
- 有 ticket 的 Task（spec 头部有 `Tickets:` 行）：做完一张就关一张（GitHub 关 issue，本地改该文件 `Status: done`）并同时写一行进展；正在做哪张只写在进展行；全部关了才能收件。
- 完成收件两问后才将状态改为 `done`，再执行 `mkdir -p .scratch/archive` 和 `mv .scratch/<功能名> .scratch/archive/<功能名>`。
- 两个 hook 脚本住在项目自己的 `.claude/hooks/`，`.codex/hooks` 是指过去的符号链接（init 会放好）。Claude 在 `.claude/settings.json` 中按以下片段配置，不设 `matcher`，保留现有其他配置：

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/session_start.py"}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stop_guard.py"}]}]
  }
}
```

- Codex 在项目根 `.codex/hooks.json` 中按同一片段配置，command 改为 `python3 .codex/hooks/session_start.py` 与 `python3 .codex/hooks/stop_guard.py`（Codex 从项目根启动）；Codex ≥0.153 从项目根到当前目录加载它。
- Codex 的 hook 必须先被信任才会执行：init 装完会打印两条 `[hooks.state."<路径>:<事件>:0:0"]` 信任条目，追加到 `~/.codex/config.toml` 即可（信任按 hook 定义哈希：改脚本内容不用重信，改 command 或 timeout 要重信）；也可在项目目录进 `codex` 跑一次 `/hooks`。仅做验证时可临时加 `--dangerously-bypass-hook-trust`，不得写进持久配置。
- harness 升级时重新复制 `.claude/hooks/stop_guard.py`、`.claude/hooks/session_start.py` 和 `docs/rules/harness.md`；init 会将这三个文件复制进项目。
- 每轮停下前仍须补进展并在收件时核对：Stop 只对 mtime 晚于 spec 且有本会话或其子代理直接证据的候选文件提醒；证据限晚于 spec 的成功编辑结果或 Codex FileChange，以及 mtime 落在调用至最后结果加 1ms 窗口内的点名文件命令或指定 git 工作区修改命令。两个 hook 不再读写 `.scratch/.session`；纯删除、未点名命令、后台进程、独立 Codex 子线程、只改 spec 正文或项目超过 20000 个文件可能漏过。
