# 首批端到端评测记录

## 本轮检查范围与 promptfoo 的作用

本轮从原有题库中选择中英各 6 道问题，共 12 道，运行“问题 → 检索片段 → DeepSeek 生成 → 最终回答”的完整流程。原有检索评测检查证据是否被找到，本轮继续检查生成结果是否包含必答事实。

promptfoo 负责读取测试题、批量调用 /ask、收集实际回答和片段、执行配置的检查并保存结果。项目代码负责检索与缓存处理，DeepSeek 负责生成回答，事实标准由题库和规则提供。

“通过”表示接口响应、检索语种路由、答案缓存绕过和必答事实匹配符合规则。这里的语种路由检查是否进入中英文库，实际回答语言在后续语义评估中单独检查。

评测日期为 2026-11-04（Asia/Shanghai）。

## 运行条件

- promptfoo 0.125.1，通过 HTTP 调用本机 `/ask`，串行执行 12 题。
- 使用 conda RAG 环境。服务绑定 127.0.0.1，缓存与队列使用 memory 后端，上传 worker 关闭。
- deepseek-chat，temperature=0.7，召回 20 条、精排保留 5 条，切块 256 token、重叠 40 token。
- 答案缓存和 promptfoo 响应缓存关闭。向量与精排缓存可生效，耗时包含首次模型初始化。
- 证据与当前 Chroma 中对应块核对通过。语料、代码和评测配置哈希记录于本地 manifest.json。

## 结果

初始规则通过 7/12。对同一批已保存回答修正规则后，通过 8/12。重评分复用原始回答。

修正涉及 en-19 的合法表达 same annotated trajectories 和 removing the thoughts，并扩大中文移除思想表达的匹配范围。原始结果保存在 baseline.json，重评分结果保存在 reviewed.json。

| 题目 | 原始规则 | 修正规则 | 最终片段中的标准证据块 | 服务耗时 ms |
|---|---|---|---|---|
| en-01 | 失败 | 失败 | 未命中 | 7098.1 |
| en-02 | 通过 | 通过 | 14 | 2729.2 |
| en-05 | 通过 | 通过 | 17 | 3304 |
| en-08 | 通过 | 通过 | 22 | 2387.8 |
| en-13 | 通过 | 通过 | 35 | 2073.5 |
| en-19 | 失败 | 通过 | 35 | 2476.4 |
| zh-01 | 通过 | 通过 | 0 | 2831.6 |
| zh-02 | 失败 | 失败 | 13 | 2447.9 |
| zh-05 | 通过 | 通过 | 18 | 2599.2 |
| zh-08 | 通过 | 通过 | 25 | 2125.8 |
| zh-13 | 失败 | 失败 | 未命中 | 2353.8 |
| zh-19 | 失败 | 失败 | 未命中 | 2605.5 |

## 失败案例复核

- en-01 返回片段未包含作者单位，回答说明无法确定。独立检索评测确认标准块在召回阶段未命中。
- zh-02 只列出前三个基准，第四项回答为网页导航，遗漏 WebShop 名称。标准证据横跨两个块，需要检查召回与精排覆盖。
- zh-13 最终片段缺少 134 个游戏的标准证据，回答说明证据不足。独立检索评测确认标准块在召回阶段未命中。
- zh-19 最终片段缺少受控比较的标准证据，回答遗漏相同轨迹和训练集随机选择，并混淆其他方法的说明。独立检索评测确认标准块在召回阶段未命中。

## 全量检索基线复测

同日运行既有 eval/run_eval.py -v，中英各 22 题，结果如下。

| 语种 | Recall@K | Hit@N | MRR |
|---|---|---|---|
| zh | 59.1% | 54.5% | 0.413 |
| en | 95.5% | 86.4% | 0.725 |

zh-02 的最终结果包含块 13，缺少续接 WebShop 信息的块 14。现有任一块命中指标将该题计为命中，端到端检查识别了答案不完整。

## 评测边界

- 通过率表示响应协议、语言路由、答案缓存绕过和关键事实正则检查通过。完整语义正确性、事实间关系及依据一致性仍需单独评分。
- en-19 初始失败属于规则漏识别，已保留修订记录。规则修订使用本轮输出，后续需要独立验收题。
- 英文问题的部分回答使用中文。当前断言检查语言路由，回答语言单独记录为后续优化项。
- 单次运行、12 题与 temperature=0.7 限制了结果稳定性判断。
- HTTP 响应未暴露模型 token 用量，因此 promptfoo 中的零 token 统计无法用于费用核算。实际费用以模型服务账单为准。
- 参考答案对照分块预览与当前库核对，尚未经独立人工审定或原 PDF 页面复核。

## 逐题回答

### en-01

参考答案为 Department of Computer Science, Princeton University, and Google Research, Brain team.

根据提供的片段，无法确定作者所属的机构。片段中仅列出了作者姓名和论文信息，没有包含作者的单位或机构信息。

规则结果为失败。Required fact pattern missing: Princeton|普林斯顿 | Required fact pattern missing: Google|谷歌 | Required fact pattern missing: Brain|大脑

### en-02

参考答案为 HotPotQA, FEVER, ALFWorld, and WebShop.

根据片段内容，用于评估 ReAct 的四个基准是：

1. **HotPotQA** — 问答（question answering）
2. **Fever** — 事实核查（fact verification）
3. **ALFWorld** — 基于文本的游戏（text-based game）
4. **WebShop** — 网页导航（webpage navigation）

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### en-05

参考答案为 A thought does not affect the external environment and produces no observation feedback. Actions interact with the external environment.

根据片段内容，思想（thought）与行动（action）在对环境的影响上的区别是：

- **思想**：在 ReAct 框架中，语言空间中的“思想”或“推理轨迹”（reasoning trace）**不影响外部环境**，因此**不会产生观察反馈**（no observation feedback）。它的作用是通过对当前上下文进行推理来组合有用信息，并更新上下文以支持未来的推理或行动。
- **行动**：行动作用于外部环境，会产生观察反馈（片段以“does not affect the external environment, thus leading to no observation feedback”来描述思想，反衬出行动会影响环境并带来观察反馈）。

简言之，思想是内部的、不影响环境的推理过程；行动则会作用于外部环境并引发观察反馈。

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### en-08

参考答案为 The browser Ctrl+F find functionality.

The lookup action simulates Ctrl+F functionality on the browser — it returns the next sentence in the page containing the given string.

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### en-13

参考答案为 134 unseen evaluation games.

根据相关片段，ALFWorld 中使用了 **134 个未见过的评估游戏（134 unseen evaluation games）**。

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### en-19

参考答案为 Act uses the same trajectories with thoughts removed. Task instances are randomly selected from the training set, favoring neither method.

The authors made the ReAct-versus-Act comparison fair and controlled by constructing Act prompts from the same annotated trajectories used for ReAct, but removing the thoughts. They also note that task instances were randomly chosen from the training set, so the setup favors neither ReAct nor Act, providing a fair and controlled comparison to test the importance of sparse thoughts.

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### zh-01

参考答案为 普林斯顿大学计算机科学系和 Google Research 的 Brain team。

根据提供的片段，论文作者来自以下机构：

- **普林斯顿大学计算机科学系**（Princeton University, Department of Computer Science）
- **谷歌研究，大脑团队**（Google Research, Brain Team）

具体对应关系为：Shunyu Yao、Karthik Narasimhan 属于普林斯顿大学计算机科学系；Jeffrey Zhao、Dian Yu、Nan Du、Izhak Shafran、Yuan Cao 属于谷歌研究大脑团队。

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### zh-02

参考答案为 HotPotQA、FEVER、ALFWorld 和 WebShop。

根据片段内容，论文用了以下四个基准来评测 ReAct：

1. **问答**：HotPotQA（Yang et al., 2018）
2. **事实验证**：Fever（Thorne et al., 2018）
3. **基于文本的游戏**：ALFWorld（Shridhar et al.）
4. **网页导航**（片段中提到 ReAct 适用于“QA、事实验证、文本游戏和网页导航”等多样化任务，其中前三个明确对应上述基准，第四个为网页导航）

因此，四个基准分别是：**HotPotQA、Fever、ALFWorld 和网页导航**。

规则结果为失败。Required fact pattern missing: WebShop|网络商店

### zh-05

参考答案为 思想不改变外部环境，因此没有环境观察反馈。行动用于与外部环境交互。

根据相关片段，思想（thought）与行动（action）在对环境的影响上的区别是：

- **思想**：语言空间中的动作（思想或推理轨迹）**不影响外部环境**，因此**没有观察反馈**。思想旨在通过对当前上下文进行推理来组成有用的信息，并更新上下文以支持未来的推理或行动。
- **行动**：行动会作用于外部环境（片段中通过对比说明思想“不影响外部环境”，暗示行动会影响外部环境并产生观察反馈，如轨迹中的“行动—观察”步骤）。

简言之，思想是内部推理、不改变外部环境且无观察反馈；行动则与外部环境交互并产生观察结果。

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### zh-08

参考答案为 浏览器的 Ctrl+F 文本查找功能。

根据相关片段，lookup 动作模拟的是浏览器上的 **Ctrl+F 功能**（即页面内查找功能）。片段中明确写道：“lookup[string]，它将返回包含 string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能。”

规则结果为通过。Response structure, route, cache bypass and required fact patterns passed

### zh-13

参考答案为 134 个未见过的评测游戏。

根据提供的片段，无法确定 ALFWorld 用了多少个“未见过的评测游戏”。片段中只提到 ReAct 在 ALFWorld 上的成功率有 34% 的绝对提高，以及 BUTLER 等相关结果，但没有给出未见过评测游戏的数量。

规则结果为失败。Required fact pattern missing: \b134\b

### zh-19

参考答案为 Act 使用相同轨迹但移除思想，任务实例从训练集随机选择，使比较不偏向任一方法。

根据片段内容，作者为确保 ReAct 与仅行动版本（Act）的对比是公平的受控实验，主要做了以下安排：将“仅动作提示（Act）”定义为移除 ReAct 轨迹中的“思想”部分，使其大致类似于 WebGPT 与互联网互动来回答问题的方式；同时说明 Act 虽然在不同任务和行动空间上操作，并使用模仿和强化学习来代替提示，但仍作为对照基线纳入比较。片段还提到作者在不同基准上进行广泛实验，并在少量学习设置下比较 ReAct 与孤立执行推理或动作生成的现有方法，以及进行系统的消融和分析。

规则结果为失败。Required fact pattern missing: 相同.{0,12}轨迹|同一.{0,12}轨迹|same(?: annotated)? trajectories | Required fact pattern missing: 随机|random | Required fact pattern missing: 训练集|training set
