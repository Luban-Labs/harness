Status: done
类型: 功能
建单: 1(owner 对「建 Task 开做」回「行」)
会话: e78a82c0-b187-4bec-b0ce-5d9c9aae5026

# 判断表按需查

目标:核心判断表只当索引,一节一张短卡,详情按需看,工人不再整表读进上下文(出处:krapi 会话 11-15 转来的实测,krapi 表 46.9KB、23 节、最长一节 6.8KB;owner「没必要整体都给Agent看…可以做成按需加载…这里只写索引和简介」)。

## 问题

规则只规定每节写定义、唯一实现、语义例外、待收口四项,没写什么不进表、没有长度上限,也没有任何检查。每个 Task 收尾都往已有条目里加字:事故经过、owner 原话、机制步骤、改动历史都堆进表里,一节装下几个判断。派工时工人常被要求读整张表,krapi 一次就占掉几万字的上下文。

## 解法

- 表里一节是一张索引卡:定义一句,唯一实现只列路径,例外和待收口各一行,一节不超过 300 字;需要时末尾一行链到 `docs/judgments/<概念>.md`。
- 详情文件只写代码看不出的东西:边界、为什么不那样做、容易踩的坑;不抄代码步骤。大多数概念不需要它。
- owner 原话、事故经过进 spec「不做」、docs/decisions.md 或提交信息;改动历史留给 git log。
- 新脚本 `judgments.py`:`ls` 列概念名加定义,`show <名>` 看一节,`show <名> --detail` 连详情一起看,`check` 查形状。
- 开场看板照旧列概念名,后面加一句「看哪节用 judgments.py show <名>」;派工时任务书写 show 命令,不让读整表。
- Stop 对本回合改过的节查形状,超长或夹了出处、日期的点名。

## 不做

- 表改成 JSON 存储(出处:owner 对「表保留 md,加 judgments.py」回「行」)。
- 机制细节写进代码注释(出处:owner 担心「代码行数又会膨胀从而触碰到我规定的最多行数」,改为放 docs/judgments/,owner「1 行」)。
- krapi 现有 23 节本 Task 不瘦身,krapi 会话在 melonflow Task 收尾后按新规则做(出处:owner「3 收尾后」)。
- README 过长另议(出处:krapi 会话转述的成因不同,owner 未要求)。
- 改 docs/decisions.md 已有条目的长度(出处:推断不在本次目标内,owner 未要求)。

## 影响面

- 整体:属于「开场看板」「Stop 检查」「安装与迁移」三块(docs/rules/architecture.md);表的解析只有 `session_start.core_judgment_entries` 一份,被 session_start.core_judgments、judgment_twins、dictionary_updates 共用。
- 重排:沿原结构;新脚本只调用 session_start 的解析,不另写一份;形状检查放新脚本,由 stop_guard 像 judgment_twins 那样在函数内导入、出错只丢这一项。
- 表的写法规则:docs/rules/harness.md「核心判断只写一份」(引用)→ 跟改,补不进表、各栏限长、详情文件、用脚本查、派工点名节;收件第一问(引用)→ 跟改,加「动过的节合不合形状」;开头总述里关于概念清单的描述 → 跟改。
- 表模板:templates/core-judgments.md(副本,init 与迁移从它取空表)→ 跟改格式说明、示例与开头说明;init.empty_core_judgments 与 migrate_trellis 读标记行之前 → 不受影响:标记行保留。
- 表开头说明:docs/rules/core-judgments.md(harness 自己的表)→ 跟改开头说明,并把超 300 字的 5 节(本会话记录、Scope、本回合、项目代码目录、代码里某个名字的定义)删短。
- 开场提示文案:session_start.core_judgments → 跟改加一句脚本用法;test_session_start、test_core_judgments 里对文案的断言 → 跟改。
- hook 清单:init.HOOKS、「安装与升级」的脚本清单、.codex/hooks 链接 → 跟改加 judgments.py。
- 路由行:AGENTS.md、templates/AGENTS.md「新写或改一个判断…」→ 不受影响:仍指向 docs/rules/core-judgments.md,表开头说明会写「用 judgments.py 查」;迁移按「读」列核对固定行不变。
- architecture.md 职责表引用的概念名 → 不受影响:概念不改名。
- 已装项目(krapi、ticket-seller-tools 等)的表 → 已知差异:升级后 Stop 只点名本回合改过的超长节,不会一次报全表;记在 docs/decisions.md 本条。
- 复用:核心判断表条目:查表「核心判断表条目」→ 复用 `session_start.core_judgment_entries`,需要每节正文时在同处扩展,不另写解析。

## 实现决策

- 长度按字符数算(中文一字一个):定义一句、不超过 120 字;语义例外、待收口每项一行、不超过 120 字;唯一实现只许反引号路径加分隔符,不许夹说明;一节合计不超过 300 字(出处:owner 对「一节 300、定义和每项例外 120」回「行」)。
- 一节里不许出现「出处:」与 `MM-DD` 这类日期(出处:owner 认可的「不进表」清单)。
- 详情文件 `docs/judgments/<概念名>.md`:只能由对应节的「详情」一行链到;check 报两种错——节链了不存在的文件、文件没有节链它。
- Stop:对比 HEAD 与磁盘,只查本回合内容变了的节;每次最多点名 3 节,并写总数。表不存在或解析失败时跳过。
- judgments.py 用法完整写在它的 `--help`;其他入口只放一行指向。
- 过大判定:不过大(模块在 hook 一层,一次会话可演示完)。

## 测试决策

- 切入点:judgments.py 的命令行输出与 stop_guard 的提醒文本,用 tests/ 里现有的临时项目夹具(test_core_judgments.py、test_judgment_twins.py 是先例)。
- 覆盖:ls 与 show 的输出;check 的超长、夹说明的唯一实现、出处、日期、孤儿与断链;Stop 只点名本回合改过的节;init 装上新脚本。
- 现有测试全过:`python3 -m unittest discover -s tests -v`。

## 未知

- 无。

## 验收

- [x] [我] 在 harness 根跑 `judgments.py ls`、`show Scope`、`check`,输出符合上面写法;harness 自己的表 `check` 通过。
- [x] [我] 造一个临时项目:改一节写成 400 字并夹「出处:」,Stop 点名这一节;没改的长节不点名。
- [x] [我] `python3 -m unittest discover -s tests -v` 全过。
- [x] [我] 新规则发给 krapi 会话(krapi-c8)。
- [ ] [等] krapi melonflow Task 收尾: krapi 的表按新规则写了 Melon 条目,`judgments.py check` 对改过的节通过。

## 进展
- 11-15 22:03 done: 建 Task、写 spec、开 worktree feat/judgments,派 Agy 实现 | next: 等: Agy 工人交工(回看: agent-watch 交工通知到达时,主会话核对后派 Codex 对抗审)
- 11-15 22:28 done: Agy 交工,复跑 300 测试全过、check 通过 | next: 等: Codex 对抗审 t4s(回看: agent-watch 交工通知到达时)
- 11-15 22:35 done: Codex 审出 3 blocking 1 important | next: 等: Agy 修审查意见(回看: agent-watch 交工通知到达时)
- 11-15 22:56 done: 修完审查 4 条,304 测试过,合进 main;krapi 已通知升级;收件三问已答,归档 | next: 等: krapi melonflow Task 收尾(回看: 每次开会话看板)
