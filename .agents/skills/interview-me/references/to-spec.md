# to spec:把已聊的综合成 spec

译自 mattpocock/skills 的 to-spec。出口判为「大」(命中 docs/rules/harness.md「何时建 Task」)、owner 直接说「出 spec」,或需求已经说得清、按 harness.md 直接建功能 spec 时读。**不再采访**,只综合已经聊过的和你对代码库的理解。记录 spec(bug、剩余项、小待办)不走本文件,生成骨架后直接填。

## 做法

1. **先看仓库现状**(还没看的话)。全程用项目 `CONTEXT.md` 的词汇;要碰的区域有 ADR 就遵守。
2. **画出测试的 seam。** 优先已有的 seam;用能用的最高一层;要新开就开在最高处;全仓 seam 越少越好,理想只有一个。**把 seam 摆给 owner 确认是否符合预期。**
3. **清点影响面。** 改动会改变已有事实时,先派只读代理按 docs/rules/harness.md「改动的影响面」查:交给它被改的事实和要搜的名字,让它把读它、拿它比较、照它执行的地方逐个列出,分引用、副本、绕外部;你的回忆只作补充。纯新增、没有读取方的跳过这步,「影响面」写「无」。
4. **生成骨架,按模板写 spec 并发布。** 项目有 `docs/agents/issue-tracker.md` 就按它发布;没有就在项目根运行 `python3 .claude/hooks/session_start.py --new-task <功能名> --kind 功能`,在生成的 `.scratch/<功能名>/spec.md` 里逐节填写,各节写法见 [spec.md](../templates/spec.md)。第 2 步确认过的 seam 写进「测试决策」;第 3 步的清单逐项写进「影响面」,每项定跟改、不受影响或已知差异,实现中发现新的使用方随时补。生成的首行就是 `ready-for-agent`,不需要再走 triage。
5. **判过不过大,过大才切。** 命中任一即过大:实现决策里要建或改的模块跨三层以上(如 schema、API、UI);最短验收演示要分几次会话才跑得完;有宽改造(一处机械改动波及全仓库)。过大 → 按 [to-tickets.md](./to-tickets.md) 切成 ticket 再开工;不过大 → 不切,直接开工。判定一行写进「实现决策」,带命中的条件。
