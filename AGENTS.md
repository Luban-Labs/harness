## 全项目硬规则

- 使用 python3 ≥3.9 标准库，保持零第三方依赖。
- hook 脚本遇到任何异常都放行，不输出，退出码为 0。

## 路由表

| 做什么 / 改到哪 | 读 |
| --- | --- |
| 开始做或收一个 Task | docs/rules/harness.md |
| 改动会改变已有的值、字段含义、规则、接口或判断(没建 Task 也算) | docs/rules/harness.md「改动的影响面」 |
| 新写或改一个判断(是不是同一个 X、把 X 归一成键) | docs/rules/core-judgments.md |
| 改 hook 脚本 | 先读 tests/，先跑 `python3 -m unittest discover -s tests -v` |
| 给一个项目装 harness | `python3 init.py --help` |
| 把一个 Trellis 项目迁到 harness | `python3 migrate_trellis.py --help` |
