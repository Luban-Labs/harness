# 核心判断

本表登记被两处以上用来做决定的判断,每个概念一节,写明唯一实现;规则见 docs/rules/harness.md「核心判断只写一份」。每节以 `## <概念名>` 开头,下列定义、唯一实现、语义例外、待收口四项,没有的写「无」。

## Task 目录
- 定义:`.scratch/` 下一个直接子目录算 Task,要同时满足:不叫 `archive`、是真目录不是符号链接、`spec.md` 解析得了、名字不含换行;`.scratch` 本身是符号链接时一个都不算。
- 唯一实现:session_start.read_tasks(逐个目录交给 session_start.task_at,归档区的 Task 也用 task_at)
- 语义例外:无
- 待收口:无

## Scope
- 定义:spec 头部 `Scope:` 的值归一成项目根下的一个目录:相对路径,不含空段、`.`、`..` 与反斜杠,不逃出项目根,已存在时必须是目录;不合格时整份 spec 解析失败。
- 唯一实现:session_start.task_scope
- 语义例外:无
- 待收口:migrate_trellis._normalize_scope 收 `--scope` 参数时另写了一份:多拦 `.git` 与经过符号链接的路径(迁移自己的安全检查),却不拦反斜杠,含反斜杠的 Scope 迁出后两个 hook 都判这份 spec 解析失败而跳过;计划:下次改迁移脚本时先过 session_start.task_scope,再加迁移自己的两条检查。

## 类型
- 定义:spec 头部 `类型:` 的值,按头部解析的口径读:键两侧空格、全角冒号都认;没写为空,Stop 第 7 条按记录查。
- 唯一实现:session_start.read_task(返回的 `kind`)
- 语义例外:无
- 待收口:无

## 认领
- 定义:spec 的 `会话:` 与一个会话 ID 相等,或是它不短于 8 位的前缀,就算这个会话认领了该 Task;看板找认领会话的进程登记与会话记录也按这条配。
- 唯一实现:session_start.session_matches
- 语义例外:无
- 待收口:无

## 主工作树
- 定义:从 cwd 往上第一个有 `.scratch/` 目录的是扫描根;cwd 在一个回链核实过的 git worktree 里、且主工作树有真 `.scratch/` 时,Task 根是主工作树,否则同扫描根;扫描根的 `.scratch` 是符号链接时没有 Task 根。
- 唯一实现:session_start.project_roots
- 语义例外:无
- 待收口:无

## hook 已登记
- 定义:配置文件某个事件下已有一条 command 与 harness 要装的命令逐字相同,就算这条 hook 已登记。
- 唯一实现:init.missing_hooks
- 语义例外:无
- 待收口:无

## spec 的节
- 定义:spec 里以 `## ` 开头的行起一节,标题是其后两头去空格的文字,按标题开头认节(如「验收」「进展」);一节到下一个 `## ` 或 `# ` 标题为止;同名的节有几个,按出现顺序连起来读。
- 唯一实现:session_start.spec_sections(按标题取非空行用 session_start.section_lines)
- 语义例外:无
- 待收口:无

## 待结案
- 定义:Task 的验收里有 `[我]` 项且全部勾上,只差收件三问、改 done 与归档;看板标「待结案」,Stop 提醒去结案。
- 唯一实现:session_start.ready_to_close
- 语义例外:无
- 待收口:无

## 项目代码目录
- 定义:目录名是 `.scratch`、`.git`、`.claude`、`.codex` 或依赖与构建产物目录(`node_modules`、`.venv`、`venv`、`__pycache__`、`dist`、`build`、`.next`、`target`)的,其下不算项目代码;Stop 兜底找代码改动证据、同类判断提醒找新函数与同类都按它跳过。
- 唯一实现:stop_evidence.excluded_dir
- 语义例外:同类判断提醒另跳过测试目录与测试文件(judgment_twins.code_file),理由:测试函数名词多,和任何判断都撞,列出来全是噪音;Stop 兜底的改动证据仍算测试文件。
- 待收口:无

## 本会话记录
- 定义:Stop 输入的 `transcript_path` 那份记录,加上同名目录下 `subagents/` 里递归找到的全部 `.jsonl`;Stop 第 7 条取证、改动未记进展的兜底取证、同类判断提醒都只读这些。
- 唯一实现:stop_evidence.session_records
- 语义例外:无
- 待收口:无

## 本回合
- 定义:Claude 记录里最后一条回合结束记录(`stop_hook_summary` 或 `turn_duration`,Stop hook 跑完后才写)之后,Codex 记录里最后一个 `task_started` 之后;回合中途到达的用户消息、任务通知、同伴消息都算本回合内。记录尾部没有边界时从读到的第一行算起。
- 唯一实现:stop_evidence.turn_boundary
- 语义例外:无
- 待收口:无
