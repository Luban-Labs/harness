# 核心判断

本表登记被两处以上用来做决定的判断、业务数、限制或保护,每个概念一节,写明唯一实现;规则见 docs/rules/harness.md「核心判断只写一份」。唯一实现写成反引号包住的项目根相对 `路径:函数名`、`路径:类名` 或 `路径:类名.方法名`。每节以 `## <概念名>` 开头,下列定义、唯一实现、语义例外、待收口四项,没有的写「无」。

## Task 目录
- 定义:`.scratch/` 下一个直接子目录算 Task,要同时满足:不叫 `archive`、是真目录不是符号链接、`spec.md` 解析得了、名字不含换行;`.scratch` 本身是符号链接时一个都不算。
- 唯一实现:`.claude/hooks/session_start.py:read_tasks`(逐个目录交给同文件的 task_at,归档区的 Task 也用 task_at)
- 语义例外:无
- 待收口:无

## Scope
- 定义:spec 头部 `Scope:` 的值归一成项目根下的一个目录:相对路径,不含空段、`.`、`..` 与反斜杠,不逃出项目根,已存在时必须是目录;不合格时整份 spec 解析失败。
- 唯一实现:`.claude/hooks/session_start.py:task_scope`
- 语义例外:无
- 待收口:migrate_trellis._normalize_scope 收 `--scope` 参数时另写了一份:多拦 `.git` 与经过符号链接的路径(迁移自己的安全检查),却不拦反斜杠,含反斜杠的 Scope 迁出后两个 hook 都判这份 spec 解析失败而跳过;计划:下次改迁移脚本时先过 session_start.task_scope,再加迁移自己的两条检查。

## 类型
- 定义:spec 头部 `类型:` 的值,按头部解析的口径读:键两侧空格、全角冒号都认;没写为空,Stop 第 7 条按记录查。
- 唯一实现:`.claude/hooks/session_start.py:read_task`(返回的 `kind`)
- 语义例外:无
- 待收口:无

## 认领
- 定义:spec 的 `会话:` 与一个会话 ID 相等,或是它不短于 8 位的前缀,就算这个会话认领了该 Task;DSH 顶层 ID 的前缀须为 `session-` 加至少 8 位 UUID,裸 UUID 前缀和 `session-` 不认领;看板找认领会话的进程登记与会话记录也按这条配。
- 唯一实现:`.claude/hooks/session_start.py:session_matches`
- 语义例外:无
- 待收口:无

## 主工作树
- 定义:从 cwd 往上第一个有 `.scratch/` 目录的是扫描根;cwd 在一个回链核实过的 git worktree 里、且主工作树有真 `.scratch/` 时,Task 根是主工作树,否则同扫描根;扫描根的 `.scratch` 是符号链接时没有 Task 根。
- 唯一实现:`.claude/hooks/session_start.py:project_roots`
- 语义例外:无
- 待收口:无

## Git 工作树回链
- 定义:工作树的 `.git` 文件指向 `.git/worktrees/` 登记目录,登记的 gitdir 回指该文件,存在的 commondir 也指向主树 `.git`,才返回该主树。
- 唯一实现:`.claude/hooks/session_start.py:main_worktree`
- 语义例外:project_roots 还要求主树有真 `.scratch` 才将它作为 Task 根;CC 信任根解析直接用回链结果,不以 `.scratch` 为条件。
- 待收口:无

## hook 已登记
- 定义:配置文件某个事件下已有一条 command 与 harness 要装的命令逐字相同,就算这条 hook 已登记。
- 唯一实现:`init.py:missing_hooks`
- 语义例外:无
- 待收口:无

## spec 的节
- 定义:spec 里以 `## ` 开头的行起一节,标题是其后两头去空格的文字,按标题开头认节(如「验收」「进展」);一节到下一个 `## ` 或 `# ` 标题为止;同名的节有几个,按出现顺序连起来读。
- 唯一实现:`.claude/hooks/session_start.py:spec_sections`(按标题取非空行用同文件的 section_lines)
- 语义例外:无
- 待收口:无

## 待结案
- 定义:Task 的验收里有 `[我]` 项且全部勾上,只差收件三问、改 done 与归档;看板标「待结案」,Stop 提醒去结案。
- 唯一实现:`.claude/hooks/session_start.py:ready_to_close`
- 语义例外:无
- 待收口:无

## 项目代码目录
- 定义:目录名是 `.scratch`、`.git`、`.claude`、`.codex` 或依赖与构建产物目录(`node_modules`、`.venv`、`venv`、`__pycache__`、`dist`、`build`、`.next`、`target`)的,其下不算项目代码;Stop 兜底找代码改动证据、同类判断提醒找新函数与同类都按它跳过。
- 唯一实现:`.claude/hooks/stop_evidence.py:excluded_dir`
- 语义例外:同类判断提醒另跳过测试目录与测试文件(judgment_twins.code_file),理由:测试函数名词多,和任何判断都撞,列出来全是噪音;Stop 兜底的改动证据仍算测试文件。
- 待收口:无

## 本会话记录
- 定义:Claude/Codex 取 Stop 输入的 `transcript_path` 那份记录,加上同名目录下 `subagents/` 里递归找到的全部 `.jsonl`;DSH 只取调度器的 dsh_transcript_path 与 dsh_child_transcript_paths,核对 v4 header.id/parentSession;Stop 第 7 条取证、改动未记进展的兜底取证、同类判断提醒都只读这些。
- 唯一实现:`.claude/hooks/stop_evidence.py:evidence_sources`(Claude/Codex 调同文件的 session_records;DSH 调 dsh_session_records 验证调度器传入的主/子日志路径)
- 语义例外:无
- 待收口:无

## 本回合
- 定义:Claude 记录里最后一条回合结束记录(`stop_hook_summary` 或 `turn_duration`,Stop hook 跑完后才写)之后,Codex 记录里最后一个 `task_started` 之后;DSH 取 seq/time/data.turn 均有效的最后一条 `turn/start`,强制继续产生的 UserPromptSubmit 不换回合。回合中途到达的用户消息、任务通知、同伴消息都算本回合内。Claude/Codex 记录尾部没有边界时从读到的第一行算起,DSH 没有有效边界时不据此阻塞。
- 唯一实现:`.claude/hooks/stop_evidence.py:turn_boundary`
- 语义例外:无
- 待收口:无

## CC 项目信任
- 定义:复用 CC 的 hasTrustDialogAccepted 严格 true 记录,分别计算 settings 目录、local settings 目录、hook 项目目录与信任键;不能用其中一值替代其它值。
- 唯一实现:`dsh/cc_hooks.py:project_context`(调度器与 init 经 trusted_project 共用)
- 语义例外:DSH 未提供 CC 显式 projectConfigRoot 或运行中 worktree 切换参数,不推断这些值。
- 待收口:无

## DSH 日志位置
- 定义:按完整 session_id 在 DSH 会话目录跨创建 cwd 查找唯一 v4 日志,验证 header.id 与目录一致;子日志由 parentSession 链关联,重复路径或索引不完整时不猜。
- 唯一实现:`dsh/cc_hooks.py:session_metadata`
- 语义例外:Stop 取证只校验并读取调度器传来的路径,不重新定位;看板直调没有索引时不标 DSH 状态。
- 待收口:无

## 本回合编辑
- 定义:从本会话及子代理记录取本轮成功编辑,按宿主回合边界过滤;Stop 的同类判断提醒和字典更新提醒共用这一份取证,编辑的 old/new 与 FileChange 片段由同文件 edit_pieces 解析。
- 唯一实现:`.claude/hooks/stop_evidence.py:turn_edits`
- 语义例外:无
- 待收口:无

## 核心判断表条目
- 定义:跳过代码围栏,只按二级标题取概念,并从每节「唯一实现」解析反引号包住的项目根相对 `路径:函数名`、`路径:类名` 或 `路径:类名.方法名`;开场概念清单与 Stop 字典更新提醒共用。
- 唯一实现:`.claude/hooks/session_start.py:core_judgment_entries`
- 语义例外:「待定」或旧格式仍保留概念名,没有可机械检查的唯一实现位置。
- 待收口:无

## 工作树代码范围
- 定义:从当前 git 仓库和可验证的同仓 worktree 找用于同类判断与字典更新提醒的代码范围,不把其他仓库或未登记目录算入。
- 唯一实现:`.claude/hooks/stop_evidence.py:worktree_roots`
- 语义例外:无
- 待收口:无

## 代码里某个名字的定义
- 定义:Python 整文件里某个名字的全部定义签名,涵盖任意嵌套层并保留同名定义的份数;都带外层名字、装饰器与类型参数,函数另取参数与返回注解,类另取基类与关键字,模块与类层级的赋值只记名字在哪一层,不含函数体与赋的值。
- 唯一实现:`.claude/hooks/dictionary_updates.py:definition_signatures`
- 语义例外:无
- 待收口:`.claude/hooks/judgment_twins.py:definitions` 仍按片段正则认定义;本 Task 不合并,出处:spec「不做」中 owner 11-02「是这个意思」确认「不改 Stop 按名字找同类的提醒」。
