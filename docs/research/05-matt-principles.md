# mattpocock/skills 的设计哲学与写法规范

调研范围:`/private/tmp/claude-501/-Users-sangba-Downloads-02-----------harness/c38a95e8-724a-458f-a564-59ac3a323ca8/scratchpad/mattskills`(版本 `1.2.3`,见 `package.json:3`)。所有结论只来自本次实际读到的文件,标注为 `path:line`。对比用的 Trellis 仓库在同一 scratchpad 下的 `trellis/`,第 7 节的引用同样落到行号。

阅读顺序建议:第 1 节(失败模型)→ 第 5 节(路由器)→ 第 7 节(与 Trellis 的取舍)是决策线;第 2、3 节是写法细则;第 4、6 节是佐证。

---

## 0. 一句话结论

Matt 的方案不是「一套流程框架」,而是**一组小到可以随时丢弃的技能 + 一个手写的路由器**,靠人在正确的时刻打出斜杠命令来推进周期。它把「周期状态」交给外部 issue tracker(可配置),把「项目语言」交给一个纯词汇表 `CONTEXT.md`,把「上下文该不该常驻」提升为一等设计变量(context load vs cognitive load)。这跟 Trellis「把状态、规范、记忆全部持久化进 `.trellis/` 并用 hook 每轮注入」是两条相反的路线,不能各取一半(详见第 7 节)。

README 自己就把三家点名了:「GSD、BMAD、Spec-Kit 试图通过**接管流程**来帮忙,但这样做拿走了你的控制权,并让流程里的 bug 难以解决」(`README.md:17`),因此这些技能被设计成「小、易改、可组合」(`README.md:19`)。

---

## 1. 作者认为 agent 失败的 4 类原因,及对应解法

全部来自 `README.md#Why These Skills Exist`(`README.md:84-182`)。每类都是「一句引文(工程经典)+ The Problem + The Fix」的固定结构。

### #1 The Agent Didn't Do What I Want(`README.md:88-103`)

- **问题**:最常见的失败模式是**错位(misalignment)**。「你以为开发者知道你要什么,然后看到成品,才发现他根本没听懂你」(`README.md:94`)。AI 时代同理,人与 agent 之间有沟通鸿沟(`README.md:96`)。
- **解法**:**grilling session** —— 让 agent 反过来盘问你(`README.md:96`)。
  - `/grill-me`:非代码场景(`README.md:100`)
  - `/grill-with-docs`:同样的盘问,但额外产出文档(`README.md:101`)
- 作者自称这是「我最受欢迎的技能」,并要求「**每次**你想做改动时都用」(`README.md:103`)。
- 底层原语是 `grilling`(model-invoked),它把决策空间建模成 **design tree**,按 **frontier**(所有前置已定的问题)一轮一轮问,而不是一次问一个(`skills/productivity/grilling/SKILL.md:6-8`);**事实由 agent 自己去查(可派子代理),决策必须交给人**(`skills/productivity/grilling/SKILL.md:26`);**frontier 空了才算结束,且必须等用户确认达成共识才能动手**(`skills/productivity/grilling/SKILL.md:27`)。

### #2 The Agent Is Way Too Verbose(`README.md:105-141`)

- **问题**:引 Eric Evans 的 DDD ubiquitous language(`README.md:107-109`)。agent 被丢进项目后要一边干活一边猜行话,于是「用 20 个词说 1 个词能说清的事」(`README.md:113`)。
- **解法**:**共享语言**,一份帮 agent 解码项目行话的文档(`README.md:115`)。示例对比:「a lesson inside a section of a course is made 'real'…」→「the materialization cascade」(`README.md:124-126`)。
- **载体**:`CONTEXT.md`;**入口**是 `/grill-with-docs`(`README.md:131`)。作者说「很难解释这有多强,这可能是本仓库里最酷的技术」(`README.md:133`)。
- 附带收益写在 TIP 里:变量/函数/文件命名一致、代码库更好导航、**agent 思考消耗的 token 更少**(`README.md:136-140`)。

### #3 The Code Doesn't Work(`README.md:142-158`)

- **问题**:引 Pragmatic Programmer「反馈的速率就是你的速度上限」(`README.md:144`)。就算对齐了,agent 还是可能产出垃圾 —— 根因是**反馈回路**缺失,agent 在盲飞(`README.md:150`)。
- **解法**:三件套反馈回路 —— **静态类型、浏览器访问、自动化测试**(`README.md:152`);自动化测试必须是 red-green-refactor(`README.md:154`)。
  - `/tdd`(`README.md:156`)
  - `/diagnosing-bugs`:把调试最佳实践包成一个**逐阶段设闸**的纪律循环(`README.md:158`)
- `tdd` 后来被改造成**纯 reference 技能**,连 Workflow 和 refactor 阶段都删了(见第 6 节)。

### #4 We Built A Ball Of Mud(`README.md:160-178`)

- **问题**:引 Kent Beck「每天投资于系统设计」和 Ousterhout「最好的模块是深的」(`README.md:162-168`)。agent 加速写码的同时**加速了软件熵**,代码库以前所未有的速度变复杂(`README.md:170`)。
- **解法**:「一种激进的新做法:**在意代码的设计**」(`README.md:172`),并声称「这已内建进这些技能的每一层」。
  - `/to-spec` 在出 spec 前先盘问你要动哪些模块(`README.md:176`)
  - `/improve-codebase-architecture` 巡检代码库找 deepening opportunities,建议**每隔几天跑一次**(`README.md:178`)
- 这里作者主动降预期:「它是**巡检,不是救援**:在真正老旧的代码库上它能找出真候选,但**不会替你把泥球解开**」(`README.md:178`)。

### Summary(`README.md:180-182`)

「软件工程基本功比以往更重要。这些技能是我把这些基本功浓缩成可重复实践的最好努力。」

**映射表(仅列 README 自己点名的解法;其余技能在 `README.md:184-231` 的 Reference 段)**

| 失败类别 | 根因判断 | 点名解法 |
| --- | --- | --- |
| #1 没做我想要的 | 人-agent 沟通鸿沟 | `grill-me`、`grill-with-docs`(底层 `grilling`) |
| #2 太啰嗦 | 缺共享语言 | `CONTEXT.md` + `grill-with-docs`(底层 `domain-modeling`) |
| #3 代码不工作 | 反馈回路缺失 | `tdd`、`diagnosing-bugs` |
| #4 泥球 | agent 加速了熵增 | `to-spec`、`improve-codebase-architecture`(底层 `codebase-design`) |

**注意这个失败模型的覆盖面**:4 类里没有一类是「跨会话状态丢失」或「任务追踪」。作者不认为「记不住上次做到哪」是首要失败模式 —— 这正是他与 Trellis 的分歧起点(Trellis 的开场白就是「AI 每个会话都从零开始 —— 不记得你的项目、约定、团队需求」,`trellis/README.md:11`)。

---

## 2. writing-for-agents:写 SKILL.md / AGENTS.md 的规范(逐条)

文件:`skills/productivity/writing-for-agents/SKILL.md`(81 行)+ `SKILL-MECHANICS.md`(22 行)。技能自身是 **model-invoked**,description 为「Writing documents for agents. Use when creating or editing skills, or modifying AGENTS.md or CLAUDE.md.」(`skills/productivity/writing-for-agents/SKILL.md:1-4`)。

适用面刻意做大:**任何 agent 会读的文档 —— 技能、`AGENTS.md`/`CLAUDE.md`、被 pointer 指到的 doc,打包方式不同但写法相同**(`SKILL.md:6`)。判据只有一句:「agent 会读它吗?」(`docs/productivity/writing-for-agents.md:13`)

### 2.1 长度:没有数字上限,只有三条可执行的删除判据

**这里要如实说明:整份规范没有给出任何「SKILL.md 不超过 N 行」的数字。** 长度是由删除规则倒推出来的:

- **Sprawl(蔓延)**:文档单纯太长,即使每行都活着、都唯一。「注意力在冗余里被稀释,而且每多一行就多一行要维持相关性」。解药是那把梯子:把 reference 下沉到 pointer 后面,并按 branch 或 sequence 拆分(`SKILL.md:43`)。
- **No-op 测试(逐句)**:一条模型默认就会遵守的指令,付出了 load 却什么都没说。「这个测试是**相对模型**的,不是相对读者的:两个人对某句是不是 no-op 有分歧,说明他们对默认行为有分歧,解决办法是**跑这份文档**,不是辩论。句子不通过时,**删整句,不要修词**」(`SKILL.md:81`)。
- **成品自检**:「文档越好越短,而且你会惊讶剩下的这么少」(`docs/productivity/writing-for-agents.md:63`)。

实测该仓库自己的分布(`find skills/{engineering,productivity} -name SKILL.md`,行数):最长 `teach` 140 行、`diagnosing-bugs` 138、`wayfinder` 128;最短 `grill-with-docs` 7、`grill-me` 7、`wait-what` 7、`research` 12、`resolving-merge-conflicts` 14、`implement` 15、`handoff` 16。**编排类可以长,执行类极短**。

### 2.2 结构:信息层级(information hierarchy)三级梯子

文档由两种内容构成:**steps**(有序动作)与 **reference**(按需查阅的定义/规则/事实),两者可自由混合(`SKILL.md:31`)。核心决策是每块内容放在梯子的哪一级:

1. **In-file step** —— 主层级:agent 要做什么,按顺序(`SKILL.md:33`)。
2. **In-file reference** —— 按需查阅。「通常是一个正当的扁平同级集合(一次 review 的每条规则都在同一级),这是合理安排,不是坏味道」(`SKILL.md:34`)。
3. **Disclosed reference** —— 推到独立文件,靠 context pointer 触发才加载;从同目录兄弟文件一直到任何文档都能指的完全外部引用(`SKILL.md:35`)。

- **张力就是全部决策**:「下沉太少顶部臃肿,下沉太多则藏起了 agent 真正需要的材料」(`SKILL.md:37`)。
- **Progressive disclosure** = 沿梯子往下移。「首先不是 token 优化,而是保护层级」。**最干净的拆分判据是 branch:每个分支都需要的就内联,只有部分分支会走到的就推到 pointer 后面**(`SKILL.md:39`)。
- **当文档含有 steps 时**,本该下沉却留在文内的 reference 会**埋掉 steps**,让「有没有注意到它们」变成抛硬币 —— 这是**方差杠杆**,不只是可读性问题(`SKILL.md:39`)。
- **Co-location(共置)**:梯子决定「下沉多深」,共置决定「落地后旁边放什么」。把一个概念的定义、规则、注意事项放在同一个标题下,读到一部分就把邻居一起带出来。判据:「文档应该读起来像是**为 agent 写的说明书**」(`SKILL.md:41`)。与 duplication 区分:重复是一个意思出现在两处,散落是一个意思被切碎在多处。

### 2.3 语气 / 措辞:leading words + 禁止否定式

- **Leading word(领头词)**:模型预训练里已有的紧凑概念(*lesson*、*fog of war*、*tracer bullets*),agent 在执行文档时用它思考。**只作为 token 反复出现,绝不写成句子**;它靠调用模型已有的先验,以最少 token 锚定一整片行为(`SKILL.md:63`)。
- **自造词可以,但成本高**:「自造词调不动任何先验:预训练词免费给你的东西,你要用定义 token 去买。**先找现成的词**」(`SKILL.md:63`)。
- **它锚定两次**:body 里锚定**执行**(每次这个词出现,agent 就伸向同一行为);pointer 里锚定**调用**(当同一个词同时活在你的 prompt、文档和代码库里,agent 更可靠地够到那份材料)(`SKILL.md:65`)。
- **主动去找重构机会**:「一个三元组在三个地方被展开写、一个 pointer 花一整句去指一个想法 —— 每一处都在求你把它坍缩成一个 token」。给的两个例子:「fast, deterministic, low-overhead」→ *tight*;「a loop you believe in」→ *red*(把模糊的门变成二值可观测状态)(`SKILL.md:67-72`)。
- **Negation(否定)是这条杠杆旁边的失败模式**:「用禁止来引导,会把被禁的行为拽进上下文,让它**更**可得,而不是更不可得。*别想大象*,于是满脑子都是大象;否定是个弱修饰词,会被强激活的概念冲垮,所以禁令有一半读起来像是在教它去做那件事。」**改写成正面表述**:直接说目标行为(「写一行的注释」),这样被禁的行为根本没被说出口。只有当你实在无法正面表述的硬护栏才配用禁令,**即便如此也要配一条正面目标**(`SKILL.md:74`)。

### 2.4 什么不能写(禁写清单)

| 禁写项 | 定义 / 判据 | 出处 |
| --- | --- | --- |
| **No-op** | 模型默认就会做的指令。逐句测:删掉它,行为变了吗?没变就删整句 | `SKILL.md:81` |
| **Duplication** | 同一个意思出现在一处以上;既费维护费 token,又**把这个意思在梯子上的显著度抬高到超过它真实的等级** | `SKILL.md:78` |
| **Cache(复述环境)** | `package.json` scripts、配置文件、目录结构、`--help` 输出**本身就是真相源**,复述它们的文档是「一次查询的缓存」,只有当查询很贵时才值这份 load。**缓存 agent 查不到的东西**(不成文约定、某个选择背后的理由、任何配置不会招认的坑),把「一个文件、一条命令」的查询留给环境,那里不会过期 | `SKILL.md:79` |
| **失去相关性的行 / sediment(沉积)** | 一行失去相关性有两种方式:从来就不作用于任务(纯说明,或本该下沉的分支),或随着行为/世界变化而过期。没有剪枝纪律的默认下场是沉积:「因为添加感觉安全、删除感觉危险,陈旧层层堆积,直到你必须打钻取芯才能找到还活着的东西」 | `SKILL.md:80` |
| **否定式指令** | 见 2.3 | `SKILL.md:74` |
| **解释模型已经知道的东西** | 「让 agent 给另一个 agent 写指令,它大部分字都花在解释模型已知的事。每一行都是 no-op」 | `docs/productivity/writing-for-agents.md:5` |
| **user-invoked 技能的 description 里写触发词列表** | user-invoked 的 description 是**给人看的**一行摘要,触发列表要剥掉 | `SKILL-MECHANICS.md:10`、`.agents/invocation.md:5` |
| **本仓库额外规矩:em-dash** | 「本仓库任何散文中都不许出现 em-dash(`SKILL.md`、docs、`README.md`、`CHANGELOG.md`、ADR、changeset、代码注释)。句子想用它时,改写成逗号、冒号、句号、括号或连词 —— **绝不做无脑字符替换**」 | `CLAUDE.md:25` |

配套的、写在别处但同源的禁写规则(周期文档相关):

- spec 与 ticket 里**不要写具体文件路径和代码片段**,它们过期极快;唯一例外是 prototype 产出的、比散文更精确地编码了决策的片段(状态机、reducer、schema、类型形状),且只留决策密集的部分(`skills/engineering/to-spec/SKILL.md:55-57`、`skills/engineering/to-tickets/SKILL.md:105`)。
- `CONTEXT.md` **完全不能有实现细节**,「不要把它当 spec、当草稿纸、当实现决策的仓库。它是词汇表,仅此而已」(`skills/engineering/domain-modeling/SKILL.md:64`);词条只收**本项目特有**的概念,通用编程概念(超时、错误类型、工具模式)即使项目大量使用也不收(`skills/engineering/domain-modeling/CONTEXT-FORMAT.md:29`)。
- 人面向的 docs 页**不写安装命令、不写作者名**(`.agents/writing-docs.md:19`、`.agents/writing-docs.md:75`)。

### 2.5 两种预算:context load vs cognitive load(整套规范的枢轴)

- **Context load**:常驻材料对 agent 窗口的成本 —— 一行 `AGENTS.md`、一个 skill description,任何每轮都在上下文里的东西,**无论是否触发都在花 token 和注意力**(`SKILL.md:24`)。
- **Cognitive load**:对**人**的成本 —— 有哪些文档、什么时候该伸手拿哪个。「**人就是索引**。这不是一个要最小化的成本:它是人类能动性的价格;在人的判断重要的地方花它,在不重要的地方去掉它」(`SKILL.md:25`)。
- 只靠 pointer 触达的材料以「pointer 自身那一行」的代价躲开了 context load;完全没有 pointer 的材料则整个骑在 cognitive load 上(`SKILL.md:27`)。
- 这条区分直接决定「这段该放 `CLAUDE.md` 还是别处」:「`CLAUDE.md` 无条件加载进每个会话;pointer 后面的材料在触发前只花 pointer 那一行。**十次里只适用一次的东西,另外九次都在白付 context load**」(`docs/productivity/writing-for-agents.md:50`)。

### 2.6 Context pointer 的写法(三条)

**Context pointer** = 上下文里持有的一个引用,它命名一份不在上下文里的材料,并**编码了够到它的条件**。skill 的 description 是一个 pointer,`AGENTS.md` 里指向某文档的一行是同一种东西。**决定 agent 何时以及多可靠地够到材料的是 pointer 的措辞,不是它的目标**;「一份必需的材料配一个措辞疲软的 pointer,是一个方差 bug:**先磨锐措辞,磨不动才内联材料**」(`SKILL.md:12`)。

pointer 做两件事:说明材料是什么 + 列出应触发它的 **branches**。因为常驻 pointer 每一个词每轮都在花钱,它比正文要被更狠地剪(`SKILL.md:14`):

1. **Front-load the leading word** —— pointer 正是它干触发活的地方(`SKILL.md:16`)。
2. **一个 branch 一个 trigger** —— 用同义词把同一个分支改名写两遍,是「一个分支写了两次」,合并掉,只留真正不同的分支(`SKILL.md:17`)。
3. **砍掉正文已经承载的身份信息**(`SKILL.md:18`)。

### 2.7 Steps 与 completion criteria(防「提前收工」)

每个 step 都以一个 **completion criterion** 结束,两个属性使它成为杠杆(`SKILL.md:47-52`):

- **Clarity(清晰度)**:agent 能不能分辨「做完了」和「没做完」?模糊的界限(「达成了理解」)招来 **premature completion** —— 在真正完成前就结束这一步,注意力滑向「快点做完」。**后面还看得见的步骤(post-completion steps)提供了那股拉力,判据的清晰度就是阻力。** 防守顺序:**先磨锐界限**(局部、便宜);只有当它不可约地模糊**且**你真的观察到了那种赶工,才拆分序列把后续步骤藏起来。「**藏只在真正的上下文边界上才有效**(一次 hand-off 或一次 subagent 派发;内联调用会把后续步骤留在上下文里,什么都没清掉)」(`SKILL.md:49`)。
- **Demand(要求量)**:判据要求多少。「every modified model accounted for」逼出彻底的工作,「produce a change list」不会。Demand 驱动 **legwork**(agent 在工作内部做的挖掘,潜伏在措辞里而不是写成单独一步),而且**不绑定 step**:「every rule applied」约束一堆扁平 reference,就像「every step done」约束一个序列 —— 这就是纯 reference 文档也能带穷尽度门槛的原因(`SKILL.md:50`)。
- **最强的判据同时是可核查的和穷尽的**(`SKILL.md:52`)。

### 2.8 何时拆分文档

拆分要花掉两种 load 之一,所以只有值回票价才拆(`SKILL.md:56-59`):

- **按 sequence 拆**:当后续步骤诱使 agent 赶完眼前这步时,把一串 steps 切开。反过来也要警惕:**合并序列会把每一步的后续步骤暴露给它,招来提前收工**(`SKILL.md:58`)。
- **按 invocation 拆**:见 `SKILL-MECHANICS.md`(`SKILL.md:59`)。

### 2.9 技能特有机制(`SKILL-MECHANICS.md`)

- **Model-invoked**:保留 `description`,agent 可自主触发,**其他技能也能够到它**。「你依然可以打它的名字:model-invocation 永远**包含**用户可达;description 只会**增加** agent 的发现能力,从不移除人的」。description 是这个技能的顶层 context pointer,被强制常驻:**用永久 context load 换可发现性**。内容全是 reference 的 model-invoked 技能还是「共享 reference 的一个家」:别的技能能调它,所以多个技能都需要的 reference 只存在一处。做法:不写 `disable-model-invocation`,写一个带触发分支的 model-facing description(pointer 规则全部适用)(`SKILL-MECHANICS.md:9`)。
- **User-invoked**:把 description 从 agent 的可达范围里剥掉,**只有人打名字能调,别的技能一律调不到**。**零 context load,但花 cognitive load**:你就是那个必须记得它存在的索引。做法:`disable-model-invocation: true`;description 变成人面向的一行摘要,触发列表剥掉(`SKILL-MECHANICS.md:10`)。
- **选择规则**:「只有当 agent 必须自己够到它、或另一个技能必须够到它时,才选 model-invocation。如果它只会被手打触发,就做成 user-invoked,一分 context load 都不付」(`SKILL-MECHANICS.md:12`)。
- **两个 user-invoked 技能都需要的共享 reference,不能住在其中任何一个里面**(都没有 description,谁也调不动谁),要推到 skill 系统之外的普通文件,做成任何技能都能指的外部 reference(`SKILL-MECHANICS.md:14`)。
- **按 invocation 拆分**:当你有一个**应该独立触发它的 leading word**(一个你在 prompt 里真的会用的触发词),或另一个技能必须够到它时,才拆出一个 model-invoked 技能。「你要为这个新的常驻 description 付 context load,所以那份独立可达性得配得上」(`SKILL-MECHANICS.md:18`)。
- **Router skill**:当 user-invoked 技能多到你记不住,那堆积起来的 cognitive load 由**路由技能**治疗 —— 一个 user-invoked 技能点名其他技能以及何时该用哪个,人只需要记住一个。「**它只能提示,永远不能点火**:user-invoked 技能没有 description,除了人没有任何东西能够到它们」(`SKILL-MECHANICS.md:20-22`)。
- **跨技能依赖的写法**(在 `.agents/invocation.md`,不在技能里):依赖写成显式的「调用 Skill 工具」指令(`Call the Skill tool with "grilling"`),**不是**深层 `../other-skill/FILE.md` 交叉引用,也**不是**丢一个 `/skill` 让模型自己领会 —— 「点名这个工具才是让它开火的原因……而且去掉前导 `/` 让它保持 harness 中立」(`.agents/invocation.md:16`)。Skill 工具一次只吃一个技能名,需要两个就写两次调用(`.agents/invocation.md:20`)。**这套约定只在被点名的技能是 model-invoked 时成立**;当某步的前置是一个 user-invoked 技能(如 `setup-matt-pocock-skills`),要写成「告诉用户去运行 `/setup-matt-pocock-skills`」,绝不写成 Skill 工具调用(`.agents/invocation.md:22`)。这条不变量被破坏过,修复记录在 `.changeset/user-invoked-skill-invocation.md:5-9`(六处调用点,原因是新增段落没和八行之上的不变量对账)。

---

## 3. 这个仓库自己的 AGENTS.md / CLAUDE.md / CONTEXT.md

### 3.1 有多长、写了什么

| 文件 | 长度 | 性质 |
| --- | --- | --- |
| `AGENTS.md` | 符号链接 → `CLAUDE.md`(`ls -la` 显示 `AGENTS.md -> CLAUDE.md`) | 加这个 symlink 是为了让 Codex 读到同一份仓库指令(`CHANGELOG.md:36`) |
| `CLAUDE.md` | **25 行 / 3737 字节**(其中 9 行是空行,实际 12 个段落) | 纯 reference,全是「本仓库的不变量 + 指向 `.agents/*.md` 的 pointer」 |
| `CONTEXT.md` | **30 行 / 1768 字节** | 纯词汇表,4 个词条 + 关系 + 已解决的歧义 |

**`CLAUDE.md` 的 12 段内容**(逐段):

1. bucket 分类法:`engineering/`(日常代码)、`productivity/`(日常非代码)、`misc/`(留着但少用,不推广)、`in-progress/`(beta,故意公开,要反馈,不进 plugin)、`deprecated/`(不再使用)(`CLAUDE.md:1-8`)
2. **promoted 桶的不变量**:`engineering/` 或 `productivity/` 里的每个技能必须在顶层 `README.md` 有引用,并在 `.claude-plugin/plugin.json` 的 `skills` 数组有条目;其余三个桶两处都不许出现(`CLAUDE.md:9`)
3. 安装命令逐字从 `.agents/install-block.md` 复制;改完 manifest 跑 `claude plugin validate . --strict`(`CLAUDE.md:11`)
4. README 每个技能条目必须把名字链到它的 `SKILL.md`(`CLAUDE.md:13`)
5. 每个 bucket 有自己的 `README.md`,promoted 桶按 User-invoked / Model-invoked 分组,非 promoted 桶用平铺列表(`CLAUDE.md:15`)
6. **docs 页规则**:promoted 桶的技能在 `docs/<bucket>/<skill-name>.md` 有人面向页面,发布 URL 恒为 `https://aihero.dev/skills-<skill-name>`(**docs 路径只是仓库组织,不是 URL 结构**);新增/改名/改行为时按 `.agents/writing-docs.md` 重新同步;成品页带四个 section:What it does / When to reach for it / Common questions / It's working if(`CLAUDE.md:17`)
7. 每个 `SKILL.md` 非此即彼:user-invoked(`disable-model-invocation: true` + `agents/openai.yaml` 里 `policy.allow_implicit_invocation: false`)或 model-invoked,细则在 `.agents/invocation.md`(`CLAUDE.md:19`)
8. **路由器维护义务**:`ask-matt` 映射每个 user-reachable 技能及其关系;「触发 docs 页重新同步的同一件事也触发它:每当你新增、改名、移除某个 user-reachable 技能,或改了它在流程里的位置,就重读 `ask-matt` 的 `SKILL.md` 并更新,让地图保持准确 —— **一个它从没提过的新技能,或一个它还在路由过去的陈旧技能,就是一个在说谎的路由器**」(`CLAUDE.md:21`)
9. `scripts/link-skills.sh` 把 `deprecated/` 与 `misc/` 之外的技能软链进本机 harness 目录(`CLAUDE.md:23`)
10. em-dash 禁令(见 2.4)(`CLAUDE.md:25`)

**`CONTEXT.md` 的内容**:标题 + 一句话项目描述(`CONTEXT.md:1-3`);`## Language` 四个词条,每条带 `_Avoid_` 同义词黑名单 —— **Issue tracker**、**Issue**、**Decision ticket**、**Triage role**(`CONTEXT.md:5-19`);`## Relationships` 三条(`CONTEXT.md:21-25`);`## Flagged ambiguities` 记录「backlog」曾同时指工具和工作量、现已裁定为 **Issue tracker**(`CONTEXT.md:27-30`)。

### 3.2 它遵守自己的规范吗?

**遵守的部分(已核实)**:

- **em-dash 禁令,在散文里执行到位**:`README.md`、`CLAUDE.md`、`CONTEXT.md` 各 0 个;`skills/**/SKILL.md` 全部 0 个(`grep -rl '—' skills --include='SKILL.md'` 返回 0 个文件);`docs/` 全部 0 个。
- **progressive disclosure 用在自己身上**:`CLAUDE.md` 只有 25 行,把安装块、invocation 细则、docs 页模板全部推到 `.agents/install-block.md`、`.agents/invocation.md`、`.agents/writing-docs.md` 后面 —— 正是它自己 `SKILL.md:35` 的第三级。`.agents/writing-docs.md` 一个文件 96 行,内容量是 `CLAUDE.md` 的四倍,但只在真要写 docs 页时才被读。
- **single source of truth**:invocation 的完整定义只在 `.agents/invocation.md`,`CLAUDE.md:19` 只留一行 pointer;docs 页模板只在 `.agents/writing-docs.md`。
- **completion criteria 带穷尽度要求**:`.agents/writing-docs.md:81-96` 的「Done when」是 15 条可逐条核查的清单(「每个链接都是绝对链接,且每一条都能解析」),符合 `SKILL.md:52` 的「既可核查又穷尽」。
- **CONTEXT.md 符合自己的 CONTEXT-FORMAT**:词条格式 `**Term**: 定义 + _Avoid_`(`CONTEXT-FORMAT.md:12-22`)、只收项目特有概念(`CONTEXT-FORMAT.md:29`)、无任何实现细节(`domain-modeling/SKILL.md:64`)。
- **技能的 invocation 选择自洽**:`ask-matt`、`grill-me`、`grill-with-docs`、`to-spec`、`to-tickets`、`implement`、`triage`、`handoff`、`wayfinder`、`improve-codebase-architecture`、`setup-matt-pocock-skills` 都是 `disable-model-invocation: true`(编排类);`grilling`、`domain-modeling`、`codebase-design`、`writing-for-agents`、`tdd`、`prototype`、`research`、`wizard`、`code-review` 是 model-invoked(可复用 reference / 需要 agent 自主够到)。这与 `SKILL-MECHANICS.md:12` 的选择规则一致。

**不遵守 / 存疑的部分(已核实文本,判断留给 owner)**:

1. **`CHANGELOG.md` 有 104 个 em-dash**,而 `CLAUDE.md:25` 明确把 `CHANGELOG.md` 列进禁令范围。待发布的 `.changeset/remove-em-dashes-repo-wide.md:5` 描述的清扫范围是「docs、`SKILL.md`、ADR、`README.md`、scripts、JSON/YAML metadata」—— **不含 CHANGELOG**。也就是说规则写得比实际执行的清扫更宽,规则与执行之间有缺口。
2. **本仓库自己的 ADR 放在 `.agents/adr/`,不是自己技能规定的 `docs/adr/`**(`skills/engineering/domain-modeling/ADR-FORMAT.md:3`:「ADRs live in `docs/adr/`」;`domain-modeling/SKILL.md:16-22` 的目录图同此)。实测 `docs/adr` 不存在,`.agents/adr/` 有两份 ADR。可以解释为「本仓库是技能仓库不是应用仓库」,但文本层面确实不一致。
3. **`CONTEXT.md` 多了一个模板里没有的 `## Flagged ambiguities` 段**(`CONTEXT-FORMAT.md:5-23` 的结构只有标题 + 描述 + `## Language`)。这是有用的扩展,但技能自己的格式文件没有它。
4. **`CONTEXT.md:13` 把「ticket」列进 Issue 的 `_Avoid_`(只允许引用外部系统或指 Decision ticket 时用),但 `to-tickets` 技能通篇把普通实现切片叫 ticket**(`skills/engineering/to-tickets/SKILL.md:9`「Break a plan, spec, or conversation into a set of **tickets**」、`:27`、`:38`)。同一个 CHANGELOG 条目里作者承认过这个张力,并靠给 wayfinder 的单位起名 **Decision ticket** 来局部化解(`CHANGELOG.md:84`),但普通 ticket 的用法仍与 `_Avoid_` 冲突。

**对 owner 的直接含义**:这套规范**自己执行得住**的部分,恰好是「有唯一入口文件、有可核查清单、有 grep 得出来的硬规则」的部分(em-dash 在散文里、桶不变量、invocation 二选一);**没执行住**的部分是「规则写在一个地方,但落地在另一个不被读的地方」(CHANGELOG、ADR 目录)。轻量 harness 自建时,规则要么可 grep/可脚本核验,要么就别写进 CLAUDE.md。

---

## 4. deep modules 与 domain model 在周期管理里的位置

结论先说:**两者都不是「开工前一次性做完」的产物,而是持续维护的、被别的周期步骤顺带驱动的层。** `ask-matt` 把它们单独归为一节,标题就叫 **「Vocabulary underneath」——「两个跑在其他技能*底下*的 model-invoked reference,各自是其词汇的唯一真相源」**(`skills/engineering/ask-matt/SKILL.md:54-59`)。

### 4.1 domain model / CONTEXT.md:持续维护,惰性创建,三处触发

**它不是一个阶段,是一条纪律。** `domain-modeling` 明确区分主动与被动:「仅仅*读* `CONTEXT.md` 取词汇**不是**这个技能:那是任何技能都能做的一行习惯。这个技能是给你在**改**模型的时候用的,不是消费它的时候」(`skills/engineering/domain-modeling/SKILL.md:8`,同一区分复述在 `.agents/invocation.md:24-26`)。

- **惰性创建**:「只在你有东西可写时才建文件。如果没有 `CONTEXT.md`,在**第一个术语被确定时**创建它。如果没有 `docs/adr/`,在**第一个 ADR 需要时**创建它」(`domain-modeling/SKILL.md:40`)。setup 技能同步这条:这些文件不存在时「**静默继续**。不要指出它们缺失;不要建议提前创建」(`setup-matt-pocock-skills/domain.md:11`)。
- **就地更新,不攒批**:「术语被确定时,**当场**更新 `CONTEXT.md`。不要攒起来:发生一个记一个」(`domain-modeling/SKILL.md:62`)。
- **四种会话中的主动动作**:与词汇表冲突的术语当场叫停(`:46`)、把模糊/超载的词收敛到一个规范词(`:48`)、用具体场景压测领域关系的边界(`:54`)、与代码交叉验证并把矛盾摆出来(`:58`)。
- **ADR 的门槛很高**:三条**全部**满足才提议 —— 难以逆转、无上下文会令人费解、**是真实权衡的结果**;缺一条就跳过(`domain-modeling/SKILL.md:66-72`,展开在 `ADR-FORMAT.md:29-47`)。ADR 本身可以只有一段话:「价值在于记录**有过**一个决策以及**为什么**,不在于填满 section」(`ADR-FORMAT.md:15`)。

**谁触发:**

| 触发路径 | 位置 | 时机 |
| --- | --- | --- |
| **自动**(model-invoked description) | 「Use when discussing codebase terminology, writing or editing a CONTEXT.md, or recording or editing an ADR」(`domain-modeling/SKILL.md:3`) | 任何会话里只要在讨论术语就可能开火 |
| **开工澄清阶段**:`grill-with-docs` | 整个技能只有一行正文:`Call the Skill tool twice, for "grilling" and "domain-modeling".`(`skills/engineering/grill-with-docs/SKILL.md:7`) | 主流程第 1 步(`ask-matt/SKILL.md:17`) |
| **架构巡检阶段**:`improve-codebase-architecture` | 「Side effects happen inline as decisions crystallize; call the Skill tool with "domain-modeling" to keep the domain model current as you go」(`improve-codebase-architecture/SKILL.md:66-70`) | 每隔几天的巡检 |
| **被动消费**:所有 spec/ticket/巡检输出 | `to-spec` 步骤 1、`to-tickets` 步骤 2 都要求「用项目词汇表的词写」(`to-spec/SKILL.md:13`、`to-tickets/SKILL.md:21`) | 每次产出 |

注意最新一次 description 调整的方向:`.changeset/domain-modeling-trigger-context-adr.md:5` 把触发条件**放宽**成「讨论代码库术语 / 写或改 CONTEXT.md / 写或改 ADR」,并**删掉**了「另一个技能需要维护领域模型」这个 caveat,理由是「那是调用方技能自己该显式说的事,不是这个 description 的事」。这是 2.6 节 pointer 规则的实践:一个 branch 一个 trigger,不写别人该写的身份信息。

### 4.2 deep modules / codebase-design:纯词汇层 + 周期性巡检

**`codebase-design` 本身没有任何流程步骤,它是词汇表和原则的集合。** 「Design **deep modules**:大量行为藏在小接口后面,放在一个干净的 seam 上,通过那个接口可测。**在任何设计或重构代码的地方使用这套语言和这些原则**」(`skills/engineering/codebase-design/SKILL.md:8`)。它对术语的强制程度很高:「精确使用这些词:不要替换成 "component"、"service"、"API" 或 "boundary"。**语言一致就是全部要点**」(`:12`)。

七个词:Module / Interface / Implementation / Depth / Seam / Adapter / Leverage / Locality(`codebase-design/SKILL.md:14-28`),四条原则里最可操作的两条:

- **The deletion test**:「想象删掉这个模块。如果复杂度消失了,它就是个 pass-through。如果复杂度在 N 个调用点重新出现,它就在挣它的饭钱」(`:63`)。
- **一个 adapter 意味着假想的 seam,两个 adapter 才意味着真实的 seam**(`:65`)。

**它在周期里的三个消费点**(全部是别的技能来调它,它自己不发起):

1. **拆任务前**:`to-spec` 步骤 2 要求「先勾勒你要在哪些 seam 上测这个功能。**已有 seam 优先于新 seam。用尽可能高的 seam**。跨代码库的 seam 越少越好,理想数量是 1」,并且**要跟用户确认这些 seam 符合他的预期**(`to-spec/SKILL.md:15-17`)。
2. **写代码时**:`tdd` 用它的接口设计指导(`ask-matt/SKILL.md:59`;`CHANGELOG.md:97-99` 记录 `tdd` 的内联 `deep-modules.md`/`interface-design.md` 被删,改为依赖共享技能)。
3. **周期性巡检**:`improve-codebase-architecture` 第一步就 `Call the Skill tool with "codebase-design"` 取词汇,并要求「**在每条建议里精确使用这些词**」(`improve-codebase-architecture/SKILL.md:13`)。

**巡检的节奏与范围**:README 建议「每隔几天在你的代码库上跑一次」(`README.md:178`);`ask-matt` 的定位是「**有空的时候**就跑,让代码库保持对 agent 友好」(`ask-matt/SKILL.md:52`)。范围有 YAGNI 闸:「**先定范围再扫描**……如果用户指了方向就照做;否则回溯一段 commit 历史(`git log --oneline`)找热点,让那些路径先吸引注意力」(`improve-codebase-architecture/SKILL.md:20-23`)。理由写在 CHANGELOG:「没人碰的代码里的 deepening opportunity 是一个你永远兑现不了的重构」(`CHANGELOG.md:94`)。

**巡检的产物不是重构,是「一个想法」**:它输出一份 HTML 报告(写到系统临时目录,**不落进仓库**,`improve-codebase-architecture/SKILL.md:39`),然后问用户选哪个;选中后进 grilling 循环。`ask-matt` 说得最清楚:「它浮出 deepening opportunities;**选一个就*生成一个 idea***,你可以把它带进主流程的 `/grill-with-docs`」(`ask-matt/SKILL.md:52`)。

### 4.3 在周期链上的位置(汇总)

```
开工/澄清 ──► grill-with-docs ──► [grilling + domain-modeling 同时开跑]
                                        │
                                        └─► CONTEXT.md / ADR 就地增量更新(惰性建文件)
拆任务 ────► to-spec(先定 seam,要人确认)──► to-tickets(tracer bullet + blocking edges)
实现 ──────► implement ──(内部驱动)──► tdd(在预先约定的 seam 上)
验证/审查 ─► code-review(Standards + Spec 两轴,并行子代理)
收尾/续工 ─► phase boundary 五选一(continue / clear / handoff / subagent / compact)
持续(与周期并行,不在链上)
          ├─ domain-modeling:任何术语讨论时自动开火
          └─ improve-codebase-architecture:每隔几天人工发起,产出的是「新 idea」而非重构
```

**结论明确回答问题**:两者都是**持续维护**,不是开工前做完。domain model 由 **agent 自动触发**(model-invoked description)+ **开工澄清阶段的 grill-with-docs 强制驱动**;deep modules 的**词汇层**由其他技能自动拉入,**巡检层**由**人**周期性发起(每隔几天),且巡检产出回流到周期起点而不是直接改代码。

---

## 5. ask-matt 作为路由器:它怎么决定,以及对「轻量 harness 只放一个入口」的启发

### 5.1 它是什么

- **user-invoked、零 context load**:`disable-model-invocation: true`(`skills/engineering/ask-matt/SKILL.md:1-5`)。
- 开场白就是它的存在理由:「**You don't remember every skill, so ask.**」(`ask-matt/SKILL.md:9`)—— 直接对应 `SKILL-MECHANICS.md:20-22` 说的「路由技能治疗堆积的 cognitive load」。
- **它只推荐、不执行**:「它推荐然后停下。它不盘问、不写 spec、不打开文件、不点燃它刚点名的技能;你拿到的是**下一个该敲的东西**,然后你去敲」(`docs/engineering/ask-matt.md:5`)。机制上也做不到点火:被它点名的都是 user-invoked,没有 description(`SKILL-MECHANICS.md:22`)。
- **它是手写地图,不是扫描结果**:「它是这个仓库里技能的一份**手写地图**,而不是对你已安装内容的扫描,所以它不会路由到你自己的技能或别人的技能」(`docs/engineering/ask-matt.md:5`)。

### 5.2 它怎么决定该用哪个技能

**第一层:按「你处在什么情境」组织,而不是按「技能列表」组织。** 它引入的领头词是 **flow** ——「一条穿过多个技能的**路径**」(`ask-matt/SKILL.md:11`),六个分区:

| 分区 | 内容 | 出处 |
| --- | --- | --- |
| **The main flow: idea → ship** | 3 步 + 2 个分支 | `ask-matt/SKILL.md:13-32` |
| **On-ramps** | 产生工作的起始情境,随后并入主流程 | `:34-46` |
| **Codebase health** | 非功能工作,纯保养 | `:48-52` |
| **Vocabulary underneath** | 跑在下面的两个词汇 reference | `:54-59` |
| **Phase boundaries** | 会话内的阶段边界怎么处理 | `:61-71` |
| **Standalone / Precondition** | 完全在流程之外的 / 首次必跑的 | `:73-89` |

**第二层:每个岔路口都是一个二值的、可当场观察的测试,不是「看情况」。** 这是最值得抄的部分:

- `grill-me` vs `grill-with-docs` → **你是不是在一个工作目录里**。「Start here whenever you are **working in a working directory**: it's stateful」(`:17`);不在工作目录就用 `grill-me`(`:77`)。作者还加了一句消歧:在工作目录里 `grill-with-docs` **严格更优**,因为跑同一个 interview 还留下纸面痕迹(`:17`、`:77`)。
- 走不走 prototype 岔路 → **这个问题需不需要一个可运行的答案**(状态、业务逻辑、必须眼见为实的 UI)(`:18`)。
- 走不走 spec+tickets → **这是不是一个多会话的构建**。是 → `to-spec` → `to-tickets` → 每个 ticket 一次 `implement` 并在之间 `/clear`;否 → 直接在当前窗口 `implement`(`:22-24`)。
- `grill-with-docs` vs `wayfinder` → **这个 idea 能不能装进一个会话**。「Where `grill-with-docs` sharpens an idea you can hold in one session, wayfinder is for the idea you can't」(`:44`)。
- 该不该 triage → **这个 issue 是不是你自己创建的**。「Triage 只针对**你没创建的** issue……`to-tickets` 产出的 ticket 已经是 agent-ready 的,所以**不要 triage 它们**」(`:40`)。
- 阶段边界五选一 → 一棵**有序**的树,「**第一个 yes 获胜**」(`PHASE-BOUNDARIES.md:19`),顺序是 Continue → `/clear` → `/handoff` → Subagent → `/compact`。

**第三层:路由器不仅给「用哪个」,还给「不要用哪个」和「用错的后果」。** 例如:wayfinder「更慢更密,所以只留给正好那种情况,绝不用于一个范围清楚的 feature」(`:44`);wayfinder 地图清晰后「**它交棒,它不建造**:并入主流程的 `to-spec`……把地图直接灌进 `implement` 会跳过那次坍缩、把链接细节扔掉」(`:46`);`/compact` 是「**默认项,不是第一反应**」,放在树的底部(`:69`、`PHASE-BOUNDARIES.md:40`);`/handoff` 被明确说成曾经「被过度推销」,它只在**新 harness / 新目录 / 交给同事 / 阶段中途分叉侧任务**四种情况下需要,买到的东西叫 **portability**(`:67`、`PHASE-BOUNDARIES.md:27-34`、`CHANGELOG.md:102`)。

**第四层:它同时管上下文卫生。** 「把第 1-3 步保持在**一个不中断的上下文窗口**里(在 `to-tickets` 之前不要 compact 或 clear),这样 grilling、spec 和 tickets 都建立在同一段思考上。之后每次 `implement` 从头开始,从 ticket 出发工作」(`:30`);上限是 **smart zone**(SOTA 模型约 150k token),「如果一个会话在 `to-tickets` 之前逼近它,**不要在退化状态下硬撑**;在最近的阶段边界 `/compact` 然后继续」(`:32`)。

**第五层:维护义务被写成硬规则。** 见 3.1 第 8 条:「一个它从没提过的新技能,或一个它还在路由过去的陈旧技能,**就是一个在说谎的路由器**」(`CLAUDE.md:21`)。这条规则是在 `ask-matt` 第一次被发现漏了五个技能之后加的(`CHANGELOG.md:161`),之后又执行过一次大修(`CHANGELOG.md:98-113`)。

### 5.3 对「轻量 harness 只放一个入口」的启发(可直接抄的 6 条)

1. **单入口的成本模型是明确的,不是感觉**:一个 user-invoked 入口 = **零 context load + 全部 cognitive load 集中到一个点**。这是路由器唯一的正当理由(`SKILL-MECHANICS.md:20-22`)。如果 owner 的 harness 只放一个入口,那个入口**必须是 user-invoked**,否则它的 description 会每轮都在收税。
2. **入口只推荐、不执行**。`ask-matt` 推荐完就停(`docs/engineering/ask-matt.md:5`)。入口一旦开始干活,它就同时承担了路由和执行两种 completion criteria,会触发 2.7 说的提前收工。
3. **按情境分区,不按技能字母序**。用户来的时候手里拿的是「我卡在哪」,不是「我要哪个命令」。`ask-matt` 的六分区(主流程 / on-ramp / 保养 / 词汇层 / 阶段边界 / 独立)可以原样借。
4. **每个岔路口给一个二值可观测的测试**,不要给「视情况而定」。「在不在工作目录」「能不能装进一个会话」「这 issue 是不是你自己建的」这三个测试的质量,决定了路由器有没有用。docs 页也把这条抽出来当卖点:「两个看起来可互换的技能 → 它们之间的界线,而且通常是**一个具体测试**而不是品味问题」(`docs/engineering/ask-matt.md:15`)。
5. **入口必须带反用法**(什么时候别用它、用错会失去什么)。`ask-matt` 里三处最长的段落都是反用法(wayfinder 过度使用、handoff 被过度推销、compact 当第一反应)。
6. **给入口配一条会失效的维护不变量**:「路由器说谎」这个说法之所以有效,是因为它把「文档过期」重新表述成「**它在骗人**」,提高了不更新的心理成本,而且触发时机明确(新增/改名/移除/改流程位置)。owner 自建时要能回答:**谁在什么事件上重读入口文件**。

一个必须继承的**局限**:`ask-matt` 是手写地图,不扫描已安装技能(`docs/engineering/ask-matt.md:5`)。轻量 harness 如果技能会经常增减,这个入口就是一个持续的人工负债 —— 要么接受它(用不变量兜底),要么让入口从目录结构生成(但那样就会失去「按情境分区 + 二值测试 + 反用法」这三样手写才有的东西)。这是个真实取舍,不是可以两全的。

---

## 6. CHANGELOG 最近 30 条看「重量」态度

统计口径:`CHANGELOG.md` 里以 `- [` 开头的条目,自顶向下第 1 到第 30 条,覆盖 `CHANGELOG.md:7` 到 `CHANGELOG.md:212`,即 1.2.3 → 1.2.2 → 1.2.0 → 1.1.0(含其 Minor 段与首条 Patch)。

### 6.1 在变重的

| 对象 | 变化 | 出处 |
| --- | --- | --- |
| **`ask-matt`(路由器)** | 两次扩容。第一次补上 5 个漏掉的技能并新增「Vocabulary underneath」节;第二次把 2 条「Crossing sessions」换成五选一决策树,并**拆出 `PHASE-BOUNDARIES.md`** | `CHANGELOG.md:161`、`CHANGELOG.md:98-113` |
| **`wayfinder`** | 从 `in-progress/` 毕业进 `engineering/`,同时被重构:改名(decision-mapping → wayfinder)、引入 `## Destination`、地图从本地 md 搬上 issue tracker、native blocking、HITL/AFK 分类、第四种 `task` ticket 类型。当前 128 行,是最重的技能之一 | `CHANGELOG.md:191-206` |
| **`triage`** | 扩展到外部 PR:「一个 PR 就是一个带代码的 issue」,同一套 roles / states / 状态机 | `CHANGELOG.md:213` |
| **`to-issues`(后并入 to-tickets)** | 拆成 Process + Reference 两段,并新增 **wide refactor / blast radius / expand-contract** 整块 | `CHANGELOG.md:179` |
| **`writing-for-agents`** | 适用范围扩大(从「写技能」到「写任何 agent 读的文档」),新增 `cache` 概念;但**同时**把 skill-only 机制拆出去 | `CHANGELOG.md:88-92` |
| **`grilling`** | 从「一次一问」改成 round-by-round frontier(13 个问题从 13 轮压到约 3 轮),事实类问题派后台子代理 | `CHANGELOG.md:126-130` |
| **`diagnosing-bugs`** | 新增 Redact 段(密钥脱敏),Phase 1 completion criterion 从「贴出调用和输出」改成「脱敏后展示」 | `CHANGELOG.md:7-11` |

### 6.2 在变轻 / 被拆 / 被废

| 对象 | 变化 | 出处 |
| --- | --- | --- |
| **`tdd`** | **改造成 reference-only**:删掉 Workflow 和每循环 checklist(理由:「red → green → refactor 已被模型已有的领头词锚定,step-by-step 基本是在复述这个循环」),**连 refactor 阶段一起删掉** —— TDD 现在只有 red → green,重构归 review 阶段,`refactoring.md` 移交 `code-review` | `CHANGELOG.md:207-212` |
| **`writing-great-skills` → `writing-for-agents`** | `GLOSSARY.md` **合并进** `SKILL.md`(一术语一处权威处理,`_Avoid_` 同义词列表与独立的 Predictability 定义**删除**);skill-only 机制**拆出** `SKILL-MECHANICS.md`。破坏性改名,**不留别名** | `CHANGELOG.md:88-90` |
| **一次删 6 个技能** | 4 个被更好的技能吸收:`ubiquitous-language` → `domain-modeling`;`design-an-interface` → `codebase-design`(design-it-twice 技术作为 `DESIGN-IT-TWICE.md` 保留在里面);`qa` → `triage` + `to-tickets`;`request-refactor-plan` → `to-spec` + `improve-codebase-architecture`。另 2 个是作者私人的(`edit-article`、`obsidian-vault`),连同 `personal/` 桶一起去掉 | `CHANGELOG.md:132-145` |
| **规划类技能合并** | `to-prd` → `to-spec`;**`to-plan` + `to-issues` 合并成一个 `to-tickets`,`to-issues` 删除** | `CHANGELOG.md:181-188` |
| **`wait-what`** | 新增技能,**三行长**。理由直接写出重量哲学:「**Concision skills fail by growing** —— 一个 400 行的技能照样让模型啰嗦,所以这个技能就是一个精确的领头词,别无他物」 | `CHANGELOG.md:76-80` |
| **`setup-matt-pocock-skills`** | 变友好=变轻:triage 标签只在 triage 装了才问,且从「覆盖式盘问」压成一个推荐 yes 的问题;「外部 PR 作为请求面」不再是 setup 问题;domain docs 默认单 context,不问 | `CHANGELOG.md:115-122` |
| **`wizard`** | 删掉时间估算(`TOTAL_MINUTES`、剩余时间显示),进度改成按 stage 计数 | `CHANGELOG.md:15` |
| **`improve-codebase-architecture`** | 加 YAGNI 范围过滤,**缩小**扫描面到最近在改的路径 | `CHANGELOG.md:94` |
| **跨 harness 减负** | 从 `code-review`、`codebase-design`、`improve-codebase-architecture` 的子代理派发指令里**删掉 Claude Code 专有的工具名和 agent 类型名**,好让这些步骤在 Codex 等 harness 上也能照做 | `CHANGELOG.md:13` |
| **`prototype`** | 逻辑分支产物从「终端应用」改成**一个自包含 HTML 文件**(无构建、无服务器);「throwaway」重新定义为「不删除,放在 `prototype/<name>` 分支上作为 primary source」 | `CHANGELOG.md:54-58` |

### 6.3 作者对「重量」的态度(从上述变化推出)

1. **重量不按行数算,按「是否有独立的触发词 / 是否有别的技能需要它」算。** 拆出一个 model-invoked 技能的条件是「你有一个真的会在 prompt 里用的领头词,或另一个技能必须够到它」,并且明说「你要为这个新的常驻 description 付 context load,所以那份独立可达性得配得上」(`SKILL-MECHANICS.md:18`)。
2. **重复即负债,合并是常态操作。** 6 个技能被删,4 个是因为「已被做得更好的技能吸收」(`CHANGELOG.md:134`);`to-plan`+`to-issues` 合并;`GLOSSARY.md` 并回 `SKILL.md`。合并时**不留别名**(`CHANGELOG.md:90`),即宁可破坏兼容也要保持一个真相源。
3. **变重的是「编排」,变轻的是「执行」。** 路由器(ask-matt)、地图型流程(wayfinder)、状态机(triage)在长;干活的技能在缩(`tdd` 变纯 reference、`implement` 15 行、`handoff` 16 行、`grill-with-docs` 7 行)。这与 2.2 的梯子一致:steps 少而顶,reference 沉到 pointer 后面。
4. **文档变长时的第一反应是「拆一个 pointer 出去」,不是「精简措辞」。** 两个最典型:`ask-matt` 扩容时拆出 `PHASE-BOUNDARIES.md`;`writing-for-agents` 扩范围时拆出 `SKILL-MECHANICS.md`。
5. **对「靠加长来解决」有明确的反面判断。** 「Concision skills fail by growing」(`CHANGELOG.md:78`);「一个没人碰的角落里的 deepening opportunity 是你永远兑现不了的重构」(`CHANGELOG.md:94`);`tdd` 的 Workflow 被删是因为「基本是在复述模型已有的循环」(`CHANGELOG.md:70`)—— 全都是 no-op 测试在生产环境的应用。
6. **beta 通道是重量的泄压阀。** `in-progress/` 被明确定义为「beta,故意公开,要反馈,不进 plugin,不给 docs 页,**可以随时改变或消失**」(`skills/in-progress/README.md:3`)。当前里面有 8 个,其中 `retro` 直接标注「STUB: design notes only, not functional yet」(`skills/in-progress/README.md:18`)。**未发布也要公开**,但用桶把它和承诺隔开。

---

## 7. 与 Trellis 直接冲突的点(owner 自建时必须二选一)

以下每条都给了两侧的行号。Trellis 侧引用来自 `scratchpad/trellis/`。

### 冲突 1:周期状态存在哪里 —— 可插拔 issue tracker vs 固定的 `.trellis/` 目录 + CLI

- **Matt**:状态住在**你自己选的** issue tracker 里。setup 技能让你在 GitHub / GitLab / 本地 markdown(`.scratch/<feature>/`)/ 其他(用一段自然语言描述工作流)之间选,选择记录进 `docs/agents/issue-tracker.md`(`skills/engineering/setup-matt-pocock-skills/SKILL.md:38-49`)。**所有技能通过这个间接层解析 tracker,不许硬编码路径** —— `wayfinder` 曾硬编码 `docs/agents/issue-tracker.md`,被当作 bug 修掉,理由是「它打破了整套体系依赖的那层间接」(`CHANGELOG.md:215-221`)。
- **Trellis**:状态住在固定结构里 —— 每个任务一个目录 `.trellis/tasks/{MM-DD-name}/`,内含 `task.json`、`prd.md`、可选 `design.md`/`implement.md`/`research/`,以及给子代理用的上下文清单 `implement.jsonl`/`check.jsonl`(`trellis/.trellis/workflow.md:42`);生命周期由 Python CLI 驱动(`task.py create/start/current/finish/archive/list`,`trellis/.trellis/workflow.md:46-52`);「当前任务」指针存在 `.trellis/.runtime/sessions/`,拿不到 session key 就没有 active task 且 `task.py start` 直接失败(`trellis/.trellis/workflow.md:76`)。
- **为什么必须二选一**:两者都想当「这个 ticket 的状态在哪」的唯一真相源。同时上,你会有 `.trellis/tasks/*/task.json` 和 issue tracker 两份 status,且没有任何机制对账。

### 冲突 2:周期怎么推进 —— 人打斜杠命令 vs hook 每轮注入 breadcrumb

**这是最根本的一条,其他冲突多半是它的下游。**

- **Matt**:全部编排技能都是 user-invoked,**人不打命令,什么都不会发生**;路由器本身也只推荐不执行(`docs/engineering/ask-matt.md:5`)。理论依据是 context load:常驻的每个词每轮都在花 token 和注意力(`writing-for-agents/SKILL.md:24`),而 cognitive load「**不是一个要最小化的成本:它是人类能动性的价格**」(`writing-for-agents/SKILL.md:25`)。
- **Trellis**:每个支持的平台用 `UserPromptSubmit` hook **每一轮**注入一个 `<workflow-state>` 面包屑,内容由 `workflow.md` 里的 `[workflow-state:STATUS]` 块单一供给(`trellis/.trellis/workflow.md` 的 breadcrumb contract 注释块,文件内 L155-L170 区段)。而且有一条被测试固化的不变量:**每个标了 `[required · once]` 的步骤都必须在对应 phase 的 breadcrumb 块里有一行强制说明,「面包屑是唯一的每轮通道;如果一个强制步骤没在那里被提到,AI 就会静默跳过它(Phase 1 planning gate 跳过和 Phase 3.4 commit 跳过都是这个缺口造成的)」**(同文件,invariant 段)。
- **为什么必须二选一**:Trellis 用生产事故证明了「不每轮注入就会被跳过」;Matt 用 context load 论证「每轮注入的东西要极度吝啬」。两者对同一个事实(常驻文本每轮都在花钱)给出了相反的结论。owner 不能既要 hook 强制推进,又要「零常驻 context」。

### 冲突 3:上下文怎么送到执行者手里 —— pointer 措辞 vs manifest 文件 + 字节上限

- **Matt**:靠 pointer 的**措辞**在需要时把材料拉进来;「决定 agent 何时以及多可靠地够到材料的是 pointer 的措辞,不是它的目标」,材料该不该内联是最后手段(`writing-for-agents/SKILL.md:12`)。
- **Trellis**:靠显式清单文件 —— `implement.jsonl` / `check.jsonl` 列出要注入子代理的 spec 和 research 条目,由 AI 在规划期 curate(`trellis/.trellis/workflow.md:54-59`);注入量由字节上限管控:单文件 32KB、单 artifact 64KB、总负载 128KB,超限的降级成索引行(`trellis/.trellis/config.yaml:140-154`)。
- **为什么必须二选一**:一个把「加载什么」交给运行时的语言概率,一个交给规划期的显式清单。混用会导致同一份 spec 既被 manifest 注入又被 pointer 拉取。

### 冲突 4:项目级文档的角色 —— 纯词汇表 vs 注入式编码规范

- **Matt**:`CONTEXT.md` **只是词汇表**,「完全不能有实现细节。不要把它当 spec、当草稿纸、当实现决策的仓库」(`domain-modeling/SKILL.md:64`);实现决策去 ADR,而 ADR 有三条硬门槛(难逆转 / 无上下文会费解 / 真实权衡),缺一不写(`domain-modeling/SKILL.md:66-72`)。
- **Trellis**:`.trellis/spec/` 是**按 package 和 layer 组织的编码规范**,入口 `index.md` 带 Pre-Development Checklist 和 Quality Check(`trellis/.trellis/workflow.md:29-31`),核心原则第 2 条就是「**Specs injected, not remembered** —— 指南通过 hook/skill 注入,不靠记忆回想」(`trellis/.trellis/workflow.md:8`);任务级还有 prd/design/implement 三件套,复杂任务在 `task.py start` 前三件套必须齐(`trellis/.trellis/workflow.md:83-87`)。
- **为什么必须二选一**:同一个「项目知识」在两边的粒度和用途完全不同。Matt 的 `CONTEXT.md` 是为了**让 agent 少说废话**(`README.md:113`),Trellis 的 spec 是为了**让 agent 照规矩写码**。两套并存 = 两份会漂移的项目描述。

### 冲突 5:跨会话续工 —— 有序判断树(默认 continue)vs 自动 journal + finish-work 归档

- **Matt**:五个选项按序判断,**第一个 yes 获胜**,`Continue` 排第一因为「它是唯一保持会话作为 **primary source** 而不是它的摘要的动作」;`/compact` 排最后,是「默认项,不是第一反应」,起手就用它的失败模式是「一个对被摘要压平的决策自信地搞错的新会话」(`ask-matt/PHASE-BOUNDARIES.md:19-40`)。核心代价模型是一张 primary vs secondary source 的表(`PHASE-BOUNDARIES.md:42-51`)。`/handoff` 很窄:只在新 harness / 新目录 / 交同事 / 阶段中途分叉时用(`PHASE-BOUNDARIES.md:27-34`),而且写到**操作系统临时目录,不写进工作区**(`skills/productivity/handoff/SKILL.md:8`)。
- **Trellis**:每个 AI 会话都记进 `.trellis/workspace/<developer>/journal-N.md`(单文件 2000 行自动轮转),外加个人 `index.md`(`trellis/.trellis/workflow.md:80-86`);用户在「活干完了或上下文快满了」时打 `/trellis:finish-work`,Trellis 归档任务并更新 journal(`trellis/README.md:76`);核心原则第 3 条:「**Persist everything** —— 研究、决策、教训全部落文件;对话会被压缩,文件不会」(`trellis/.trellis/workflow.md:9`)。
- **为什么必须二选一**:Matt 把「摘要」当作有损、要尽量推迟的操作;Trellis 把「落盘」当作默认动作,每个会话都做。前者的默认是 continue,后者的默认是 persist。

### 冲突 6:收尾时的学习回写 —— 高门槛人工判定 vs 自动提升回 spec

- **Matt**:ADR 三条件门槛(见冲突 4);对应的「会话复盘并改进 agent 环境」的技能 **`retro` 至今是 STUB,「只有设计笔记,还不能用」**(`skills/in-progress/README.md:18`)。也就是说这条链在 Matt 这边**是空的**。
- **Trellis**:4 阶段循环的第 4 阶段就是「最后一次 check 跑完,然后 `trellis-update-spec` 把新学到的东西**提升回** `.trellis/spec/`,让下一个会话起点更聪明」(`trellis/README.md:85`);核心原则第 5 条同款(`trellis/.trellis/workflow.md:11`);`trellis-update-spec/SKILL.md` 356 行,是 Trellis 第四长的技能。
- **对 owner 的含义**:这是 Trellis **有而 Matt 没有**的能力,不是纯冲突。但采用它就等于采用了「spec 是活的、会被 agent 自动改写」这个前提,而这与 Matt 的「`CONTEXT.md` 只在人确认一个术语时就地更新」(`domain-modeling/SKILL.md:62`)是不同的信任模型。

### 冲突 7:认知负荷该由谁承担(哲学根源)

- **Matt**:「**人就是索引**。这不是一个要最小化的成本:它是人类能动性的价格;在人的判断重要的地方花它,在不重要的地方去掉它」(`writing-for-agents/SKILL.md:25`)。
- **Trellis**:开宗明义要消除它 —— 「AI 写码很快,但每个会话都从零开始 —— 不记得你的项目、你的约定、你团队的需求。Trellis 把 spec、task 和 memory 持久化进你的仓库」(`trellis/README.md:11`)。
- 这条不是实现细节的冲突,是**产品定位的冲突**,前六条都是它的投影。

### 冲突 8:技能体量的量级差

实测(`find ... -name SKILL.md -exec wc -l`):

- Matt:最长 `teach` 140 行、`diagnosing-bugs` 138、`wayfinder` 128;25 个 promoted 技能中位数约 71 行。
- Trellis:`python-design` 451 行、`contribute` 421、`first-principles-thinking` 403、`trellis-update-spec` 356、`trellis-brainstorm` 200。

两边对「一个技能该多大」的量级判断差 3 倍以上。这不是必须二选一的架构决策,但它是**写法规范能不能落地的检验**:如果 owner 采纳了 writing-for-agents 的 no-op 测试,Trellis 量级的技能文件基本活不下来。

### 7.1 汇总:owner 自建时必须做的取舍(5 个决策点)

| # | 决策点 | 选项 A(Matt) | 选项 B(Trellis) | 判据建议 |
| --- | --- | --- | --- | --- |
| 1 | 周期状态住哪 | 外部 issue tracker,靠一层 `docs/agents/issue-tracker.md` 间接指向 | `.trellis/tasks/` 固定目录 + `task.json` + Python CLI | 有没有真实协作者要看状态;单人本地 → A 的 local markdown 分支最轻 |
| 2 | 靠什么推进 | 人打 user-invoked 斜杠命令,零常驻 | hook 每轮注入 `<workflow-state>` breadcrumb | 你能不能忍受「忘了打命令 = 这步没做」;不能忍就必须付每轮的 context 税 |
| 3 | 上下文怎么送 | pointer 措辞按需触发 | manifest jsonl + 字节上限自动 inline | 执行者是同一个会话还是子代理;子代理越多越倾向 B |
| 4 | 项目知识的形态 | `CONTEXT.md` 纯词汇表(禁实现细节)+ 高门槛 ADR | `.trellis/spec/` 分层编码规范 + 每任务 prd/design/implement | 你的痛点是「agent 说不清楚话」还是「agent 不守规矩」 |
| 5 | 收尾与续工 | 阶段边界五选一,默认 continue,handoff 很窄;学习回写这条链是空的 | 每会话 journal + finish-work 归档 + update-spec 自动回写 | 会话长度与换机器频率;若常跨机器/跨 harness,A 的 handoff 不够,要补 |

### 7.2 不冲突、可以直接拿走的部分

以下与 Trellis 的状态机制**正交**,采用哪条路线都能用:

1. **no-op 逐句测试 + 删整句不修词**(`writing-for-agents/SKILL.md:81`)—— 这是压缩任何一份 harness 文档的通用工具。
2. **两种 load 的记账法**(`writing-for-agents/SKILL.md:20-27`)—— 每加一行 always-loaded 内容前先问它属于哪个预算。
3. **Leading words + 禁否定式**(`SKILL.md:63-74`)。
4. **Completion criteria 的 clarity/demand 二属性,以及「先磨锐界限,再考虑拆分」的防守顺序**(`SKILL.md:47-52`)。
5. **Tracer bullet 垂直切片规则 + blocking edges + frontier**(`to-tickets/SKILL.md:29-40`),以及 wide refactor 的 expand-contract 例外(`to-tickets/SKILL.md:40`)。
6. **单入口路由器的六条做法**(见 5.3)。
7. **grilling 的 round-by-round frontier + 「事实是 agent 的活、决策是人的活」**(`grilling/SKILL.md:8,26`)。

---

## 8. 未核实 / 本次没读的部分

- 没读:`skills/engineering/` 下 `code-review`、`diagnosing-bugs`、`tdd`、`prototype`、`research`、`wizard`、`wayfinder`、`triage`(只读了前 60 行)的 `SKILL.md` 正文,以及它们的附属 reference 文件;`skills/in-progress/` 与 `skills/misc/` 的技能正文(只读了两个桶的 README 和 `claude-handoff/SKILL.md`);`docs/` 下除 `writing-for-agents.md` 和 `ask-matt.md`(前 40 行)之外的 18 个页面。
- 没读:`.agents/adr/0002-ship-as-a-claude-code-plugin.md`、`.agents/install-block.md`、`.out-of-scope/` 三个文件、`skills/engineering/codebase-design/DEEPENING.md` 与 `DESIGN-IT-TWICE.md`、`improve-codebase-architecture/HTML-REPORT.md`、`triage/AGENT-BRIEF.md` 与 `OUT-OF-SCOPE.md`。
- 「最近 30 条 CHANGELOG」按仓库内 `CHANGELOG.md` 的条目顺序取,**不等于 git 提交时间顺序**;同一个 PR 号(如 #763)在多条里出现,说明一次 PR 可拆成多条 changeset。
- Trellis 侧只读了 `README.md`、`.trellis/workflow.md`(前约 200 行)、`.trellis/config.yaml`、一个任务目录的文件清单,以及 `.claude/skills/*/SKILL.md` 的行数统计。**Trellis 的 hook 实现代码、`.trellis/spec/` 内容、`packages/` 源码本次未读**,冲突 2 和 3 的结论基于 `workflow.md` 与 `config.yaml` 的自述,未做代码级验证。
- `README.md:122` 引用的外部示例 `CONTEXT.md`(course-video-manager 仓库)是外链,未访问。
- 本报告未核实这些技能的**实际效果**(作者的效果声称如「这可能是本仓库里最酷的技术」`README.md:133` 属自述,非实测)。
