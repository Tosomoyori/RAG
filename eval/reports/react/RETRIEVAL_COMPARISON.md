# 检索策略对照实验

## 比较对象与评测流程

本轮比较检索方式变化后，能否找到更多答案证据，以及最终回答能否改善。两组使用相同问题、文档、生成模型和提示词。

检索指标由 Python 脚本计算。端到端问答由 promptfoo 批量调用 /ask，并按配置的事实规则检查回答。实际检索由项目代码执行，实际回答由 DeepSeek 生成。

| 名称 | 候选片段的来源 | 精排后的处理 |
|---|---|---|
| 原向量方案（vector） | 向量检索找出 20 块 | 保留精排前 5 块，作为生成资料 |
| 改进检索方案（候选） | 中文使用 hybrid，英文使用 vector | 先保留精排前 5 块，再补相邻块，最多 10 块且片段总长不超过 2560 token |

逐题记录中的“vector 回答”指原向量方案生成的答案，“候选回答”指改进检索方案生成的答案。“候选”是实验阶段的名称，这套检索组合后来被采用为默认配置。

## vector、hybrid 与 language 的含义

- vector 是向量检索。embedding 模型将问题和文档片段转换为数字向量，Chroma 按相似程度选择片段。相关表达即使用词不同，也可能被找到；效果取决于模型和语料。
- BM25 是词法检索，主要根据问题和片段共享的词项评分，同时考虑词项出现频率、区分度和片段长度。本实现的英文使用字母数字词项，中文使用连续汉字二元组，例如“评测游戏”拆成“评测”“测游”“游戏”。
- hybrid 是融合检索。向量检索与 BM25 各找出 20 块，用 RRF 将两路排名折算成分数并相加，保留融合排名前 20 块，再进行精排。同一片段同时出现在两路结果中时，会累计两边的排名分数。
- language 是按问题语种选择检索方式的配置开关。中文走 hybrid，英文走 vector。

```text
vector    问题 → 向量检索 20 块 → 精排选出 5 块
hybrid    问题 → 向量检索 20 块 ＋ BM25 检索 20 块
                → RRF 融合保留 20 块 → 精排选出 5 块
language  中文选择 hybrid，英文选择 vector
```

## 精排种子、相邻块与长度预算

精排模型重新比较问题与候选片段的相关程度。精排保留的前 5 块称为“种子”，即优先放入生成资料的核心片段。

相邻块按同一文档的切块编号确定。半径为 1 时，选中第 13 块后，可补充第 12、14 块；半径为 0 时只使用精排结果。相邻块有助于接回被切块边界截断的说明。

```text
文档顺序    第 12 块 ← 第 13 块 → 第 14 块
处理方式      可补充    核心块     可补充
```

扩充时先保留精排种子，再从精排第一名开始，依次尝试加入其前一块、后一块，然后处理后续种子。重复片段去重。达到数量或长度限制后停止添加，因此各个种子的邻块可能只补入一部分。

数量限制为最多 10 块，长度限制为这些片段各自 token 数之和最多 2560。token 是模型计算文本长度的单位。预算仅统计片段，完整生成输入还包括用户问题和提示词。

## 实验条件

- 同一中英文语料、切块、embedding、精排模型、生成提示词和题目。开发检索集为中英各 22 题。
- 向量与 BM25 各召回 20 条，等权 RRF 的常数为 60，融合后保留 20 条，cross-encoder 精排至 5 条。
- BM25 使用 k1=1.5、b=0.75。英文按字母数字词项，中文按连续汉字二元组，单个汉字保留为词项。词项未做语义扩展。
- 相邻块半径为 1，优先保留精排种子，再按种子排名添加同文档邻块，上限 10 块、片段 token 总和 2560。预算不含提示词和问题。
- 端到端基线使用 vector、相邻块半径 0。候选使用 language、相邻块半径 1，其中中文 hybrid、英文 vector。
- 端到端串行调用相同 deepseek-chat，temperature=0.7。答案缓存与 promptfoo 响应缓存关闭，向量和精排缓存可生效。
- 8 道新验收问题在查看检索实验结果前冻结。它们来自同一论文，部分证据与开发题重叠。

## 检索指标的计分方法

标注块是题库预先标记的答案相关证据块。候选片段是第一轮检索找出的资料；在本实验中，其数量上限为 20。最终上下文是实际交给 DeepSeek 的全部片段。

| 表中指标 | 检查阶段 | 一道题如何计分 |
|---|---|---|
| 初筛命中率，即候选任一标注块命中 | 精排之前的前 20 块 | 找到至少一个标注块记为命中，再计算命中题数占全部题数的比例 |
| 精排命中率，即种子 top-5 命中 | 精排留下的 5 个核心片段 | 找到至少一个标注块记为命中 |
| 精排 MRR，即种子 MRR | 精排留下的 5 块及其排名 | 每题取第一个标注块排名的倒数，再对所有题平均。第 1 名得 1，第 2 名得 0.5，前 5 块未找到得 0 |
| 最终资料命中率，即上下文任一标注块命中 | 补充相邻块之后的全部生成资料 | 找到至少一个标注块记为命中 |
| 平均资料长度，即平均片段 token | 最终生成资料 | 统计每题片段的 token 总和，再求平均，用于观察输入量增加多少 |

计分示例采用中文四基准题，其标注证据为第 13、14 块。下表说明“任一标注块命中”的计分规则。

| 假设初筛结果 | 初筛是否命中 |
|---|---|
| 包含第 13 块，未包含第 14 块 | 是 |
| 两块都包含 | 是 |
| 两块都未包含 | 否 |

中文 vector 的初筛命中率为 59.1%，对应 22 道题中有 13 道至少找到一个标注块。四基准题需要跨块信息才能完整回答，找到其中一块后仍可能遗漏 WebShop，答案完整性由后面的问答检查继续判断。

## 检索结果

zh 表示中文，en 表示英文。每一行在对应语种的 22 道检索题上统计，邻块半径 0、1 分别表示关闭、开启前后各一块的扩充。

| 语种 | 检索方式 | 邻块半径 | 初筛命中率（20 块） | 精排命中率（5 块） | 精排 MRR | 最终资料命中率 | 平均资料长度（token） |
|---|---|---|---|---|---|---|---|
| zh | vector | 0 | 59.1% | 54.5% | 0.413 | 54.5% | 1280 |
| zh | vector | 1 | 59.1% | 54.5% | 0.413 | 63.6% | 2548 |
| zh | hybrid | 0 | 86.4% | 72.7% | 0.587 | 72.7% | 1280 |
| zh | hybrid | 1 | 86.4% | 72.7% | 0.587 | 77.3% | 2548 |
| en | vector | 0 | 95.5% | 86.4% | 0.725 | 86.4% | 1280 |
| en | vector | 1 | 95.5% | 86.4% | 0.725 | 90.9% | 2537 |
| en | hybrid | 0 | 95.5% | 81.8% | 0.708 | 81.8% | 1280 |
| en | hybrid | 1 | 95.5% | 81.8% | 0.708 | 90.9% | 2537 |

标注块可能提供替代证据，也可能分担不同答案要点。任一块命中和标注块覆盖率均不能直接代表答案完整。邻块方案的上下文更大，种子 top-5 指标用于保持相同候选规模的比较。

## 候选选择与逐题变化

中文使用 hybrid 加邻块。英文 hybrid 的种子 top-5 命中从 19/22 降至 18/22，因此英文候选采用 vector 加邻块。候选选择依据开发集表现。

- zh 的上下文新增命中题为 zh-04、zh-10、zh-13、zh-15、zh-22，退步题为 无。
- en 的上下文新增命中题为 en-10，退步题为 无。

## 端到端规则检查

端到端检查从输入问题开始，经过检索与生成，检查最终回答。此阶段使用 12 道开发题及 8 道预先冻结的验收题，共 20 题。检索表中的 44 题与本节的 20 题分别用于不同层次的评估。

本节“通过”表示响应格式、检索语种路由、答案缓存绕过和必答事实规则均通过。语种路由检查是否进入预期的中英文库；实际回答使用哪种语言，在后续语义评估中另行评分。

实际案例 zh-02 中，原向量方案的最终片段包含第 13 块，缺少后续的第 14 块，回答遗漏 WebShop。改进方案补入所需资料后，最终回答完整列出 HotPotQA、FEVER、ALFWorld 和 WebShop。

| 题组 | 原向量方案（vector） | 改进检索方案（候选） |
|---|---|---|
| 开发题 | 8/12 | 10/12 |
| 验收题 | 7/8 | 8/8 |

| 题目 | 原向量方案（vector） | 改进检索方案（候选） | 原方案片段数 | 改进方案片段数 |
|---|---|---|---|---|
| en-01 | 失败 | 失败 | 5 | 10 |
| en-02 | 通过 | 通过 | 5 | 10 |
| en-05 | 通过 | 通过 | 5 | 10 |
| en-08 | 通过 | 通过 | 5 | 10 |
| en-13 | 通过 | 通过 | 5 | 10 |
| en-19 | 通过 | 通过 | 5 | 10 |
| zh-01 | 通过 | 通过 | 5 | 10 |
| zh-02 | 失败 | 通过 | 5 | 10 |
| zh-05 | 通过 | 通过 | 5 | 10 |
| zh-08 | 通过 | 通过 | 5 | 10 |
| zh-13 | 失败 | 通过 | 5 | 10 |
| zh-19 | 失败 | 失败 | 5 | 10 |
| acceptance-zh-gain | 通过 | 通过 | 5 | 10 |
| acceptance-zh-prompts | 通过 | 通过 | 5 | 10 |
| acceptance-zh-products | 通过 | 通过 | 5 | 10 |
| acceptance-zh-examples | 失败 | 通过 | 5 | 10 |
| acceptance-en-gain | 通过 | 通过 | 5 | 10 |
| acceptance-en-prompts | 通过 | 通过 | 5 | 10 |
| acceptance-en-products | 通过 | 通过 | 5 | 10 |
| acceptance-en-examples | 通过 | 通过 | 5 | 10 |

## 适用范围

- 结果来自小规模、同论文开发与验收题，指标针对当前标注。验收题未用于配置选择，但证据主题并非全部独立。
- 生成结果为单次采样。规则检查覆盖必答模式，完整正确性与依据一致性仍需独立语义复核。
- 扩充上下文增加了输入量。服务端未返回 token 账单数据，无法据此计算实际费用。
- 英文回答语言仍由当前提示词与模型决定。
- 词法统计按请求读取当前 collection 重新计算，避免文档更新后复用旧词法快照。大语料场景需要另行评估开销。

## 采用配置

默认采用 RETRIEVAL_MODE=language、CONTEXT_NEIGHBORS=1、CONTEXT_MAX_CHUNKS=10、CONTEXT_MAX_TOKENS=2560。旧基线通过显式设置 RETRIEVAL_MODE=vector、CONTEXT_NEIGHBORS=0 复现。

候选结果为开发题 10/12、验收题 8/8，基线分别为 8/12 和 7/8。英文作者机构 en-01 与中文受控比较 zh-19 仍未完成。zh-19 缺少关键证据时生成了较长的概括，需继续检查回答依据。

## 逐题回答对照

### en-01

问题为 Which institutions are the authors affiliated with?

参考答案为 Department of Computer Science, Princeton University, and Google Research, Brain team.

**vector 回答（原向量方案）**

根据提供的片段，无法确定作者所属的机构。片段中只列出了作者姓名和论文信息（标题、期刊/会议、年份、URL 等），没有包含任何作者的单位或机构信息。

**候选回答（改进检索方案）**

根据提供的片段，无法确定作者所属的机构。片段中只列出了作者姓名和论文标题/出版信息，没有包含任何作者的单位或隶属机构信息。

候选规则检查结果为失败。缺少必答事实匹配，规则为 Princeton|普林斯顿 | 缺少必答事实匹配，规则为 Google|谷歌 | 缺少必答事实匹配，规则为 Brain|大脑

### en-02

问题为 What are the four benchmarks used to evaluate ReAct?

参考答案为 HotPotQA, FEVER, ALFWorld, and WebShop.

**vector 回答（原向量方案）**

根据提供的片段，用于评估 ReAct 的四个基准是：

1. **HotPotQA** — 问答（question answering）
2. **Fever** — 事实核查（fact verification）
3. **ALFWorld** — 基于文本的游戏（text-based game）
4. **WebShop** — 网页导航（webpage navigation）

**候选回答（改进检索方案）**

根据片段内容，用于评估 ReAct 的四个基准是：

1. **问答（Question Answering）**：HotPotQA（Yang et al., 2018）
2. **事实核查（Fact Verification）**：Fever（Thorne et al., 2018）
3. **文本游戏（Text-based Game）**：ALFWorld（Shridhar et al., 2020b）
4. **网页导航（Webpage Navigation）**：WebShop（Yao et al., 2022）

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### en-05

问题为 How does a thought differ from an action in terms of effect on the environment?

参考答案为 A thought does not affect the external environment and produces no observation feedback. Actions interact with the external environment.

**vector 回答（原向量方案）**

Based on the provided excerpts, a thought differs from an action in its effect on the environment as follows:

- A **thought** (also called a reasoning trace) is an action in the language space (Â = A ∪ L). It **does not affect the external environment**, and therefore leads to **no observation feedback**. Instead, a thought composes useful information by reasoning over the current context and updates the context to support future reasoning or acting.

- An **action** (in the domain-specific action space A) is distinct from a thought in that thoughts are explicitly described as not affecting the external environment, implying that actions do produce effects on the environment (and thus yield observation feedback). The excerpts note that ReAct augments the action space with language space, where a language-space action "does not affect the external environment, thus leading to no observation feedback" — contrasting it with regular actions that do interact with the environment.

In short: thoughts operate internally on context only (no environmental effect, no observation), while actions interact with the external environment and generate observations.

**候选回答（改进检索方案）**

Based on the provided text, a thought differs from an action in terms of effect on the environment as follows:

- A **thought** (or reasoning trace) is an action in the language space (ˆat ∈ L) that **does not affect the external environment**, and therefore leads to **no observation feedback**. Instead, a thought composes useful information by reasoning over the current context and updates the context to support future reasoning or acting.
- An **action** (in the traditional action space A) is executed in the environment and produces observation feedback from the environment (the agent receives an observation ot ∈ O after taking an action at ∈ A).

In short: thoughts operate internally on context only and leave the external environment unchanged, whereas actions interact with the external environment and yield observations.

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### en-08

问题为 What browser functionality does the lookup action simulate?

参考答案为 The browser Ctrl+F find functionality.

**vector 回答（原向量方案）**

The `lookup[string]` action simulates **Ctrl+F functionality on the browser** — specifically, it returns the next sentence in the page containing the given string.

**候选回答（改进检索方案）**

The lookup action simulates Ctrl+F functionality on the browser — it returns the next sentence in the page containing the given string.

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### en-13

问题为 How many unseen evaluation games were used in ALFWorld?

参考答案为 134 unseen evaluation games.

**vector 回答（原向量方案）**

根据提供的片段，ALFWorld 中使用了 **134 个未见过的评估游戏（134 unseen evaluation games）**。

**候选回答（改进检索方案）**

根据提供的片段，ALFWorld 中使用了 **134 个未见过的评估游戏（134 unseen evaluation games）**。片段中明确提到：“Following Shridhar et al. (2020b), we evaluate on 134 unseen evaluation games in a task-specific setup.” 以及 “On ALFWorld, we use all 134 unseen validation task instances”。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### en-19

问题为 What did the authors do to make the ReAct-versus-Act comparison a fair and controlled one?

参考答案为 Act uses the same trajectories with thoughts removed. Task instances are randomly selected from the training set, favoring neither method.

**vector 回答（原向量方案）**

The authors made the ReAct-versus-Act comparison fair and controlled by constructing Act prompts from the same annotated trajectories used for ReAct, but removing the “thoughts.” They also note that task instances were randomly chosen from the training set, so the setup “favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts.”

**候选回答（改进检索方案）**

The authors made the ReAct-versus-Act comparison fair and controlled by constructing the Act prompts from the same annotated trajectories used for ReAct, but stripping out the thoughts. Specifically, they note that “Act prompts are constructed using the same trajectories, but without thoughts — since task instances are randomly chosen from the training set, it favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts.” They also report that the advantage of ReAct over Act was consistent across six controlled trials.

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### zh-01

问题为 论文作者分别来自哪些机构？

参考答案为 普林斯顿大学计算机科学系和 Google Research 的 Brain team。

**vector 回答（原向量方案）**

根据片段中明确标注的作者机构信息，论文作者分别来自：

- **普林斯顿大学计算机科学系**（Princeton University, Department of Computer Science）
- **谷歌研究，大脑团队**（Google Research, Brain Team）

具体对应作者为：Shunyu Yao、Karthik Narasimhan 隶属普林斯顿大学计算机科学系；Jeffrey Zhao、Dian Yu、Nan Du、Izhak Shafran、Yuan Cao 隶属谷歌研究大脑团队。片段中其他参考文献未标注作者机构信息，无法据此判断。

**候选回答（改进检索方案）**

根据提供的片段，论文《REACT: 协同推理和行动》的作者机构信息如下：

- **普林斯顿大学计算机科学系**（作者：Shunyu Yao、Karthik Narasimhan）
- **谷歌研究，大脑团队**（作者：Jeffrey Zhao、Dian Yu、Nan Du、Izhak Shafran、Yuan Cao）

片段中明确标注了作者的单位 affiliation：¹ 普林斯顿大学计算机科学系，² 谷歌研究，大脑团队。其他引用文献的作者机构信息未在片段中完整给出，无法确认。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### zh-02

问题为 论文用了哪四个基准来评测 ReAct？

参考答案为 HotPotQA、FEVER、ALFWorld 和 WebShop。

**vector 回答（原向量方案）**

根据片段内容，论文在四个不同的基准上对 ReAct 进行了实证评估，分别是：

1. **问答**：HotPotQA（Yang et al., 2018）
2. **事实验证**：Fever（Thorne et al., 2018）
3. **基于文本的游戏**：ALFWorld（Shridhar et al., …）
4. **网页导航**（片段中在列举任务类型时提到“包括但不限于QA、事实验证、文本游戏和网页导航”，但第四个基准的具体名称在提供的片段中被截断，未完整给出）

**候选回答（改进检索方案）**

根据片段内容，论文用了以下四个基准来评测 ReAct：

1. **问答**：HotPotQA（Yang et al., 2018）
2. **事实验证**：Fever（Thorne et al., 2018）
3. **基于文本的游戏**：ALFWorld（Shridhar et al., 2020b）
4. **网页导航**：WebShop（Yao et al., 2022）

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### zh-05

问题为 思想（thought）与行动（action）在对环境的影响上有什么区别？

参考答案为 思想不改变外部环境，因此没有环境观察反馈。行动用于与外部环境交互。

**vector 回答（原向量方案）**

根据相关片段，思想（thought）与行动（action）在对环境的影响上的区别是：

- **行动**：会影响外部环境。片段指出，语言空间中的动作（即思想或推理轨迹）“不影响外部环境，从而导致没有观察反馈”，这从反面说明行动是作用于外部环境并会产生观察反馈的。
- **思想**：不影响外部环境，也不会产生观察反馈。片段明确说明“语言空间中的动作……我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈”。思想的作用是对当前上下文进行推理、组成有用信息，并更新上下文以支持未来的推理或行动。

简言之，行动会改变外部环境并带来观察反馈，而思想只作用于内部上下文、不改变外部环境。

**候选回答（改进检索方案）**

根据提供的片段，思想（thought）与行动（action）在对环境的影响上的区别主要体现在：

1. **思想不影响外部环境**：片段明确指出，语言空间中的动作（即思想或推理轨迹）“不影响外部环境，从而导致没有观察反馈”。

2. **思想作用于上下文而非环境**：思想旨在“通过对当前上下文ct进行推理来组成有用的信息，并更新上下文ct+1=(ct，at)以支持未来的推理或行动”——即思想更新的是内部上下文，而非外部环境。

3. **行动则与环境交互**：片段将代理描述为“与环境交互以解决任务”，代理从环境接收观察ot，并采取行动at；行动空间A与语言空间L被明确区分（扩大后的动作空间为Aˇ=A∪L），说明行动是作用于外部环境、能产生观察反馈的那类动作，而思想属于语言空间、不产生环境观察反馈。

简言之：**思想不改变外部环境、不产生观察反馈，只更新内部上下文以支持后续推理或行动；行动则与环境交互并产生观察反馈。**

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### zh-08

问题为 lookup 动作模拟的是浏览器的什么功能？

参考答案为 浏览器的 Ctrl+F 文本查找功能。

**vector 回答（原向量方案）**

根据相关片段，lookup 动作模拟的是浏览器上的 **Ctrl+F 功能**（即在页面中查找字符串并返回包含该字符串的页面中的下一个句子）。

**候选回答（改进检索方案）**

根据相关片段，lookup[string] 动作模拟的是浏览器上的 **Ctrl+F（查找）功能**，即返回包含指定 string 的页面中的下一个句子。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### zh-13

问题为 ALFWorld 用了多少个未见过的评测游戏？

参考答案为 134 个未见过的评测游戏。

**vector 回答（原向量方案）**

根据提供的片段，无法确定 ALFWorld 用了多少个未见过的评测游戏。片段中只提到 ReAct 在 ALFWorld 上的成功率有34%的绝对提高，以及提到了训练任务实例数量（如103~105个、3553个、1012条人类注释轨迹、10587条训练指令等），但没有给出“未见过的评测游戏”的具体数量。

**候选回答（改进检索方案）**

根据提供的片段，ALFWorld 使用了 **134 个未见过的评测游戏**（文中表述为“134 个看不见的评估游戏”/“134 个不可见的验证任务实例”）。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### zh-19

问题为 作者做了哪些安排，才让 ReAct 与仅行动版本的对比算得上是公平的受控实验？

参考答案为 Act 使用相同轨迹但移除思想，任务实例从训练集随机选择，使比较不偏向任一方法。

**vector 回答（原向量方案）**

根据片段内容，作者为确保 ReAct 与仅行动版本（Act）的对比是公平的受控实验，主要做了以下安排：将仅行动提示（Act）定义为“移除反应轨迹中的思想”，即在与 ReAct 相同的反应轨迹基础上去掉推理（思想）部分，使其大致类似于 WebGPT 与互联网互动来回答问题的方式；同时说明 Act 虽然在不同任务和行动空间上操作，并使用模仿和强化学习来代替提示，但在对比中作为仅行动的基线。片段还提到实验在少量学习设置下、在不同基准上进行广泛实验，并辅以系统的消融和分析，以理解推理任务中行动的重要性以及交互任务中推理的重要性。

**候选回答（改进检索方案）**

根据片段内容，作者为让 ReAct 与仅行动版本的对比算得上公平的受控实验，主要做了以下安排：

1. **设置“仅行动”的受控基线**：片段明确提到“表现出相对于只有行动的受控基线的持续优势”，说明作者将仅行动版本作为受控基线进行比较。

2. **在相同基准上进行广泛实验**：作者“在不同的基准上进行广泛的实验”，以展示 ReAct 相对于孤立地执行推理或动作生成的现有方法的优势。

3. **进行系统的消融和分析**：作者“提出了系统的消融和分析，以理解在推理任务中行动的重要性，以及在交互任务中推理的重要性”，通过消融实验分离推理与行动各自的作用。

4. **采用少量学习设置**：实验在“少量学习设置”下进行，ReAct“仅从一到六个上下文实例中学习”，并与仅推理或仅行动的基线在相同条件下比较。

5. **控制提示选择**：片段提到“ReAct 性能对提示选择的鲁棒性如何”，并在 ALFWorld 上“使用根据 PaLM-540B 设置的最佳提示”，说明对提示设置进行了统一/控制。

6. **使用相同模型与解码设置进行比较**：例如 GPT-3 实验采用“text-davinci-002，greedy decoding”，并在 HotpotQA 上“随机抽取了 500 个验证问题的子集”，在 ALFWorld 上“使用所有 134 个不可见的验证任务实例”，以保证比较条件一致。

片段中没有进一步说明其他具体的实验控制细节（如随机种子、任务实例配对方式等），因此以上仅依据给定内容概括。

候选规则检查结果为失败。缺少必答事实匹配，规则为 相同.{0,12}轨迹|同一.{0,12}轨迹|same(?: annotated)? trajectories | 缺少必答事实匹配，规则为 (没有|移除|去掉|不含|删除).{0,30}(思想|思考|推理)|without thoughts|thoughts.{0,12}removed|remov(?:e|ing).{0,12}thoughts | 缺少必答事实匹配，规则为 训练集|training set

### acceptance-zh-gain

问题为 ReAct 在 ALFWorld 和 WebShop 上的成功率分别绝对提高了多少个百分点？

参考答案为 分别提高 34 和 10 个百分点。

**vector 回答（原向量方案）**

根据相关片段，ReAct 在 ALFWorld 和 WebShop 上的成功率分别绝对提高了 **34%** 和 **10%** 个百分点。

**候选回答（改进检索方案）**

根据片段内容，ReAct 在 ALFWorld 和 WebShop 上的成功率分别绝对提高了 **34 个百分点**和 **10 个百分点**。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### acceptance-zh-prompts

问题为 ALFWorld 实验为每一种任务类型构造了多少个提示？

参考答案为 每种任务类型构造 6 个提示。

**vector 回答（原向量方案）**

根据相关片段，ALFWorld 实验为每一种任务类型构造了 **6 个提示**。具体做法是：从注释的 3 个轨迹中，通过 2 个注释轨迹的每个排列，为每个任务类型构建 6 个提示；Act 提示则使用相同的轨迹构建，但不包含思想（推理痕迹）。

**候选回答（改进检索方案）**

根据相关片段，ALFWorld 实验为每一种任务类型构造了 **6 个提示**。具体来说，是从注释的 3 条轨迹中，通过 2 条注释轨迹的每个排列来构建的。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### acceptance-zh-products

问题为 WebShop 环境有多少真实世界商品和人工指令？

参考答案为 118 万件商品和 12k（12000）条人工指令。

**vector 回答（原向量方案）**

根据提供的片段，WebShop 环境拥有 **118 万件真实世界的产品**和 **12k 人工说明（人工指令）**。

**候选回答（改进检索方案）**

根据提供的片段，WebShop 环境拥有 **118 万件真实世界的产品**和 **12k 人工说明（人工指令）**。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### acceptance-zh-examples

问题为 用于 HotpotQA 和 Fever 的 ReAct 提示各选了多少个训练案例？

参考答案为 分别选取 6 和 3 个训练案例。

**vector 回答（原向量方案）**

根据提供的片段，ReAct 在 HotpotQA 和 FEVER 上分别设置了 **7 个**和 **5 个**步骤（用于 ReAct→CoT-SC 的切换启发），但片段中并未明确说明“各选了多少个训练案例”。片段提到的是步骤数，而非训练案例数。因此，无法从给定内容中得出训练案例的具体数量。

**候选回答（改进检索方案）**

根据相关片段，对于 HotpotQA 和 Fever 的 ReAct 提示，分别随机选择了 **6 个**和 **3 个**训练案例，并手动构建 ReAct-format 轨迹以用作提示中的少数镜头样本。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### acceptance-en-gain

问题为 By how many percentage points did ReAct improve success rates on ALFWorld and WebShop, respectively?

参考答案为 34 and 10 percentage points, respectively.

**vector 回答（原向量方案）**

根据片段内容，ReAct 在 ALFWorld 和 WebShop 上的成功率分别提升了 **34 个百分点**和 **10 个百分点**。片段中明确写道：“with an absolute improvement of 34% and 10% in success rates respectively.”

**候选回答（改进检索方案）**

ReAct improved success rates by 34 percentage points on ALFWorld and 10 percentage points on WebShop.

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### acceptance-en-prompts

问题为 How many prompts were constructed per task type for the ALFWorld experiments?

参考答案为 6 prompts per task type.

**vector 回答（原向量方案）**

根据片段内容，ALFWorld 实验中为每种任务类型构造了 **6 个 prompts**。原文表述为：“For robustness, we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.”

**候选回答（改进检索方案）**

For the ALFWorld experiments, **6 prompts were constructed for each task type**.

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### acceptance-en-products

问题为 How many real-world products and human instructions does the WebShop environment contain?

参考答案为 1.18 million products and 12 thousand human instructions.

**vector 回答（原向量方案）**

根据相关片段，WebShop 环境包含 **1.18M 个真实世界产品**和 **12k 条人类指令**。

**候选回答（改进检索方案）**

根据相关片段，WebShop 环境包含 **1.18M（118万）个真实世界产品和 12k（1.2万）条人类指令**。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过

### acceptance-en-examples

问题为 How many training examples were selected for the HotpotQA and Fever ReAct prompts, respectively?

参考答案为 6 and 3 examples, respectively.

**vector 回答（原向量方案）**

根据相关片段，HotpotQA 和 Fever 分别随机选择了 **6** 个和 **3** 个训练案例来手工构建 ReAct 格式的轨迹，作为提示中的少样本示例。

**候选回答（改进检索方案）**

根据相关片段，对于 HotpotQA 和 Fever 的 ReAct 提示，分别随机选择了 **6 个**和 **3 个**训练集案例，并手工编写成 ReAct 格式的轨迹作为提示中的少样本示例。

候选规则检查结果为通过。响应结构、语种路由、答案缓存绕过和必答事实检查均通过
