# CONTEXT.md 格式

译自 mattpocock/skills 的 CONTEXT-FORMAT。

## 结构

```md
# {Context 名}

{一两句:这个 context 是什么、为什么存在。}

## Language

**Order**:
{一两句描述这个术语}
_Avoid_: Purchase, transaction

**Invoice**:
交付后发给客户的付款请求。
_Avoid_: Bill, payment request

**Customer**:
下单的个人或组织。
_Avoid_: Client, buyer, account
```

## 规则

- **有立场。** 同一概念有多个词,选最好的一个,其余列在 `_Avoid_` 下。
- **定义收紧。** 最多一两句;定义它**是什么**,不写它做什么。
- **只收本项目 context 特有的术语。** 通用编程概念(超时、错误类型、工具模式)即使项目大量使用也不收。加词前先问:这是本 context 独有的概念,还是通用编程概念?只有前者算。
- **自然成簇时用子标题分组。** 全部属于一个内聚区域就平铺。

## 单 context 与多 context

**单 context(多数仓库):** 根目录一个 `CONTEXT.md`。

**多 context:** 根目录 `CONTEXT-MAP.md` 列出各 context 的位置与关系:

```md
# Context Map

## Contexts

- [Ordering](./src/ordering/CONTEXT.md): 接收并跟踪客户订单
- [Billing](./src/billing/CONTEXT.md): 生成发票、处理付款

## Relationships

- **Ordering → Fulfillment**: Ordering 发 `OrderPlaced` 事件,Fulfillment 消费它开始拣货
- **Ordering ↔ Billing**: 共享 `CustomerId` 与 `Money` 类型
```

判断规则:有 `CONTEXT-MAP.md` 就读它找 context;只有根 `CONTEXT.md` 就是单 context;都没有,第一个术语定下来时懒创建根 `CONTEXT.md`。多 context 时推断当前话题属于哪个;不清楚就问。
