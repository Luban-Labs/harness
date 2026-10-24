# to tickets:把一个会话做不完的 spec 切成 ticket

译自 mattpocock/skills 的 to-tickets,发布方式按 owner 定:有 GitHub 远端发 issue,没有就本地文件。只在 spec 一个新会话做不完时读;做得完就不切,直接开工。

## 做法

1. **从已有上下文出发。** spec 就在当前会话里,不要 `/clear` 或压缩后再来;还没看过代码就先看,ticket 的标题和描述用项目 CONTEXT.md 的词,遵守相关 ADR。有能让实现变容易的预重构,先切成第一张 ticket。
2. **切纵向切片(tracer bullet)。** 每张 ticket:
   - 纵切一条窄但完整的路径,穿过所有层(schema、API、UI、测试),不是某一层的横切;
   - 做完单独可演示、可验证;
   - 尺寸恰好塞进一个全新的会话,因为领它的人没看过 spec。
   **先定共用契约再切。** 几张 ticket 共用的数据形状、服务接口、schema、API 路径,先写进 spec 的「实现决策」,或单切一张只搭骨架的最小 ticket;第一张只做骨架,不把共用部分和第一个完整功能捆成一张大票——纵切的第一张天然是瓶颈,它越大后面等得越久。
   每张写清 **Blocked by**:必须先做完的其他 ticket,只记真依赖——只依赖已定契约、不依赖别张实现细节的不算阻塞;没有的可以立刻开工。frontier 上的 ticket 同时派出,各开 worktree,派工按 WORKERS.md。
   **宽改造是例外**:一处机械改动(改列名、改共享类型)波及全仓库、任何纵切都无法单独变绿,就按 expand–contract 排:先 expand(新旧并存)→ 分批 migrate(按包或目录切批,每批一张 ticket,都被 expand 阻塞)→ 最后 contract(删旧,被全部 migrate 阻塞)。批次也没法单独绿的,共用一个集成分支,全部阻塞最后一张 integrate-and-verify。
3. **对一轮再发。** 把切法列成编号清单:标题、Blocked by、交付的端到端行为。按采访风格**一次只问最要紧的一个**:粒度太粗还是太细;阻塞边对不对;要不要合并或再拆。最常见的毛病是拆得太碎,拆到每张都没有意义——owner 说合并就合并。owner 点头才发布。
4. **发布。** 按项目情况二选一,把结果写进 spec.md 头部(`Tickets:` 行,头部各行顺序不限):
   - **GitHub**(`git remote -v` 有 GitHub 远端且 `gh auth status` 通过):按依赖顺序建 issue,blocker 先建。`gh issue create --title "<NN>: <标题>" --body-file <临时文件>`,正文用下面 issue 模板。阻塞边用 GitHub 原生依赖:`gh api --method POST repos/<owner>/<repo>/issues/<被阻塞号>/dependencies/blocked_by -F issue_id=<blocker 的数据库 id>`,数据库 id 用 `gh api repos/<owner>/<repo>/issues/<号> --jq .id` 取。写 `Tickets: github #12 #13 #14`。
   - **本地**(没有远端):一张 ticket 一个文件 `.scratch/<功能名>/issues/<NN>-<slug>.md`,从 01 起按依赖顺序编号,用下面文件模板。写 `Tickets: local`。
5. **状态只有两态,正在做哪张只写一处。** GitHub 是 open / closed,本地是 `Status: ready-for-agent` / `done`;ticket 上没有 in-progress。「正在做哪张」只写在 Task 的进展行里(`done: #13 … | next: 等: #14 #15 工人交回(回看: codex-watch 唤醒)`;自己做的写 `我:`);frontier 上的几张可同时派给不同工人,进展行列出正在做的全部票号。能领的就是 blocker 全关的那些:GitHub 看 `issue_dependencies_summary.blocked_by` 为 0,本地看 `Blocked by` 里的都 done。
6. **做完一张就关一张。** 关 issue(`gh issue close <号> --comment "<一句结果>"`)或改文件 `Status: done`,同时写一行进展;两个动作一起做,不攒。「全部 ticket 关闭」是 Task 验收段里的一条 `[我]` 项,全部关了才勾它。这一步 Matt 原版没有,是补的。

## 本地文件模板

```md
# <NN>: <标题>

**What to build:** 这张 ticket 让哪个端到端行为跑起来,用户视角,不是逐层实现清单。

**Blocked by:** 阻塞它的 ticket 编号/标题,或「None(可立刻开工)」。

**Status:** ready-for-agent

- [ ] 验收标准 1
- [ ] 验收标准 2
```

## GitHub issue 正文模板

```md
## Parent
#<spec 所属的 Task,若 spec 也发了 issue 就写它的号;否则删本节>

## What to build
这张 ticket 让哪个端到端行为跑起来,用户视角。

## Acceptance criteria
- [ ] 标准 1
- [ ] 标准 2

## Blocked by
- #<号>,或「None(可立刻开工)」
```

两种形式都不写具体文件路径与代码片段;原型产出的状态机 / schema / 类型形状例外,裁到只剩决策部分并注明来自原型。

## 不做

- 不建标签体系、不自动派发:每张 ticket 就是一份 WORKERS.md 的任务包,派谁、并行几个按那里定。
- 不关、不改父 issue 或 spec;Task 的收件走 harness.md。
