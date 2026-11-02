# 总图

```text
需求 → 采访与 Task spec → 开工/看板 → 实现与验证 → Stop 检查 → 收件/归档
                          ↑                │
                          └── SessionStart ┘

项目安装/升级 ──→ 规则、模板、hook ──→ 上述 Task 流程
Trellis 迁移 ───→ 规则、模板、hook ──→ 上述 Task 流程
DSH 事件 ──────→ CC hook 桥接 ─────→ 上述看板与检查
```

| 块 | 职责 | 模块文档 | 职责表概念 |
| --- | --- | --- | --- |
| 采访与 Task | 澄清需求、生成 spec、认领与收件 | `.agents/skills/interview-me/SKILL.md`, `docs/rules/harness.md` | `docs/rules/core-judgments.md`「Task 目录」「类型」「认领」「待结案」「spec 的节」 |
| 开场看板 | 从项目与会话状态生成提示、概念清单 | `docs/rules/harness.md` | `docs/rules/core-judgments.md`「主工作树」「核心判断表条目」「本会话记录」 |
| Stop 检查 | 检查 Task、同类判断和职责表更新 | `docs/rules/harness.md` | `docs/rules/core-judgments.md`「本回合」「本回合编辑」「工作树代码范围」「项目代码目录」「代码里某个名字的定义」 |
| 安装与迁移 | 安装或迁移规则、模板、hook 与路由 | `docs/rules/harness.md` | `docs/rules/core-judgments.md`「hook 已登记」「Scope」 |
| DSH 桥接 | 按宿主事件运行受信任的 CC hook | `dsh/research_evidence.md` | `docs/rules/core-judgments.md`「CC 项目信任」「DSH 日志位置」 |
