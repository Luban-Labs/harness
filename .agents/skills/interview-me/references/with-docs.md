# with docs:边采访边建领域模型

译自 mattpocock/skills 的 grill-with-docs(= grilling + domain-modeling)。这是**主动**的纪律:挑战术语、编边界场景、术语与决策一成型就当场写下。只是读 CONTEXT.md 取词不算,那是任何 skill 都该有的一行习惯。

## 文件结构

多数仓库只有一个 context:

```
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-event-sourced-orders.md
│       └── 0002-postgres-for-write-model.md
└── src/
```

根目录有 `CONTEXT-MAP.md` 就是多 context,map 指向每个 context 的位置(各自有 `CONTEXT.md` 与 `docs/adr/`,根 `docs/adr/` 放系统级决策)。

文件**懒创建**:有东西要写才建。没有 `CONTEXT.md`,第一个术语定下来时建;没有 `docs/adr/`,第一条 ADR 需要时建。

## 采访过程中

- **对着词汇表挑战。** owner 用的词与 `CONTEXT.md` 已有定义冲突,当场指出:「词汇表里 cancellation 是 X,你现在说的像 Y,是哪个?」
- **收紧模糊用词。** owner 用了含混或多义的词,提一个精确的规范词:「你说的 account 是 Customer 还是 User?这是两回事。」
- **拿具体场景压。** 讨论领域关系时编边界场景逼 owner 把概念之间的界线说清。
- **和代码对照。** owner 说某事怎么运作,去代码里核;矛盾就摆出来:「代码里取消的是整单,你刚说可以部分取消,哪个对?」
- **当场更新 CONTEXT.md。** 一个术语定下来就立刻写,不攒着。格式见 [context.md](../templates/context.md)。CONTEXT.md 只是词汇表,不放实现细节、不当 spec、不当草稿本。
- **ADR 只在三条同时成立时才提议:** 难逆转;无上下文会费解;真实权衡的结果。缺一条就不写。格式见 [adr.md](../templates/adr.md)。
