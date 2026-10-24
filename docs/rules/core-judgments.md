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
