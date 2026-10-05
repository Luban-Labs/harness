Status: done

# stop-guard v2:凭本会话的直接证据判「本会话改过代码」

## 目标

同一项目里有别的会话在干活时,Stop 兜底只拦真正动过手的会话,不再拦只读会话(owner 10-05「让他以后也不要误判了」)。

## 最短验收演示

1. 回放 10-05 现场(ticket-seller-tools-refactor,Task 邮件-收尾-解析器迁移):两份真实记录截到 10:58:45.061Z、spec mtime 10:57:09.779Z → 只读会话 028f0799 放行、改代码的会话 a6f26dcf 被拦;a6f26dcf 截到它真实停下的 10:59:03.921Z、spec mtime 10:58:56.465Z(进展已写)→ 放行。旧版对 028f0799 拦(已发生)。
2. `python3 -m unittest discover -s tests -v` 全过,新用例覆盖三种证据各自拦与不拦的边界、子代理、Codex、记录缺失与坏行。
3. 真实端到端:同一临时项目里两个 `claude -p` 并发,一个改文件,一个只读并跑一次 pytest 与 ruff → 只拦前者;`codex exec` 改一个文件 → 拦下→补进展→放行。

## 范围与不做项

做:

- 判据:候选 = 范围内 mtime 晚于 spec 的文件(排除目录、20000 上限不变);候选有下列任一条本会话证据才算本会话改动,有一个就拦。出处:10-05 两次误拦(10:58:45 被另一会话的改动拦;11:22:17 被本会话 lint Stop hook 写在项目根的 `.ruff_cache`、`.mypy_cache` 拦),以及三路实测推翻了「mtime 落在本会话工具窗口内就算」:权限等待能把一个 Bash 窗口撑到 71460 秒;并发会话约一半的写入会落进读者的窗口;lint hook 停下后重排文件,会把本会话的真改动挪出窗口。
  1. 编辑工具改过它:Claude Edit/Write/MultiEdit(`file_path`)、NotebookEdit(`notebook_path`)成功,且结果行晚于 spec;Codex `event_msg` item_completed 的 FileChange(`changes` 的路径)完成晚于 spec。与 mtime 无关,formatter 事后重排也认得出。
  2. 命令点了它的名:mtime 落在本会话一次命令类调用的窗口 [调用行时间, 最后结果行时间 + 1ms] 内,且调用输入里有一个路径词的最后一段等于它的文件名。命令类 = Claude Bash;Codex exec、exec_command、shell、local_shell_call、write_stdin、js。
  3. git 改工作区:mtime 落在本会话一次命令类调用的窗口内,且输入里有 git merge/pull/checkout/switch/rebase/reset/stash/cherry-pick/revert/am/apply/restore。出处:WORKERS.md「取完整 diff 对账后并入」——合入是常规改代码动作,旧版拦得到。
- 证据来源:Stop 输入的 `transcript_path`,加 `<transcript_path 去 .jsonl>/subagents/**/*.jsonl`(Claude 子代理与工作流代理改代码是常规动作,旧版拦得到)。Claude 按 `tool_use.id` ↔ `tool_result.tool_use_id` 配对,Codex 按 `call_id` 配对、结束取最后一个 output;没配上的调用不算;坏行逐行跳过;记录读不到 → 放行。出处:三路实测的格式(Claude Code 2.1.289、codex-cli 0.160.0)。
- 先走目录,没有候选直接放行,有候选才解析记录;解析前按子串预筛行,mtime 不晚于 spec 的子代理文件跳过。出处:22.6MB 记录全量解析 128–209ms。
- stop_guard 不再读 `.scratch/.session`,session_start 不再写它。出处:decisions 09-10「两个会话同时开同一项目会互相覆盖标记,v1 接受」;换判据后它没有消费者。
- 文档:docs/rules/harness.md 末两条改写,docs/decisions.md 追加一条;同步到 dashboard(main)与 ticket-seller-tools-refactor(refactor/converge)。

不做:

- 不点名的命令写的文件不算(按 glob 算路径的脚本、对整个目录跑的 formatter、codegen、npm install 改 lockfile):要算就得回到「窗口内一律算」,10-05 的误拦就回来了。
- 后台进程(run_in_background 的 Bash、codex companion/exec 工人)、Codex 子线程(记录在别的 rollout)、Codex 挂起后在两次轮询之间才写的命令,不算发起会话的;发起会话合入或亲手改时照常拦,其余靠自觉与收件核对。
- 本会话点名某文件的命令运行时,并发会话恰好也改了这个文件:仍算本会话的。
- 别的会话写进展刷新 spec mtime、盖住本会话未记的改动:原有行为。
- 删 init 与 migrate_trellis 里的 `.scratch/.session` .gitignore 行:已装项目里还留着旧标记文件,这一行仍把它挡在库外。

## 最小路径

1. 在 `feat/stop-guard-v2` 先写失败用例,再改 stop_guard.py、session_start.py。
2. 跑验收 1、2、3。
3. 对抗审一轮 → 合入 main → 把 stop_guard.py、session_start.py、docs/rules/harness.md 复制到两个已装项目并各自提交。

## 未知与验证动作

- Codex FileChange 是否盖住所有 apply_patch:三路实测 1800/1801 有对应 item;端到端 codex exec 用 apply_patch 改文件再看一次,缺了就把 apply_patch 输入里的路径也算作证据 1。
- 测试与 lint 缓存:验收 3 里只读会话跑 pytest 与 ruff 后不被拦算支持;被拦就另起一版。

## 进展
- 10-06 00:17 done: Astra 交付(diff 6f866b01),亲验 69 个测试(3.14)与 40 个 hook 测试(3.9.6)全过;回放 10-05 三个场景全对(旧版误拦只读会话);端到端:Claude 双会话里写者不写进展时新版只拦写者、旧版两个都拦,只读会话跑 pytest/ruff 后不被拦;Codex apply_patch 凭 FileChange 拦下→补进展→放行 | next: 收 codex 只读对抗审→合入 main→同步 dashboard 与 ticket-seller-tools-refactor | 别再试: 只看 mtime 是否落在本会话工具窗口内(权限等待能把窗口撑到 71460 秒、并发写入约一半落进读者窗口、formatter 事后重排会把真改动挪出窗口)
- 10-06 00:58 done: 外派只读对抗审 FAIL(2 blocking:引号文件名切词、git 全局参数),复现属实;Astra 续包 1 钉回归后报 3 处契约冲突,裁决两层切词(shell 词与命令边界 / 文件名片段)后续包 2 修复并自审补 JS 注释;亲验 diff d11393bf、85 个测试(3.14)与 56 个 hook 测试(3.9.6)全过,15 个反例与常见写法全对,回放三场景全对,端到端 Claude 双会话(写者不写进展)只拦写者、Codex 拦下→补进展→放行;收件一问:docs/rules/harness.md 已更新,tests/ 已更新,init.py --help 不受影响,migrate_trellis.py --help 不受影响;二问:无新增主题规则,新判据已写进 docs/rules/harness.md 末条 | next: 合入 main,同步 dashboard 与 ticket-seller-tools-refactor | 别再试: 对原文跑不认引号的正则切词(会把 "my app.py" 拆成 app.py)
