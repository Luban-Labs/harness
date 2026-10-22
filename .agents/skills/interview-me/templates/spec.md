# Spec 模板

译自 mattpocock/skills 的 to-spec,加了 harness 的「验收」一节。八节全写;不写具体文件路径与代码片段,它们过时得太快。例外:原型产出的片段比散文更精确地表达了一个决策(状态机、reducer、schema、类型形状),就内联到对应决策下并注明来自原型;只留决策密集的部分,不放可运行 demo。

```md
Status: ready-for-agent

## Problem Statement(问题陈述)

用户视角下用户面对的问题。

## Solution(解法)

用户视角下的解法。

## 验收

每项一个勾选框并标执行者;Stop hook 按它判什么时候该结案。依赖自然发生的事就自己造一个场景,造不出来的写成 [你] 项。

- [ ] [我] <执行者当场能演示并自验的:做什么、看到什么>
- [ ] [你] <只有 owner 能做或要 owner 看的>

## User Stories(用户故事)

一个**长**的编号列表,格式:

1. As a <actor>, I want a <feature>, so that <benefit>

例:As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending

要极尽详尽,覆盖这个功能的方方面面。

## Implementation Decisions(实现决策)

已做出的实现决策,可包括:要建/改的模块、这些模块要改的接口、开发者给的技术澄清、架构决策、schema 变更、API 契约、具体交互。

## Testing Decisions(测试决策)

包括:什么算好测试(只测外部行为,不测实现细节)、哪些模块会被测、代码库里已有的同类测试作为先例。

## Out of Scope(不做)

本 spec 不覆盖的东西。

## Further Notes(补充)

其他说明。
```
