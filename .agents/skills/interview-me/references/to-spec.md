# to spec:把已聊的综合成 spec

译自 mattpocock/skills 的 to-spec。只在出口判为「大」(命中 docs/rules/harness.md「何时建 Task」)、或 owner 直接说「出 spec」时读。**不再采访**,只综合已经聊过的和你对代码库的理解。

## 做法

1. **先看仓库现状**(还没看的话)。全程用项目 `CONTEXT.md` 的词汇;要碰的区域有 ADR 就遵守。
2. **画出测试的 seam。** 优先已有的 seam;用能用的最高一层;要新开就开在最高处;全仓 seam 越少越好,理想只有一个。**把 seam 摆给 owner 确认是否符合预期。**
3. **按模板写 spec 并发布。** 模板见 [spec.md](../templates/spec.md)。发布位置:项目有 `docs/agents/issue-tracker.md` 就按它;没有就按本地 markdown 约定——`.scratch/<feature-slug>/spec.md`,目录不存在就建。发布后标 `ready-for-agent`(本地约定:文件顶部一行 `Status: ready-for-agent`,下一行 `建单: <命中哪条>`),不需要再走 triage。
4. **判过不过大,过大才切。** 命中任一即过大:Implementation Decisions 里要建或改的模块跨三层以上(如 schema、API、UI);最短验收演示要分几次会话才跑得完;有宽改造(一处机械改动波及全仓库)。过大 → 按 [to-tickets.md](./to-tickets.md) 切成 ticket 再开工;不过大 → 不切,直接开工。判定一行写在 spec 末尾「Further Notes」里,带命中的条件。
