# 核心判断

本表登记被两处以上用来做决定的判断、业务数、限制或保护,每节一张 ≤300 字索引卡;规则见 docs/rules/harness.md「核心判断只写一份」。用 `python3 .claude/hooks/judgments.py` 按需查(`ls`、`show <名>`、`show <名> --detail`、`check`),不整表读进上下文。每节以 `## <概念名>` 开头,下列定义、唯一实现、语义例外、待收口四项(没有写「无」),需要时末尾加「详情」。

## Task 目录
- 定义:`.scratch/` 下一个直接子目录算 Task,要同时满足:不叫 `archive`、是真目录不是符号链接、`spec.md` 解析得了、名字不含换行;`.scratch` 本身是符号链接时一个都不算。
- 唯一实现:`.claude/hooks/session_start.py:read_tasks`
- 语义例外:无
- 待收口:无

## Scope
- 定义:spec 头部 `Scope:` 的值归一成项目根下的相对目录,不含空段、`.`、`..` 与反斜杠,不逃出项目根且存在时须为目录,否则整份 spec 解析失败。
- 唯一实现:`.claude/hooks/session_start.py:task_scope`
- 语义例外:无
- 待收口:`migrate_trellis._normalize_scope` 另写一份(多拦 `.git` 与符号链接但漏拦反斜杠);计划改用 `task_scope` 再补两项校验。

## 类型
- 定义:spec 头部 `类型:` 的值,按头部解析的口径读:键两侧空格、全角冒号都认;没写为空,Stop 第 7 条按记录查。
- 唯一实现:`.claude/hooks/session_start.py:read_task`
- 语义例外:无
- 待收口:无

## 认领
- 定义:spec 的 `会话:` 等于会话 ID 或为其 ≥8 位前缀即认领(DSH 顶层须为 `session-` 加 ≥8 位 UUID),看板探测进程与记录亦按此匹配。
- 唯一实现:`.claude/hooks/session_start.py:session_matches`
- 语义例外:无
- 待收口:无

## 主工作树
- 定义:从 cwd 向上首个含 `.scratch/` 的是扫描根(符号链接则无 Task 根);回链核实的 git worktree 且主树有真 `.scratch/` 时 Task 根为主树,否则同扫描根。
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
- 唯一实现:`.claude/hooks/session_start.py:spec_sections`
- 语义例外:无
- 待收口:无

## 待结案
- 定义:Task 的验收里有 `[我]` 项且全部勾上,只差收件三问、改 done 与归档;看板标「待结案」,Stop 提醒去结案。
- 唯一实现:`.claude/hooks/session_start.py:ready_to_close`
- 语义例外:无
- 待收口:无

## 项目代码目录
- 定义:目录名属 .scratch、.git、.claude、.codex、node_modules、.venv、venv、__pycache__、dist、build、.next、target 时不算代码。
- 唯一实现:`.claude/hooks/stop_evidence.py:excluded_dir`
- 语义例外:同类判断(`judgment_twins.code_file`)另跳过测试目录与测试文件,防测试函数撞名噪音;Stop 兜底仍算测试。
- 待收口:无

## 本会话记录
- 定义:取当前会话主记录及其子代理记录,供 Stop 兜底、spec 格式、同类判断、字典更新与判断表形状取证使用。
- 唯一实现:`.claude/hooks/stop_evidence.py:evidence_sources`
- 语义例外:无
- 待收口:无
- 详情:`docs/judgments/本会话记录.md`

## 本回合
- 定义:从宿主最后一条有效回合边界(Claude 上轮结束记录/Codex task_started/DSH turn/start)起到当前的区间,含中途到达的消息。
- 唯一实现:`.claude/hooks/stop_evidence.py:turn_boundary`
- 语义例外:无
- 待收口:无
- 详情:`docs/judgments/本回合.md`

## CC 项目信任
- 定义:复用 CC 的 hasTrustDialogAccepted 严格 true 记录,分别计算 settings 目录、local settings 目录、hook 项目目录与信任键;不能用其中一值替代其它值。
- 唯一实现:`dsh/cc_hooks.py:project_context`
- 语义例外:DSH 未提供 CC 显式 projectConfigRoot 或运行中 worktree 切换参数,不推断这些值。
- 待收口:无

## DSH 日志位置
- 定义:按完整 session_id 在 DSH 会话目录跨创建 cwd 查找唯一 v4 日志,验证 header.id 与目录一致;子日志由 parentSession 链关联,重复路径或索引不完整时不猜。
- 唯一实现:`dsh/cc_hooks.py:session_metadata`
- 语义例外:Stop 取证只校验并读取调度器传来的路径,不重新定位;看板直调没有索引时不标 DSH 状态。
- 待收口:无

## 本回合编辑
- 定义:从本会话及子代理记录取本轮成功编辑,按宿主回合边界过滤;Stop 同类判断、字典更新与判断表形状共用,片段由 edit_pieces 解析。
- 唯一实现:`.claude/hooks/stop_evidence.py:turn_edits`
- 语义例外:无
- 待收口:无

## 核心判断表条目
- 定义:跳过代码围栏,按二级标题与「唯一实现」反引号 `路径:名` 抽出概念及整节原文;开场清单、字典更新、judgments.py 与判断表形状共用。
- 唯一实现:`.claude/hooks/session_start.py:core_judgment_entries`
- 语义例外:「待定」或旧格式仍保留概念名,没有可机械检查的唯一实现位置。
- 待收口:无

## 工作树代码范围
- 定义:从当前 git 仓库和可验证的同仓 worktree 找用于同类判断与字典更新提醒的代码范围,不把其他仓库或未登记目录算入。
- 唯一实现:`.claude/hooks/stop_evidence.py:worktree_roots`
- 语义例外:无
- 待收口:无

## 代码里某个名字的定义
- 定义:Python 整文件某名字的全部定义签名(含嵌套层与份数,保留装饰器、类型参数、参数返回、基类关键字与顶层/类赋值层级,不含函数体与值)。
- 唯一实现:`.claude/hooks/dictionary_updates.py:definition_signatures`
- 语义例外:无
- 待收口:`.claude/hooks/judgment_twins.py:definitions` 仍按片段正则认定义,暂不合并。

## 判断表形状
- 定义:校验核心判断表每节字段、字符上限、禁写项、唯一实现引用格式及 `docs/judgments/` 断链、符号链接与孤儿文件。
- 唯一实现:`.claude/hooks/judgments.py:table_issues`
- 语义例外:无
- 待收口:无
