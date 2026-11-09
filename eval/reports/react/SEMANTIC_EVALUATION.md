# 回答语义评估与提示词对照

## 本轮评估的对象与分工

本轮固定每道题的检索片段，再比较不同提示词生成的回答。这样控制了找资料的差异，观察提示词对回答正确性、资料使用、证据边界和语言的影响。

保存回答的 AI 参考复核由项目中的 AI 证据审查形成。promptfoo 负责组织批量运行、保存回答和执行检查；DeepSeek 既生成回答，也在独立评分调用中根据评分标准给分。独立人工复核待完成。

## 评分项与分值

C/G/B/L 按固定顺序记录四项分数，即“正确性／依据一致性／证据边界行为／回答语言”。每项使用 0、1、2 分，2 分表示符合该项要求。

| 缩写 | 中文名称 | 检查内容 | 2 分 | 1 分 | 0 分 |
|---|---|---|---|---|---|
| C | 正确性 | 是否完成参考答案要求的信息 | 必答信息完整且正确 | 只有部分必答信息 | 缺少所问的事实答案，或核心事实错误 |
| G | 依据一致性 | 回答中的事实是否得到本次检索片段支持 | 所有事实有依据，合理说明缺失信息也可得 2 分 | 核心答案有依据，但额外细节支持不足 | 核心解释无依据或与片段矛盾 |
| B | 证据边界行为 | 证据充分、缺失、部分充分或问题前提错误时如何处理 | 有证据则回答，缺失则明确说明，前提错误则纠正 | 边界表达含糊，或部分混入猜测 | 将缺少依据的内容当作确定答案，或接受错误前提 |
| L | 回答语言 | 主要解释语言是否与问题要求一致 | 中文问题用中文，英文问题用英文 | 混用语言，要求的语言仍占主导 | 主要解释使用其他语言 |

原有 20 道题的正确性对照原文事实答案。新增题中，若参考答案本身要求说明资料缺失，恰当说明依据不足也可获得正确性 2 分；部分答案题需同时给出有依据的部分和缺失说明。

例如，en-01 的参考评分为 0/2/2/0。原文有作者机构信息，但这次检索片段没有提供，回答用中文说明无法确定。四项分数分别表示下列判断。

| 项目 | 分数 | 本例含义 |
|---|---|---|
| 正确性 C | 0 | 没有完成原文中的作者机构问题 |
| 依据一致性 G | 2 | 说明片段未给出机构，与本次资料相符 |
| 证据边界 B | 2 | 承认证据不足，未猜测机构 |
| 回答语言 L | 0 | 问题为英文，回答的主要解释为中文 |

四项分开记录，能够同时呈现任务完成情况和证据处理方式。2/2/2/2 表示四项均满足本表的参考标准。

## 评估定义

- 正确性 C（correctness）检查参考答案要求的信息，依据一致性 G（grounding）检查回答中的全部事实是否得到当前片段支持。
- 证据边界 B（behavior）检查证据充分、缺失、部分充分和错误前提下的回答方式，语言 L（language）检查主要解释语言。
- 综合通过要求 G、B、L 均为 2。需要正常回答或纠正前提时，C 也须为 2。对上下文不足而应拒答的题，综合通过允许未完成原文中的事实问题，正确性分数单独报告。
- 参考复核由 AI 完成，尚无独立人工标注。裁判和回答模型均使用 deepseek-chat，存在共同偏差。

## 保存回答的参考复核与评分校准

| 维度 | 与 AI 参考分数完全一致 | 有效评分数 |
|---|---|---|
| 正确性（C） | 19/20 | 20 |
| 依据一致性（G） | 18/20 | 20 |
| 证据边界行为（B） | 19/20 | 20 |
| 回答语言（L） | 17/20 | 20 |

例如正确性一行的 19/20，表示 20 道题中有 19 道的模型裁判分数与 AI 参考分数完全一致。这张表用于观察评分一致程度。有效评分数之外的执行错误单独记录，独立人工验证待完成。

| 题目 | AI 参考 C/G/B/L | 裁判 C/G/B/L |
|---|---|---|
| en-01 | 0/2/2/0 | 0/2/2/0 |
| en-02 | 2/2/2/0 | 2/2/2/0 |
| en-05 | 2/2/2/2 | 2/2/2/2 |
| en-08 | 2/2/2/2 | 2/2/2/2 |
| en-13 | 2/2/2/0 | 2/2/2/1 |
| en-19 | 2/2/2/2 | 2/2/2/2 |
| zh-01 | 2/1/2/2 | 2/2/2/2 |
| zh-02 | 2/2/2/2 | 2/2/2/2 |
| zh-05 | 2/2/2/2 | 2/2/2/2 |
| zh-08 | 2/2/2/2 | 2/2/2/2 |
| zh-13 | 2/2/2/2 | 2/2/2/2 |
| zh-19 | 0/0/0/2 | 1/1/1/2 |
| acceptance-zh-gain | 2/2/2/2 | 2/2/2/2 |
| acceptance-zh-prompts | 2/2/2/2 | 2/2/2/2 |
| acceptance-zh-products | 2/2/2/2 | 2/2/2/2 |
| acceptance-zh-examples | 2/2/2/2 | 2/2/2/2 |
| acceptance-en-gain | 2/2/2/2 | 2/2/2/2 |
| acceptance-en-prompts | 2/2/2/2 | 2/2/2/2 |
| acceptance-en-products | 2/2/2/0 | 2/2/2/1 |
| acceptance-en-examples | 2/2/2/0 | 2/2/2/1 |

### 分歧记录

- en-13。参考复核为 回答中的必答事实和解释与保存的来源片段一致。 裁判理由为 The answer correctly states 134 unseen evaluation games, matching the reference and directly quoting the context: 'we evaluate on 134 unseen evaluation games in a task-specific setup' and 'we use all 134 unseen validation task instances'. Grounding is fully supported by these quotations. Behavior is direct and answers the question. However, the main explanatory prose is in Chinese rather than the expected English, so language=1 (technical terms and quoted source text remain in English, but the surrounding prose is Chinese).
- zh-01。参考复核为 片段包含机构信息，但抽取出的署名部分缺少第一作者姓名，现有片段未完整呈现 Shunyu Yao 与所属机构的对应关系。 裁判理由为 回答准确给出参考中的两个机构：普林斯顿大学计算机科学系和 Google Research 的 Brain team，并正确对应作者。上下文明确写有“1 普林斯顿大学计算机科学系”“2 谷歌研究，大脑团队”，且作者列表与回答一致。回答还恰当说明其他引用文献的机构信息未完整给出，未编造缺失信息。
- zh-19。参考复核为 来源片段缺少使用相同轨迹、从训练集随机选取任务实例等关键安排。GPT-3 附录中的实验细节和一般性消融说明，无法支持问题所要求的 ReAct 与 Act 受控比较条件。 裁判理由为 参考要求的关键事实是：Act 使用相同轨迹但移除思想，任务实例从训练集随机选择，使比较不偏向任一方法。回答没有提到“相同轨迹但移除思想”或“从训练集随机选择任务实例”，因此缺少核心控制安排；但它确实提到“只有行动的受控基线”和“系统的消融和分析”，部分符合参考。回答还加入了若干未被上下文直接支持的细节，如“仅从一到六个上下文实例中学习”“使用根据 PaLM-540B 设置的最佳提示”“随机抽取了 500 个验证问题的子集”“使用所有 134 个不可见的验证任务实例”等，这些在片段中或未出现、或与所问的公平受控安排无直接对应，属于额外推断。行为上回答给出了看似完整的安排清单，但未明确承认缺失的关键信息（相同轨迹、随机选择任务实例），边界不清。语言为中文，符合要求。
- acceptance-en-products。参考复核为 回答中的必答事实和解释与保存的来源片段一致。 裁判理由为 The answer correctly states 1.18M products and 12k human instructions, matching the reference and directly supported by context: 'WebShop ... with 1.18M real-world products and 12k human instructions.' However, the main explanatory prose is in Chinese rather than the expected English, so language is scored 1.
- acceptance-en-examples。参考复核为 回答中的必答事实和解释与保存的来源片段一致。 裁判理由为 The answer correctly states 6 and 3 examples, matching the reference and the context: 'For HotpotQA and Fever, we randomly select 6 and 3 cases2 from the training set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts.' Grounding is fully supported by that sentence. Behavior is appropriate: it answers directly with the requested quantities. Language is scored 1 because the main explanatory prose is in Chinese, while the expected language is English; the technical names and numbers remain in their original form.

## 固定片段的提示词对照

20 道原有问题与 8 道新增边界问题使用冻结片段。参考答案和行为标注只用于评分，生成模型只接收问题、片段和目标语言。各提示词版本分别新生成回答，每个回答由相同裁判评分。

grounded-v1 增加证据不足、错误前提和部分回答规则。查看第一轮结果后，grounded-v2 进一步显式传入目标语言。第二版沿用相同问题，属于开发集上的迭代验证。

grounded-v2 的 zh-01 仍补入缺损文本中不完整的作者姓名，模型裁判给了 grounding=2，AI 逐条复核将其判为 grounding=1。grounded-v3 据此限制回答范围、禁止补全缺损姓名，并缩短证据不足时的背景展开。第三版继续沿用本批问题，后续需要新题验证。

grounded-v3 在 zh-01 给出机构集合后，又因逐位映射不完整而表达无法回答，裁判给 correctness=1。grounded-v4 进一步要求直接回答已有依据的部分，不把用户未要求的扩展细节作为回答条件。第四版同样属于本批开发题上的迭代。

grounded-v4 在 boundary-zh-partial 把机构上标写成“作者1/作者2”，裁判未识别该语义变化。grounded-v5 要求机构问题只列机构名称，不将机构编号转写为作者序号。该问题说明裁判可能漏判细粒度语义错误。

grounded-v5 在 boundary-en-funding 将 NSF 项目编号 2107048 当作资助金额 $2,107,048。该结果是实质性回归，裁判识别为 correctness=0、grounding=0、behavior=0。

第一轮存在一次裁判 JSON 格式错误，重试配置还出现过一次绝对断言路径兼容错误。最终通过标准配置过滤重跑该题，原始与重试导出均保留。评分器增加了最多一次 JSON 格式修复，不更换被评回答。

生成温度为 0.7，裁判温度为 0。单次生成与评分，promptfoo 响应缓存关闭。新增边界题包含资料缺失、部分答案和错误前提。

| 题组 | 提示词 | 综合通过 | 正确性 2 分 | 依据 2 分 | 行为 2 分 | 语言 2 分 | 执行错误 |
|---|---|---|---|---|---|---|---|
| 原有问题 | legacy | 14/20 | 18/20 | 19/20 | 19/20 | 15/20 | 0 |
| 原有问题 | grounded-v1 | 18/20 | 18/20 | 20/20 | 20/20 | 18/20 | 0 |
| 原有问题 | grounded-v2 | 20/20 | 18/20 | 20/20 | 20/20 | 20/20 | 0 |
| 原有问题 | grounded-v3 | 19/20 | 17/20 | 20/20 | 20/20 | 20/20 | 0 |
| 原有问题 | grounded-v4 | 20/20 | 18/20 | 20/20 | 20/20 | 20/20 | 0 |
| 原有问题 | grounded-v5 | 20/20 | 18/20 | 20/20 | 20/20 | 20/20 | 0 |
| 新增边界题 | legacy | 4/8 | 8/8 | 8/8 | 8/8 | 4/8 | 0 |
| 新增边界题 | grounded-v1 | 6/8 | 8/8 | 8/8 | 8/8 | 6/8 | 0 |
| 新增边界题 | grounded-v2 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 | 0 |
| 新增边界题 | grounded-v3 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 | 0 |
| 新增边界题 | grounded-v4 | 8/8 | 8/8 | 8/8 | 8/8 | 8/8 | 0 |
| 新增边界题 | grounded-v5 | 7/8 | 7/8 | 7/8 | 7/8 | 8/8 | 0 |

## 逐题对照

| 题目 | legacy C/G/B/L | grounded-v1 C/G/B/L | grounded-v2 C/G/B/L | grounded-v3 C/G/B/L | grounded-v4 C/G/B/L | grounded-v5 C/G/B/L |
|---|---|---|---|---|---|---|
| en-01 | 0/2/2/0 | 0/2/2/0 | 0/2/2/2 | 0/2/2/2 | 0/2/2/2 | 0/2/2/2 |
| en-02 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| en-05 | 2/2/2/0 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| en-08 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| en-13 | 2/2/2/1 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| en-19 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| zh-01 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 1/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| zh-02 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| zh-05 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| zh-08 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| zh-13 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| zh-19 | 1/1/1/2 | 0/2/2/2 | 0/2/2/2 | 0/2/2/2 | 0/2/2/2 | 0/2/2/2 |
| acceptance-zh-gain | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| acceptance-zh-prompts | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| acceptance-zh-products | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| acceptance-zh-examples | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| acceptance-en-gain | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| acceptance-en-prompts | 2/2/2/1 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| acceptance-en-products | 2/2/2/1 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| acceptance-en-examples | 2/2/2/2 | 2/2/2/1 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| boundary-zh-gpu | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| boundary-en-funding | 2/2/2/0 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 0/0/0/2 |
| boundary-zh-premise | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| boundary-en-premise | 2/2/2/1 | 2/2/2/1 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| boundary-zh-partial | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| boundary-en-partial | 2/2/2/0 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| boundary-zh-date | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |
| boundary-en-seed | 2/2/2/0 | 2/2/2/1 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 | 2/2/2/2 |

## 回答与评分理由

### en-01

预期行为为 abstain。参考答案为 Department of Computer Science, Princeton University, and Google Research, Brain team.

**legacy**

根据提供的片段，无法确定作者所属的机构。片段中仅列出了作者姓名和论文信息，没有包含作者的单位或机构信息。

The reference answer specifies 'Department of Computer Science, Princeton University, and Google Research, Brain team,' but the supplied context contains only author names and paper citations with no affiliation information. The answer correctly abstains, stating the affiliations cannot be determined from the excerpt, which is supported by the absence of institutional details in the context. However, correctness is 0 because the factual reference answer is not provided. Behavior is 2 for an appropriate abstention given insufficient context. Language is 0 because the main prose is in Chinese, not the expected English.

**grounded-v1**

资料不足以回答这个问题。提供的文本是参考文献列表和部分实验结果，其中没有给出本文作者的署名信息或其所属机构。

The reference answer specifies the authors' affiliations (Department of Computer Science, Princeton University, and Google Research, Brain team), but the response does not provide these facts; it abstains. The supplied context is a reference list and appendix with no author affiliation block, so the abstention is grounded ("资料不足以回答这个问题"). Behavior is appropriate for expected_behavior=abstain: it explicitly states the missing information without inventing an answer. However, the main prose is in Chinese while expected_language is English, so language=0.

**grounded-v2**

The provided material does not contain an author affiliation list or any statement identifying the institutions the authors are affiliated with. It consists of reference entries, author names, titles, and bibliographic details, but no institutional affiliations. Therefore, the available evidence is insufficient to answer which institutions the authors are affiliated with.

The reference answer specifies 'Department of Computer Science, Princeton University, and Google Research, Brain team,' but the response does not provide these facts. However, the supplied context indeed lacks any affiliation information, so the abstention is appropriate for the retrieved context. Grounding is 2 because the response accurately notes the absence of affiliation data, supported by the context containing only bibliographic entries and author names. Behavior is 2 because the response explicitly acknowledges the missing information and does not speculate. Language is 2 as the main prose is in English.

**grounded-v3**

The provided material does not contain author affiliation information. It consists of reference entries (author names, paper titles, venues, years, URLs) and a results table, none of which state institutional affiliations. Therefore, the institutions cannot be determined from this document.

The reference answer specifies 'Department of Computer Science, Princeton University, and Google Research, Brain team,' but the response abstains, stating affiliations are absent. The context indeed contains only citation entries and a results table with no affiliation statements, so the abstention is grounded and appropriate given the insufficient retrieved context. However, correctness is 0 because the factual reference answer is not provided. Behavior is 2 for a justified abstention with explicit identification of missing information. Language is 2 as the response is in English.

**grounded-v4**

The provided material does not contain any affiliation information for the authors. The excerpts consist of reference entries (author names, paper titles, venues, years, URLs) and a results table, but no institutional affiliations are listed. Therefore, the institutions the authors are affiliated with cannot be determined from this material.

The reference answer specifies 'Department of Computer Science, Princeton University, and Google Research, Brain team,' but the response does not provide these facts. However, the supplied context indeed contains only bibliographic entries and a results table with no affiliation information, so the abstention is grounded and appropriate. The response explicitly acknowledges the missing information, satisfying the expected abstain behavior. Language is English as required.

**grounded-v5**

The provided material does not contain author affiliation information, so the institutions cannot be determined from it.

The reference answer specifies 'Department of Computer Science, Princeton University, and Google Research, Brain team,' but the response abstains, stating the context lacks affiliation information. The context indeed contains only references and author names without affiliations, so the abstention is grounded and appropriate given the supplied context, though it does not provide the factual answer from the reference.

### en-02

预期行为为 answer。参考答案为 HotPotQA, FEVER, ALFWorld, and WebShop.

**legacy**

The four benchmarks used to evaluate ReAct are:

1. **HotPotQA** — question answering (Yang et al., 2018)
2. **Fever** — fact verification (Thorne et al., 2018)
3. **ALFWorld** — text-based game (Shridhar et al., 2020b)
4. **WebShop** — webpage navigation (Yao et al., 2022)

The answer lists exactly the four benchmarks named in the context: 'question answering (HotPotQA, Yang et al., 2018), fact verification (Fever, Thorne et al., 2018), text-based game (ALFWorld, Shridhar et al., 2020b), and webpage navigation (WebShop, Yao et al., 2022).' Each benchmark is correctly paired with its task type and citation, matching the reference answer. The response is direct, fully supported by the context, and written in English.

**grounded-v1**

The four benchmarks are HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

The answer lists exactly the four benchmarks named in the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. All task-to-benchmark mappings are directly supported by the quoted context, and the response is in English.

**grounded-v2**

The four benchmarks used to evaluate ReAct are: **HotPotQA** (question answering), **Fever** (fact verification), **ALFWorld** (text-based game), and **WebShop** (webpage navigation).

The answer lists exactly the four benchmarks named in the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. Each benchmark is correctly paired with its task type, matching the reference answer. All claims are directly supported by the supplied context, the response answers directly as expected, and the prose is in English.

**grounded-v3**

The four benchmarks are HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

The answer lists exactly the four benchmarks named in the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. All task-to-benchmark mappings are directly supported by the quoted context, and the response is in English.

**grounded-v4**

The four benchmarks are HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

The answer lists exactly the four benchmarks named in the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. Each benchmark is correctly paired with its task type, matching the reference answer with no incorrect facts. All claims are directly supported by the supplied context, the response answers directly as expected, and the prose is in English.

**grounded-v5**

The four benchmarks are HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

The answer lists exactly the four benchmarks named in the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. Each benchmark is correctly paired with its task type, matching the reference answer with no incorrect facts. All claims are directly supported by the quoted context, and the response answers directly in English.

### en-05

预期行为为 answer。参考答案为 A thought does not affect the external environment and produces no observation feedback. Actions interact with the external environment.

**legacy**

根据提供的片段，思维（thought）与行动（action）在对外部环境的影响上有明确区别：

**思维（thought / reasoning trace）不影响外部环境。** 片段指出，语言空间中的动作（即思维或推理轨迹）“does not affect the external environment, thus leading to no observation feedback”（不影响外部环境，因此不会产生观察反馈）。思维的作用是通过对当前上下文进行推理来组合有用信息，并更新上下文以支持未来的推理或行动。

**行动（action）则会作用于外部环境。** 片段将思维与“external feedback”（外部反馈）相对照，并提到行动会产生“observation feedback”（观察反馈），说明行动会改变环境并由此获得环境的观察结果。片段还强调“the importance of internal reasoning vs. simple reactions to external feedback”（内部推理相对于简单对外部反馈作出反应的重要性），进一步表明行动是与外部反馈/环境交互的部分，而思维是内部的、不触及环境的。

简言之：思维是内部的、不改变环境、无观察反馈；行动则与外部环境交互并产生观察反馈。

The answer accurately states the reference facts: a thought 'does not affect the external environment, thus leading to no observation feedback,' while actions interact with the external environment and yield observation feedback, supported by context quotes contrasting 'internal reasoning vs. simple reactions to external feedback.' However, the main explanatory prose is in Chinese, not the expected language (en), so language=0.

**grounded-v1**

A thought differs from an action in that a thought (a reasoning trace in the language space) **does not affect the external environment**, so it produces **no observation feedback**. Instead, a thought composes useful information by reasoning over the current context and updates the context to support future reasoning or acting. This is contrasted with actions, which do affect the external environment and yield observations.

The answer accurately reflects the reference: a thought does not affect the external environment and produces no observation feedback, while actions interact with the environment. It is directly supported by the context: 'An action ... in the language space, which we will refer to as a thought or a reasoning trace, does not affect the external environment, thus leading to no observation feedback.' The contrast with actions affecting the environment is a faithful inference from the setup where actions yield observations.

**grounded-v2**

According to the material, an action in the language space — referred to as a thought or reasoning trace — "does not affect the external environment, thus leading to no observation feedback." Instead, a thought composes useful information by reasoning over the current context and updates the context to support future reasoning or acting. So a thought affects only the internal context, whereas the material's contrast implies actions do affect the external environment (since thoughts are distinguished by not doing so and by producing no observation feedback).

The material does not further specify the exact mechanism or extent of an action's effect on the environment beyond this contrast.

The answer accurately captures the reference distinction: a thought 'does not affect the external environment, thus leading to no observation feedback,' while actions are contrasted as affecting the external environment. It also correctly notes the material does not specify the exact mechanism of an action's environmental effect, which is a faithful acknowledgment of the context's limits. All factual claims are supported by the quoted context.

**grounded-v3**

According to the document, a thought (an action in the language space L, also called a reasoning trace) "does not affect the external environment, thus leading to no observation feedback." Instead, it composes useful information by reasoning over the current context and updates the context to support future reasoning or acting. By contrast, actions in the action space A are taken in the environment and produce observation feedback (the context includes observations o_t received from the environment).

The answer accurately reflects the reference: thoughts 'does not affect the external environment, thus leading to no observation feedback' while actions interact with the environment and produce observations. Both claims are directly supported by context quotes: 'An action ˆat ∈L in the language space, which we will refer to as a thought or a reasoning trace, does not affect the external environment, thus leading to no observation feedback' and 'an agent receives an observation ot ∈O from the environment and takes an action at ∈A'. The answer directly addresses the question with no unsupported extras.

**grounded-v4**

According to the document, an action in the language space (referred to as a thought or reasoning trace) "does not affect the external environment, thus leading to no observation feedback." Instead, a thought composes useful information by reasoning over the current context and updates the context to support future reasoning or acting. In contrast, actions (in the regular action space A) are what the agent takes in the environment, and the environment returns observations in response—so actions do affect the external environment and produce observation feedback.

The document does not provide further detail beyond this distinction.

The answer accurately captures the reference distinction: a thought 'does not affect the external environment, thus leading to no observation feedback,' while actions interact with the environment and yield observations. The contrast drawn for actions is a faithful paraphrase of the context's action-observation loop ('receives an observation ot ... and takes an action at'). The closing note that the document provides no further detail is a supported acknowledgement of scope.

**grounded-v5**

According to the document, a thought (or reasoning trace) is an action in the language space L that "does not affect the external environment, thus leading to no observation feedback." Instead, it composes useful information by reasoning over the current context and updates the context to support future reasoning or acting. By contrast, (regular) actions are drawn from the action space A and interact with the environment, producing observation feedback (the context includes observations o_t received from the environment after actions).

In short: a thought has no effect on the external environment and yields no observation, while an action affects the environment and leads to observation feedback.

The answer accurately reflects the reference: a thought 'does not affect the external environment, thus leading to no observation feedback,' while actions interact with the environment and produce observations. All claims are directly supported by the quoted context, including the definition of thoughts in language space L and the context update mechanism. The response directly answers the question with no unsupported additions.

### en-08

预期行为为 answer。参考答案为 The browser Ctrl+F find functionality.

**legacy**

The lookup action simulates Ctrl+F functionality on the browser — it returns the next sentence in the page containing the given string.

The answer directly matches the reference: context states 'lookup[string], which would return the next sentence in the page containing string, simulating Ctrl+F functionality on the browser.' Both the Ctrl+F simulation and the next-sentence behavior are explicitly supported.

**grounded-v1**

The lookup action simulates Ctrl+F functionality on the browser.

The answer directly matches the reference and is explicitly supported by the context: 'lookup[string], which would return the next sentence in the page containing string, simulating Ctrl+F functionality on the browser.' No unsupported claims are present.

**grounded-v2**

The lookup[string] action simulates Ctrl+F functionality on the browser.

The answer directly and accurately states that lookup[string] simulates Ctrl+F browser functionality, matching the reference. The context explicitly supports this: 'lookup[string], which would return the next sentence in the page containing string, simulating Ctrl+F functionality on the browser.' No unsupported claims are present.

**grounded-v3**

The lookup action simulates Ctrl+F functionality on the browser. The document states that `lookup[string]` "would return the next sentence in the page containing string, simulating Ctrl+F functionality on the browser."

The answer accurately states that lookup simulates Ctrl+F browser functionality, directly supported by the context: 'lookup[string], which would return the next sentence in the page containing string, simulating Ctrl+F functionality on the browser.' The answer is concise, in English, and directly addresses the question.

**grounded-v4**

The lookup[string] action simulates Ctrl+F functionality on the browser.

The answer directly and accurately states that lookup[string] simulates Ctrl+F browser functionality, matching the reference. The context explicitly supports this: 'lookup[string], which would return the next sentence in the page containing string, simulating Ctrl+F functionality on the browser.' No unsupported claims are present.

**grounded-v5**

The lookup action simulates Ctrl+F functionality on the browser.

The answer directly and accurately states that lookup[string] simulates Ctrl+F functionality on the browser, matching the reference. The context explicitly supports this: 'lookup[string], which would return the next sentence in the page containing string, simulating Ctrl+F functionality on the browser.' No unsupported claims are present.

### en-13

预期行为为 answer。参考答案为 134 unseen evaluation games.

**legacy**

根据提供的片段，ALFWorld 中使用了 **134 个未见过的评估游戏（134 unseen evaluation games）** 进行评估。片段中明确提到：“Following Shridhar et al. (2020b), we evaluate on 134 unseen evaluation games in a task-specific setup.” 以及 “On ALFWorld, we use all 134 unseen validation task instances”。

The answer correctly states 134 unseen evaluation games, matching the reference and directly quoting the context: 'we evaluate on 134 unseen evaluation games in a task-specific setup' and 'we use all 134 unseen validation task instances'. Grounding is fully supported. However, the main explanatory prose is in Chinese rather than the expected English, though the key quoted evidence remains in English; the requested language is not dominant, so language=1.

**grounded-v1**

134 unseen evaluation games were used in ALFWorld, according to the document.

The answer states 134 unseen evaluation games, matching the reference. The context explicitly supports this: 'we evaluate on 134 unseen evaluation games in a task-specific setup' and 'we use all 134 unseen validation task instances.' The response directly answers the question in English with no unsupported claims.

**grounded-v2**

134 unseen evaluation games were used in ALFWorld. The document states: "we evaluate on 134 unseen evaluation games in a task-specific setup," and later, "we use all 134 unseen validation task instances."

The answer correctly states 134 unseen evaluation games, matching the reference. It is directly supported by context quotations: 'we evaluate on 134 unseen evaluation games in a task-specific setup' and 'we use all 134 unseen validation task instances.' The response answers directly in English with no unsupported claims.

**grounded-v3**

134 unseen evaluation games were used in ALFWorld. The document states: "we evaluate on 134 unseen evaluation games in a task-specific setup" and "we use all 134 unseen validation task instances."

The answer directly states 134 unseen evaluation games, matching the reference. It is supported by context quotations: 'we evaluate on 134 unseen evaluation games in a task-specific setup' and 'we use all 134 unseen validation task instances.' The response is in English and directly answers the question.

**grounded-v4**

134 unseen evaluation games were used in ALFWorld.

The answer states 134 unseen evaluation games, matching the reference and directly supported by context: 'we evaluate on 134 unseen evaluation games in a task-specific setup.' The response is concise, in English, and directly answers the question.

**grounded-v5**

134 unseen evaluation games were used in ALFWorld.

The answer directly states '134 unseen evaluation games,' matching the reference. The context explicitly supports this: 'we evaluate on 134 unseen evaluation games in a task-specific setup' and 'we use all 134 unseen validation task instances.' No unsupported claims are present.

### en-19

预期行为为 answer。参考答案为 Act uses the same trajectories with thoughts removed. Task instances are randomly selected from the training set, favoring neither method.

**legacy**

The authors made the ReAct-versus-Act comparison fair and controlled by constructing the Act prompts from the same annotated trajectories used for ReAct, but removing the thoughts. Specifically, they annotated three trajectories per task type (with sparse thoughts) and built 6 prompts per task type through permutations of 2 of those 3 trajectories; the Act prompts used the same trajectories “but without thoughts.” They also note that task instances were randomly chosen from the training set, so the setup “favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts.”

The answer accurately captures both reference facts: Act prompts use the same trajectories without thoughts ('Act prompts are constructed using the same trajectories, but without thoughts') and task instances are randomly chosen from the training set ('since task instances are randomly chosen from the training set, it favors neither ReAct nor Act and provides a fair and controlled comparison'). The additional detail about 6 prompts from permutations of 2 of 3 trajectories is directly supported by the context ('we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate'). All claims are grounded in the supplied context, the response directly answers the question, and it is in English.

**grounded-v1**

The authors made the ReAct-versus-Act comparison fair and controlled in the ALFWorld setup by constructing **Act prompts from the same annotated trajectories as ReAct, but without the thoughts**. They also note that task instances were **randomly chosen from the training set**, so the setup “favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts.” Additionally, for robustness they constructed **6 prompts for each task type** via permutations of **2 annotated trajectories from the 3 they annotate**, and the ReAct-vs-Act advantage was reported as consistent across **six controlled trials**.

The answer accurately reflects the reference: Act prompts use the same trajectories without thoughts ('Act prompts are constructed using the same trajectories, but without thoughts') and task instances are randomly chosen from the training set ('since task instances are randomly chosen from the training set, it favors neither ReAct nor Act and provides a fair and controlled comparison'). The additional details about 6 prompts from permutations of 2 of 3 trajectories and six controlled trials are directly supported by the context ('we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate'; 'consistent across six controlled trials'). All claims are grounded, the answer is direct and complete, and it is in English.

**grounded-v2**

The authors made the ReAct-versus-Act comparison fair and controlled by constructing **Act prompts from the same annotated trajectories as ReAct, but without the thoughts**. The document states that "Act prompts are constructed using the same trajectories, but without thoughts," and that because task instances are randomly chosen from the training set, this "favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts."

The document also refers to the ReAct advantage over Act being "consistent across six controlled trials," but it does not provide further details on how those six trials were controlled beyond the matched-trajectory prompt construction described above.

The answer accurately captures both required facts from the reference: Act prompts use the same trajectories with thoughts removed ('Act prompts are constructed using the same trajectories, but without thoughts'), and task instances are randomly chosen from the training set, favoring neither method ('since task instances are randomly chosen from the training set, it favors neither ReAct nor Act and provides a fair and controlled comparison'). It also correctly notes the six controlled trials without overclaiming details. All claims are directly supported by the context.

**grounded-v3**

The authors made the ReAct-versus-Act comparison fair and controlled by constructing **Act prompts from the same annotated trajectories as ReAct, but without the thoughts**. The document states that task instances were randomly chosen from the training set, so this "favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts." It also reports the ReAct advantage over Act was "consistent across six controlled trials."

The answer accurately captures both required facts from the reference: Act prompts use the same trajectories with thoughts removed ('Act prompts are constructed using the same trajectories, but without thoughts'), and task instances are randomly chosen from the training set ('since task instances are randomly chosen from the training set, it favors neither ReAct nor Act and provides a fair and controlled comparison'). The additional mention of 'six controlled trials' is also directly supported by the context ('consistent across six controlled trials'). All claims are grounded in the supplied context, the response directly answers the question, and the prose is in English.

**grounded-v4**

The authors made the ReAct-versus-Act comparison fair and controlled by constructing the Act prompts from the same annotated trajectories used for ReAct, but without the thoughts. They state that task instances are randomly chosen from the training set, so this favors neither ReAct nor Act, providing a fair and controlled comparison to test the importance of sparse thoughts.

The answer accurately reproduces both reference facts: 'Act prompts are constructed using the same trajectories, but without thoughts' and 'task instances are randomly chosen from the training set, it favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts.' Both are directly quoted/paraphrased from the context, so grounding is full and no unsupported claims are present.

**grounded-v5**

The authors made the ReAct-versus-Act comparison fair and controlled in the following ways, based on the provided material:

- **Same annotated trajectories:** Act prompts were "constructed using the same trajectories" as ReAct, but "without thoughts."
- **Random task-instance selection:** Task instances were "randomly chosen from the training set," which the authors state "favors neither ReAct nor Act and provides a fair and controlled comparison to test the importance of sparse thoughts."
- **Multiple controlled trials:** The advantage was reported as "consistent across six controlled trials."

The material does not provide further details on other control procedures beyond these points.

The answer accurately captures both required facts from the reference: Act prompts use the same trajectories without thoughts ('Act prompts are constructed using the same trajectories, but without thoughts'), and task instances are randomly chosen from the training set ('task instances are randomly chosen from the training set, it favors neither ReAct nor Act and provides a fair and controlled comparison'). The additional point about six controlled trials is directly supported by context ('consistent across six controlled trials'). All claims are grounded in the supplied context, the answer directly addresses the question, and the prose is in English.

### zh-01

预期行为为 answer。参考答案为 普林斯顿大学计算机科学系和 Google Research 的 Brain team。

**legacy**

根据提供的片段，论文《REACT：协同推理和行动》的作者机构信息如下：

- **Shunyu Yao、Karthik Narasimhan**：普林斯顿大学计算机科学系（Princeton University, Department of Computer Science）
- **Jeffrey Zhao、Dian Yu、Nan Du、Izhak Shafran、Yuan Cao**：谷歌研究大脑团队（Google Research, Brain Team）

片段中明确标注了作者 affiliation 为：
1. 普林斯顿大学计算机科学系
2. 谷歌研究，大脑团队

其他引用文献的作者机构信息在片段中未完整提供，无法准确回答。

回答准确对应参考事实：普林斯顿大学计算机科学系和 Google Research 的 Brain team。上下文明确列出“1 普林斯顿大学计算机科学系”和“2 谷歌研究，大脑团队”，并给出作者与机构对应关系。回答还恰当说明其他引用文献的机构信息未完整提供，未编造缺失信息。

**grounded-v1**

资料中能明确对应到论文《ReAct: Synergizing Reasoning and Acting in Language Models》（ICLR 2023）作者机构的信息是：作者署名中标注了 **1 普林斯顿大学计算机科学系** 和 **2 谷歌研究，大脑团队**。因此，该论文作者分别来自普林斯顿大学计算机科学系和谷歌研究大脑团队。

资料中其他文献的作者机构信息不完整，无法据此逐一列出所有作者的机构。

回答准确给出参考中的两个机构：普林斯顿大学计算机科学系和 Google Research 的 Brain team，并对应到 ReAct 论文。上下文明确支持：“1 普林斯顿大学计算机科学系”和“2 谷歌研究，大脑团队”。回答还说明其他文献机构信息不完整，未编造额外机构。

**grounded-v2**

资料中能明确支持的是 ReAct 论文作者所属机构：**普林斯顿大学计算机科学系**和**谷歌研究，大脑团队（Google Research, Brain Team）**。作者列表为 Shunyu Yao、Jeffrey Zhao、Dian Yu、Nan Du、Izhak Shafran、Karthik Narasimhan、Yuan Cao，其中标注 1 的隶属普林斯顿大学计算机科学系，标注 2 的隶属谷歌研究大脑团队。

资料没有给出所列举的其他参考文献作者（如 Antonia Creswell、Murray Shanahan 等）的机构信息，因此无法据此回答“论文作者分别来自哪些机构”中涉及这些文献作者的部分。

回答准确给出参考中的机构：普林斯顿大学计算机科学系和 Google Research 的 Brain team，并对应到 ReAct 论文作者；上下文明确写有“1 普林斯顿大学计算机科学系”“2 谷歌研究，大脑团队”。回答还恰当说明其他参考文献作者机构未在资料中给出，未编造。

**grounded-v3**

资料只支持论文《REACT:协同推理和行动》的作者机构信息：作者署名中标注“1 普林斯顿大学计算机科学系”和“2 谷歌研究，大脑团队”。资料没有给出该论文每位作者分别对应哪个机构，也没有提供其他论文的作者机构信息，因此无法回答“论文作者分别来自哪些机构”中逐位作者的归属。

回答正确指出资料中出现的两个机构（“1 普林斯顿大学计算机科学系”和“2 谷歌研究，大脑团队”），与参考答案的机构集合一致；但未按参考答案直接给出“普林斯顿大学计算机科学系和 Google Research 的 Brain team”作为答案，而是以无法逐位归属为由未完成回答，因此只部分满足参考事实。其关于资料未给出逐位作者归属的说明有上下文支持（署名仅列机构编号与作者列表），无额外无据主张。

**grounded-v4**

资料中能明确对应到论文作者机构的信息只有一处：题为“REACT:协同推理和行动”的论文（Published as a conference paper at ICLR 2023）标注作者机构为：

- 普林斯顿大学计算机科学系（1）
- 谷歌研究，大脑团队（2）

资料中其他参考文献条目未标明作者所属机构，因此无法据此列出这些文献作者的机构。

回答准确给出参考中的两个机构：'普林斯顿大学计算机科学系'和'谷歌研究，大脑团队'，与上下文标注一致（'1 普林斯顿大学计算机科学系'、'2 谷歌研究，大脑团队'）。回答还明确说明其他文献未标明机构，属于对缺失信息的恰当说明，未编造额外机构。

**grounded-v5**

资料中明确列出的作者机构为：普林斯顿大学计算机科学系、谷歌研究大脑团队。

回答准确对应参考事实：作者机构为普林斯顿大学计算机科学系和 Google Research 的 Brain team。上下文明确列出“1 普林斯顿大学计算机科学系”和“2 谷歌研究，大脑团队”，支持该答案。回答直接、无多余推测，语言为中文。

### zh-02

预期行为为 answer。参考答案为 HotPotQA、FEVER、ALFWorld 和 WebShop。

**legacy**

根据片段内容，论文用了以下四个基准来评测 ReAct：

1. **问答**：HotPotQA（Yang et al., 2018）
2. **事实验证**：Fever（Thorne et al., 2018）
3. **基于文本的游戏**：ALFWorld（Shridhar et al., 2020b）
4. **网页导航**：WebShop（Yao et al., 2022）

回答准确列出四个基准：HotPotQA、Fever、ALFWorld、WebShop，与参考一致。上下文明确支持：'我们在四个不同的基准上对ReAct 和最先进的基线进行了实证评估:问答(HotPotQA，Yang et al.,2018)、事实验证(发烧、Thorne et al.,2018),基于文本的游戏(ALFWorld，Shridhar et al.,2020b),和网页导航( 网络商店，Yaoet al.,2022)'。回答直接、无多余推测，中文表述。

**grounded-v1**

资料中明确提到的四个基准是：HotPotQA（问答）、FEVER（事实验证）、ALFWorld（基于文本的游戏）、WebShop（网页导航）。

回答准确列出参考中的四个基准并附任务类型，均可在上下文中找到支持：'问答(HotPotQA...)、事实验证(发烧/Thorne...)、基于文本的游戏(ALFWorld...)'以及'网页导航(网络商店，Yao et al.,2022)'，且后文明确'ALFWorld 和WebShop'。无额外无据主张。

**grounded-v2**

根据资料，论文用以下四个基准评测 ReAct：

1. 问答：HotPotQA
2. 事实验证：Fever（资料中写作“发烧”）
3. 基于文本的游戏：ALFWorld
4. 网页导航：WebShop

资料明确写道：“我们在四个不同的基准上对ReAct 和最先进的基线进行了实证评估：问答(HotPotQA，Yang et al.,2018)、事实验证(发烧、Thorne et al.,2018),基于文本的游戏(ALFWorld，Shridhar et al.,2020b),和网页导航(网络商店，Yao et al.,2022)。”

答案准确列出四个基准 HotPotQA、FEVER（资料中译为“发烧”）、ALFWorld 和 WebShop，与参考一致。上下文明确写道“我们在四个不同的基准上对ReAct 和最先进的基线进行了实证评估:问答(HotPotQA...)、事实验证(发烧...)、基于文本的游戏(ALFWorld...),和网页导航(网络商店...)”，并多处提及 ALFWorld 和 WebShop，支持全部事实。回答直接、无臆造，中文表述。

**grounded-v3**

资料中明确提到的四个基准是：问答（HotPotQA，Yang et al., 2018）、事实验证（Fever，Thorne et al., 2018）、基于文本的游戏（ALFWorld，Shridhar et al., 2020b）和网页导航（WebShop，Yao et al., 2022）。

回答准确列出四个基准：HotPotQA、Fever、ALFWorld、WebShop，与参考一致。上下文明确支持：“问答(HotPotQA，Yang et al.,2018)、事实验证(发烧、Thorne et al.,2018),基于文本的游戏(ALFWorld，Shridhar et al.,2020b),和网页导航(网络商店，Yao et al.,2022)”。回答直接、无多余推测，中文表述。

**grounded-v4**

资料中明确列出的四个基准是：问答（HotPotQA）、事实验证（Fever）、基于文本的游戏（ALFWorld）、网页导航（WebShop）。

回答准确列出四个基准：HotPotQA、Fever、ALFWorld、WebShop，与参考一致。上下文明确支持：'问答(HotPotQA，Yang et al.,2018)、事实验证(发烧、Thorne et al.,2018),基于文本的游戏(ALFWorld，Shridhar et al.,2020b),和网页导航(网络商店，Yao et al.,2022)'。回答直接、无多余推测，中文表述。

**grounded-v5**

资料中明确提到的四个基准是：HotPotQA（问答）、Fever（事实验证）、ALFWorld（基于文本的游戏）和WebShop（网页导航）。

回答准确列出四个基准：HotPotQA、Fever、ALFWorld、WebShop，与参考一致。上下文明确支持：'问答(HotPotQA，Yang et al.,2018)、事实验证(发烧、Thorne et al.,2018),基于文本的游戏(ALFWorld，Shridhar et al.,2020b),和网页导航(网络商店，Yao et al.,2022)'，其中'发烧'为FEVER的翻译、'网络商店'为WebShop的翻译，属忠实翻译。回答直接、无多余推测，中文表述。

### zh-05

预期行为为 answer。参考答案为 思想不改变外部环境，因此没有环境观察反馈。行动用于与外部环境交互。

**legacy**

根据提供的片段，思想（thought）与行动（action）在对环境的影响上的区别主要体现在：

1. **行动会影响外部环境**：行动是代理在外部动作空间A中采取的操作，会作用于轨迹环境，并产生观察反馈（片段中提到“行动4”需要对轨迹环境进行复杂推理，以及代理因未能理解环境中的物体关系而产生幻觉行为）。

2. **思想不影响外部环境**：片段明确指出，语言空间中的动作（即思想或推理轨迹）“不影响外部环境，从而导致没有观察反馈”。思想的作用是通过对当前上下文进行推理来组成有用信息，并更新上下文以支持未来的推理或行动，例如分解任务目标、创建行动计划、注入常识知识、提取观察中的重要部分、跟踪进展、处理异常并调整计划等。

简言之：行动对外部环境产生实际作用并引发观察反馈；思想仅在内部上下文层面进行推理和更新，不改变外部环境，也不产生观察反馈。

回答准确区分了思想与行动：引用“思想或推理轨迹，不影响外部环境，从而导致没有观察反馈”，并说明行动作用于轨迹环境、产生观察反馈，与参考一致。所有事实性主张均有上下文支持，如“行动4”需对轨迹环境复杂推理、思想更新上下文以支持未来推理或行动。回答直接、无臆造，语言为中文。

**grounded-v1**

资料明确说明：语言空间中的动作（即“思想/推理轨迹”）**不影响外部环境**，因此没有观察反馈；而（外部）行动会作用于环境并产生观察反馈。资料还指出，思想旨在通过对当前上下文推理来组成有用信息并更新上下文，以支持未来推理或行动。

资料未进一步具体说明行动对环境造成影响的具体形式或机制。

回答准确复述了参考要点：思想（语言空间动作）'不影响外部环境，从而导致没有观察反馈'，而行动用于与环境交互并产生观察反馈；并补充思想更新上下文以支持未来推理或行动，均见上下文'语言空间中的动作aˇt∈L，我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈'及'思想at 旨在通过对当前上下文ct 进行推理来组成有用的信息，并更新上下文ct+1'。回答还明确说明资料未具体说明行动影响环境的具体机制，边界清晰，无编造。

**grounded-v2**

资料明确指出：语言空间中的动作（思想/推理轨迹）“不影响外部环境，从而导致没有观察反馈”；相反，思想旨在对当前上下文进行推理、组成有用信息并更新上下文，以支持未来的推理或行动。资料还提到“内部推理与外部反馈”的区别，但未进一步展开行动对环境的具体影响机制。因此，可支持的答案是：思想不改变外部环境、不产生观察反馈，只更新内部上下文；关于行动如何具体改变环境，资料依据不足。

回答准确复述了参考要点：思想“不影响外部环境，从而导致没有观察反馈”，并说明思想更新上下文以支持未来推理或行动；同时指出资料未展开行动对环境的具体影响机制，属于对缺失信息的恰当说明。所有事实性表述均可由上下文直接支持，未引入外部知识。

**grounded-v3**

资料明确区分了二者：思想（thought）是语言空间中的动作，**不影响外部环境，因此没有观察反馈**；思想的作用是对当前上下文进行推理、组成有用信息，并更新上下文以支持未来的推理或行动。行动（action）则是在环境中执行的动作，会作用于外部环境并产生观察结果（资料中轨迹由“思想-行动-观察”步骤组成，说明行动后会有环境观察反馈）。

依据片段：“语言空间中的动作……我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈。”

回答准确复述了参考要点：思想不影响外部环境、无观察反馈，行动用于与外部环境交互并产生观察。依据上下文“语言空间中的动作……我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈”以及“思想at 旨在通过对当前上下文ct 进行推理来组成有用的信息，并更新上下文”，均得到支持。回答直接、无臆造，语言为中文。

**grounded-v4**

思想不影响外部环境，也不产生观察反馈；行动则作用于外部环境。资料指出，语言空间中的动作（即思想或推理轨迹）“不影响外部环境，从而导致没有观察反馈”。思想的作用是对当前上下文进行推理、组成有用信息并更新上下文，以支持未来的推理或行动。

回答准确区分了思想与行动：思想不改变外部环境、无观察反馈，行动作用于外部环境，与参考一致。引用上下文“不影响外部环境，从而导致没有观察反馈”直接支持该说法；关于思想更新上下文以支持未来推理或行动也由“更新上下文ct+1=(ct，at)以支持未来的推理或行动”支持。

**grounded-v5**

资料中明确指出的区别是：思想（thought）或推理轨迹属于语言空间中的动作，**不影响外部环境，因此不会产生观察反馈**；而行动（action）作用于环境，会带来环境观察。思想的作用是对当前上下文进行推理、组成有用信息并更新上下文，以支持未来的推理或行动。

资料未进一步说明行动对环境造成的具体影响类型或程度。

回答准确复述了上下文的核心区别：'语言空间中的动作aˇt∈L，我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈'，并说明思想更新上下文以支持未来推理或行动（'更新上下文ct+1=(ct，at)以支持未来的推理或行动'）。对行动作用于环境、产生观察的表述与上下文一致（行动与观察交替出现）。回答还明确说明资料未进一步说明行动的具体影响类型，属于对缺失信息的恰当承认，无编造内容。

### zh-08

预期行为为 answer。参考答案为 浏览器的 Ctrl+F 文本查找功能。

**legacy**

根据相关片段，lookup[string] 动作模拟的是浏览器上的 **Ctrl+F** 功能，即查找页面中包含指定字符串的下一个句子。

回答准确指出 lookup[string] 模拟浏览器 Ctrl+F 功能，与参考一致；上下文明确支持：“lookup[string]，它将返回包含 string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能”；回答直接、无多余推测，主语言为中文。

**grounded-v1**

资料明确提到：lookup[string]“模拟浏览器上的Ctrl+F功能”。因此，lookup 动作模拟的是浏览器的 **Ctrl+F（页内查找）功能**。

回答准确指出 lookup 模拟浏览器 Ctrl+F 功能，与参考一致；上下文明确支持：'lookup[string]，它将返回包含 string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能'。回答直接、无多余推测，主语言为中文。

**grounded-v2**

lookup[string] 动作模拟的是浏览器上的 Ctrl+F 功能（即在页面中查找字符串并返回包含该 string 的下一个句子）。

答案准确对应参考事实：lookup 模拟浏览器 Ctrl+F 文本查找功能。上下文明确支持：“lookup[string]，它将返回包含 string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能。” 回答直接、无多余推测，且使用中文。

**grounded-v3**

lookup[string] 模拟的是浏览器上的 Ctrl+F 功能。资料原文为：“lookup[string]，它将返回包含 string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能。”

答案准确指出 lookup 动作模拟浏览器 Ctrl+F 功能，与参考一致；上下文明确支持：“lookup[string]，它将返回包含 string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能。”回答直接、无多余推测，主语言为中文。

**grounded-v4**

lookup[string] 动作模拟的是浏览器上的 Ctrl+F 功能，即查找页面中包含指定字符串的下一个句子。

答案准确对应参考事实：上下文明确写道“lookup[string]，它将返回包含string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能”，答案复述了该功能并补充了查找下一个句子的细节，均有上下文支持。

**grounded-v5**

资料明确说明：lookup[string] 模拟浏览器上的 Ctrl+F 功能。

回答准确指出 lookup 模拟浏览器 Ctrl+F 功能，与参考一致；上下文明确支持：“lookup[string]，它将返回包含 string 的页面中的下一个句子，模拟浏览器上的Ctrl+F 功能。” 回答直接、无多余推测，语言为中文。

### zh-13

预期行为为 answer。参考答案为 134 个未见过的评测游戏。

**legacy**

根据提供的片段，ALFWorld 使用了 **134 个未见过的评测游戏**（片段中明确提到“我们在一个特定任务的设置中评估了134 个看不见的评估游戏”，以及“我们使用所有134 个不可见的验证任务实例”）。

回答准确给出 134 个未见过的评测游戏，与参考一致；上下文明确支持：“我们在一个特定任务的设置中评估了134 个看不见的评估游戏”及“我们使用所有134 个不可见的验证任务实例”。回答直接、无多余推测，主语言为中文。

**grounded-v1**

资料显示 ALFWorld 使用了 **134 个未见过的评测游戏**（文中一处称“134 个看不见的评估游戏”，另一处称“所有 134 个不可见的验证任务实例”）。

回答准确给出 134 个未见过的评测游戏，与参考一致；上下文明确支持：“我们在一个特定任务的设置中评估了134 个看不见的评估游戏”及“我们使用所有134 个不可见的验证任务实例”。回答直接、无多余推测，主语言为中文。

**grounded-v2**

资料显示：ALFWorld 使用了 **134 个未见过的评测游戏**（文中表述为“134 个看不见的评估游戏”/“134 个不可见的验证任务实例”）。

回答准确给出 134 个未见过的评测游戏，与参考一致；上下文明确支持：“我们在一个特定任务的设置中评估了134 个看不见的评估游戏”以及“我们使用所有134 个不可见的验证任务实例”。回答直接、无多余推测，主语言为中文。

**grounded-v3**

资料显示 ALFWorld 使用了 **134 个未见过的评测游戏**（“134 个看不见的评估游戏”；另处称“所有 134 个不可见的验证任务实例”）。

回答准确给出 134 个未见过的评测游戏，与参考一致；上下文明确支持：“我们在一个特定任务的设置中评估了134 个看不见的评估游戏”及“我们使用所有134 个不可见的验证任务实例”。回答直接、无多余推测，主语言为中文。

**grounded-v4**

资料显示，ALFWorld 使用了 **134 个未见过的评测游戏**（也称“134 个不可见的验证任务实例”）。

回答准确给出 134 个未见过的评测游戏，与参考一致；上下文明确支持：“我们在一个特定任务的设置中评估了134 个看不见的评估游戏”以及“我们使用所有134 个不可见的验证任务实例”。回答直接、无多余推测，主语言为中文。

**grounded-v5**

资料显示 ALFWorld 使用了 **134 个未见过的评测游戏**（文中一处称“134 个看不见的评估游戏”，另一处称“所有 134 个不可见的验证任务实例”）。

回答准确给出 134 个未见过的评测游戏，与参考一致；上下文明确支持：“我们在一个特定任务的设置中评估了134 个看不见的评估游戏”及“我们使用所有134 个不可见的验证任务实例”。回答直接、无多余推测，主语言为中文。

### zh-19

预期行为为 abstain。参考答案为 Act 使用相同轨迹但移除思想，任务实例从训练集随机选择，使比较不偏向任一方法。

**legacy**

根据片段内容，作者为让 ReAct 与仅行动版本的对比算得上公平的受控实验，主要做了以下安排：

1. **设置“仅行动”的受控基线**：片段明确提到展示了“稀疏、通用的推理在决策中的重要性，表现出相对于只有行动的受控基线的持续优势”，即把仅执行动作生成的版本作为受控基线来对比。

2. **在相同基准和少量学习设置下进行广泛实验**：作者“在不同的基准上进行广泛的实验，以展示 ReAct 在少量学习设置中相对于孤立地执行推理或动作生成的现有方法的优势”，说明对比是在相同基准、相同少量学习条件下与“孤立地执行推理或动作生成”的方法进行比较。

3. **进行系统的消融和分析**：作者“提出了系统的消融和分析，以理解在推理任务中行动的重要性，以及在交互任务中推理的重要性”，通过消融分别考察推理与行动各自的作用，从而支撑 ReAct 与仅行动版本的公平对比。

4. **控制提示与模型设置的一致性**：在 GPT-3 补充实验中，作者说明在 ALFWorld 上“使用根据 PaLM-540B 设置的最佳提示”，并在 HotpotQA 上随机抽取 500 个验证问题子集，体现了对提示设置和评测子集的控制，以保证不同模型/版本间对比的一致性。

5. **结合 CoT 作为对照与组合基线**：片段提到 ReAct 在 HotPotQA 和 Fever 上“优于普通的动作生成模型，同时与思维链推理（CoT）具有竞争力”，并指出“最好的方法是将 ReAct 和 CoT 结合起来”，说明作者也把纯推理（CoT）和纯行动（Act）作为对照，形成推理、行动及二者结合的完整对比框架。

综上，作者通过设立仅行动的受控基线、在相同基准与少量学习设置下比较、系统消融分析推理与行动的作用、控制提示与评测子集设置，以及与 CoT 等对照方法并列比较，使 ReAct 与仅行动版本的对比成为公平的受控实验。

参考要求的关键事实是：Act 使用相同轨迹但移除思想，任务实例从训练集随机选择，使比较不偏向任一方法。回答没有给出这两项核心安排（相同轨迹移除思想、从训练集随机选择任务实例），只泛泛提到“只有行动的受控基线”“相同基准和少量学习设置”“消融分析”等，属于部分相关但未命中参考要点。上下文确实支持“相对于只有行动的受控基线的持续优势”（“表现出相对于只有行动的受控基线的持续优势”）以及“系统的消融和分析”，但未支持“相同轨迹但移除思想”或“任务实例从训练集随机选择”。回答还加入了“控制提示与模型设置的一致性”“随机抽取500个验证问题子集”等细节，其中随机抽取500个验证问题子集有上下文依据（“我们随机抽取了500个验证问题的子集”），但把它解释为公平受控实验安排属于额外推断；将 CoT 作为对照与组合基线也有一定上下文依据（“与思维链推理(CoT)具有竞争力”“最好的方法是将ReAct 和CoT 结合起来”），但整体仍把未支持的安排包装成答案。行为上未明确承认缺失关键信息，而是给出看似完整的五点总结，边界不清。语言为中文，符合要求。

**grounded-v1**

资料不足以回答该问题。资料提到 ReAct 在 ALFWorld 和 WebShop 上“两次甚至一次的 ReAct 提示能够优于用 10³–10⁵ 个任务实例训练的模仿或强化学习方法”，并称其为“相对于只有行动的受控基线”的优势，还提到“系统的消融和分析，以理解在推理任务中行动的重要性，以及在交互任务中推理的重要性”。但资料没有具体说明作者为让 ReAct 与“仅行动版本”的对比成为公平受控实验做了哪些安排（例如是否匹配提示数量、演示样例数、模型、解码设置、动作空间或评测任务等）。因此，缺少可用于回答该问题的具体实验控制信息。

The reference answer requires three specific facts: Act uses the same trajectories but removes thoughts, task instances are randomly sampled from the training set, and the comparison is not biased toward either method. The answer abstains, stating the context lacks details on the experimental controls. The context does mention a 'controlled baseline with only actions' and 'systematic ablations' but does not state the same-trajectory-minus-thoughts design or random sampling from the training set. Thus the abstention is grounded and appropriate given the supplied context, but it does not provide the required factual answer, so correctness=0. Grounding=2 because the answer accurately notes the absence of the specific control details and quotes only supported claims. Behavior=2 because expected_behavior is abstain and the answer explicitly identifies the missing information without speculating. Language=2 because the main prose is in Chinese.

**grounded-v2**

资料不足以完整回答“作者做了哪些安排，才让 ReAct 与仅行动版本的对比算得上是公平的受控实验”。资料中只能确认以下几点相关依据：

1. 资料提到 ReAct 在少量学习设置中与“孤立地执行推理或动作生成的现有方法”比较，并称其“持续优于仅跨不同领域推理或行动的基线”；但这只是比较对象的描述，没有列出公平性安排。
2. 资料提到“系统的消融和分析，以理解在推理任务中行动的重要性，以及在交互任务中推理的重要性”，说明作者做了消融分析，但未说明消融如何控制变量。
3. 资料提到在 ALFWorld 上使用“所有134个不可见的验证任务实例，并使用根据PaLM-540B设置的最佳提示”，这可视为评测设置的一部分，但没有说明仅行动基线是否使用相同任务实例、相同提示选择或相同模型设置。
4. 资料提到 ReAct 与 CoT 比较、并与模仿或强化学习方法比较成功率提升，但没有给出为公平受控比较而做的具体安排。

缺少的具体信息包括：是否使用相同语言模型、相同提示/示例数量、相同检索或环境访问权限、相同动作空间、相同评测任务与指标、如何选择基线提示、如何控制训练数据与微调差异等。资料没有支持这些细节，因此不能据资料列出完整的公平受控实验安排。

参考答案要求说明三项具体安排：Act 使用相同轨迹但移除思想、任务实例从训练集随机选择、比较不偏向任一方法。回答明确表示资料不足，未给出这些事实，因此相对原始参考的正确性为 0。不过，回答对上下文的判断是准确的：上下文只提到“孤立地执行推理或动作生成的现有方法”“系统的消融和分析”以及 ALFWorld 使用“所有134个不可见的验证任务实例”，并未说明相同轨迹、随机选择训练实例或控制变量等安排；回答也正确指出缺少相同模型、提示、动作空间等细节。行为上，回答在资料不足时明确说明缺失信息，没有编造答案，符合 expected_behavior=abstain。语言为中文。

**grounded-v3**

资料不足以说明作者做了哪些具体安排来保证 ReAct 与仅行动版本对比的公平性。资料只提到“相对于只有行动的受控基线的持续优势”、在不同基准上“展示 ReAct 在少量学习设置中相对于孤立地执行推理或动作生成的现有方法的优势”，以及“系统的消融和分析”，但没有给出控制条件、提示设置、样本选择或基线配置等公平性安排的具体信息。

参考答案要求说明三项公平性安排：Act 使用相同轨迹但移除思想、任务实例从训练集随机选择、比较不偏向任一方法。回答明确表示资料不足，未给出这些事实，因此未满足事实性参考答案（correctness=0）。不过其判断与所给上下文一致：上下文仅有“相对于只有行动的受控基线的持续优势”“系统的消融和分析”等笼统表述，未出现控制条件、样本选择或基线配置细节，故其“资料不足”的结论有据（grounding=2）。在 expected_behavior=abstain 下，回答没有编造安排，并明确说明缺失信息，行为恰当（behavior=2）。主文为中文（language=2）。

**grounded-v4**

资料没有说明作者为公平对比做了哪些具体安排。资料只提到 ReAct 在少量学习设置中“相对于孤立地执行推理或动作生成的现有方法”展示优势，并称其为“受控基线”，但没有给出控制条件、基线配置、提示或样本对齐等安排细节。

因此，依据不足，无法回答该问题。

参考要求回答三项安排：Act 使用相同轨迹但移除思想、任务实例从训练集随机选择、比较不偏向任一方法。回答未给出任何这些事实，仅说明资料不足，因此未满足参考事实（correctness=0）。其“资料没有说明具体安排”的判断与所给上下文一致：上下文只出现“受控基线”和“相对于孤立地执行推理或动作生成的现有方法”等表述，未提供控制条件细节，故 grounding=2。问题在原始文档中可答但检索上下文不足，回答明确承认缺失并拒绝臆测，符合 expected_behavior=abstain，behavior=2。主文为中文，language=2。

**grounded-v5**

资料不足以回答“作者做了哪些安排，才让 ReAct 与仅行动版本的对比算得上是公平的受控实验”。

资料中能支持的相关信息只有：作者称进行了“系统的消融和分析”，并展示了 ReAct 相对于“只有行动的受控基线”的持续优势；在 HotpotQA 和 FEVER 上，因可访问维基百科 API，ReAct 优于普通动作生成模型。但资料没有具体说明为公平对比所做的控制安排，例如是否使用相同提示示例数量、相同模型、相同动作空间、相同检索接口、相同训练数据或相同评测设置等。

参考答案要求说明公平受控对比的具体安排：Act 使用相同轨迹但移除思想，任务实例从训练集随机选择。回答明确表示资料不足，未给出这些事实，因此相对原始参考事实正确性为 0。其陈述的“资料只提到系统的消融和分析”“只有行动的受控基线”“HotpotQA 和 FEVER 上可访问维基百科 API 使 ReAct 优于普通动作生成模型”均可在上下文中找到对应表述，且对缺失信息的说明有据，故 grounding=2。期望行为为 abstain，回答没有臆造控制安排，并明确列出缺失的具体控制信息，行为恰当，behavior=2。主文为中文，language=2。

### acceptance-zh-gain

预期行为为 answer。参考答案为 分别提高 34 和 10 个百分点。

**legacy**

根据相关片段，ReAct 在 ALFWorld 和 WebShop 上的成功率分别绝对提高了 **34%** 和 **10%** 个百分点。

答案准确给出 ALFWorld 34 个百分点、WebShop 10 个百分点，与参考一致；上下文明确支持：“成功率分别有34%和10%的绝对提高”以及“ReAct 分别以34%和10%的绝对成功率优于模仿和强化学习方法”。回答直接、无多余推测，主语言为中文。

**grounded-v1**

根据资料，ReAct 在 ALFWorld 和 WebShop 上的成功率分别绝对提高了 **34%** 和 **10%**（即 34 个百分点和 10 个百分点）。

资料原文两处均表述为：“在 ALFWorld 和 WebShop 上……成功率分别有 34% 和 10% 的绝对提高”；另一处为“ReAct 分别以 34% 和 10% 的绝对成功率优于模仿和强化学习方法”。

回答准确给出 ALFWorld 34 个百分点、WebShop 10 个百分点，与参考一致；上下文两处明确支持：“成功率分别有34%和10%的绝对提高”及“ReAct 分别以34%和10%的绝对成功率优于模仿和强化学习方法”。回答直接、无多余推测，主语言为中文。

**grounded-v2**

资料明确给出：在 ALFWorld 和 WebShop 上，ReAct 的成功率分别有 **34%** 和 **10%** 的绝对提高。

回答准确给出 ALFWorld 34 个百分点、WebShop 10 个百分点，与参考一致；上下文两处明确支持：“成功率分别有34%和10%的绝对提高”及“分别以34%和10%的绝对成功率优于模仿和强化学习方法”。回答直接、无多余推测，主语言为中文。

**grounded-v3**

ReAct 在 ALFWorld 和 WebShop 上的成功率分别绝对提高了 **34 个百分点**和 **10 个百分点**。

依据：资料中两处均写明“成功率分别有34%和10%的绝对提高”，另处也写明“ReAct 分别以34%和10%的绝对成功率优于模仿和强化学习方法”。

答案准确给出 ALFWorld 提高 34 个百分点、WebShop 提高 10 个百分点，与参考一致；上下文两处明确支持：“成功率分别有34%和10%的绝对提高”及“ReAct 分别以34%和10%的绝对成功率优于模仿和强化学习方法”。回答直接、无多余推测，主要说明文字为中文。

**grounded-v4**

资料显示，ReAct 在 ALFWorld 和 WebShop 上的成功率分别有 **34%** 和 **10%** 的绝对提高。

回答准确给出 ALFWorld 34 个百分点、WebShop 10 个百分点，与参考一致；上下文明确支持：“成功率分别有34%和10%的绝对提高”及“分别以34%和10%的绝对成功率优于模仿和强化学习方法”。回答直接、无多余推测，主语言为中文。

**grounded-v5**

ReAct 在 ALFWorld 和 WebShop 上的成功率分别绝对提高了 **34 个百分点**和 **10 个百分点**。

回答准确给出 ALFWorld 提高 34 个百分点、WebShop 提高 10 个百分点，与参考一致；上下文明确支持：“成功率分别有34%和10%的绝对提高”以及“ReAct 分别以34%和10%的绝对成功率优于模仿和强化学习方法”。回答直接、无多余推测，主语言为中文。

### acceptance-zh-prompts

预期行为为 answer。参考答案为 每种任务类型构造 6 个提示。

**legacy**

根据相关片段，ALFWorld 实验为每一种任务类型构造了 **6 个提示**。具体来说，是从注释的 3 条轨迹中，通过 2 条注释轨迹的每个排列来为每个任务类型构建 6 个提示。

回答准确给出每种任务类型构造6个提示，与参考一致；上下文明确支持：“从我们注释的3 个轨迹中，通过2 个注释轨迹的每个排列，为每个任务类型构建6 个提示”。回答直接、无多余推测，中文表述。

**grounded-v1**

资料显示：ALFWorld 实验“从我们注释的3个轨迹中，通过2个注释轨迹的每个排列，为每个任务类型构建6个提示”。因此，每一种任务类型构造了 **6 个提示**。

回答准确给出每种任务类型构造 6 个提示，与参考一致；上下文明确支持：“从我们注释的3 个轨迹中，通过2 个注释轨迹的每个排列，为每个任务类型构建6 个提示”。回答直接、无多余推测，主语言为中文。

**grounded-v2**

资料明确支持：ALFWorld 实验中，为每一种任务类型构造了 **6 个提示**。原文为：“我们从我们注释的3 个轨迹中，通过2 个注释轨迹的每个排列，为每个任务类型构建6 个提示。”

回答准确给出参考事实“每种任务类型构造 6 个提示”，并引用上下文原句“为每个任务类型构建6 个提示”作为支持，无额外无依据内容。

**grounded-v3**

资料显示：为每种任务类型构建了 **6 个提示**。依据是“通过 2 个注释轨迹的每个排列，为每个任务类型构建 6 个提示”。

回答准确给出参考事实“每种任务类型构造 6 个提示”，并引用上下文“通过 2 个注释轨迹的每个排列，为每个任务类型构建 6 个提示”作为依据，完全支持该结论。

**grounded-v4**

资料显示：从注释的3个轨迹中，通过2个注释轨迹的每个排列，为每种任务类型构建6个提示。因此，ALFWorld 实验为每一种任务类型构造了 **6 个提示**。

回答准确给出参考事实“每种任务类型构造6个提示”，并引用上下文原句“从我们注释的3个轨迹中，通过2个注释轨迹的每个排列，为每个任务类型构建6个提示”作为依据，无额外无支撑断言。

**grounded-v5**

资料显示：从注释的 3 条轨迹中，通过 2 条注释轨迹的每个排列，为每种任务类型构建 6 个提示。

回答准确给出每种任务类型 6 个提示，与参考一致；上下文明确支持：“从我们注释的3 个轨迹中，通过2 个注释轨迹的每个排列，为每个任务类型构建6 个提示”。回答直接、无多余推测，中文表述。

### acceptance-zh-products

预期行为为 answer。参考答案为 118 万件商品和 12k（12000）条人工指令。

**legacy**

根据相关片段，WebShop 环境拥有 **118 万件真实世界的产品**和 **12k 人工说明（人工指令）**。

答案准确给出参考中的两个数量：118 万件商品和 12k 人工指令。上下文明确支持：“拥有118 万件真实世界的产品和12k 人工说明”。回答直接、无多余推测，主语言为中文。

**grounded-v1**

资料显示：WebShop 环境拥有 **118 万件真实世界的产品** 和 **12k 人工说明（人工指令）**。

回答准确给出参考中的两个事实：118 万件商品和 12k 人工指令，与上下文“拥有118 万件真实世界的产品和12k 人工说明”一致。回答直接、无多余推测，主语言为中文。

**grounded-v2**

资料显示：WebShop 拥有 **118 万件真实世界的产品**和 **12k 人工说明（人工指令）**。

回答准确给出参考中的两个数量：118 万件商品和 12k 人工指令。上下文明确支持：“拥有118 万件真实世界的产品和12k 人工说明”。语言为中文，直接作答，无多余推测。

**grounded-v3**

资料显示：WebShop 拥有 **118 万件真实世界的产品**和 **12k 人工说明**（即约 1.2 万条人工指令）。

依据原文：“拥有118 万件真实世界的产品和12k 人工说明。”

答案准确给出参考中的两个事实：118 万件商品和 12k（约 1.2 万）条人工指令，并直接引用上下文“拥有118 万件真实世界的产品和12k 人工说明。”，与参考完全一致，无多余或错误事实。

**grounded-v4**

资料显示 WebShop 拥有 **118 万件真实世界产品**和 **12k 人工说明（指令）**。

答案准确给出参考中的两个数量：118 万件商品和 12k 人工指令。上下文明确支持：“拥有118 万件真实世界的产品和12k 人工说明”。回答直接、无多余推测，主语言为中文。

**grounded-v5**

资料显示：WebShop 环境拥有 **118 万件真实世界的产品**和 **12k 人工说明（人工指令）**。

回答准确给出参考中的两个事实：'118 万件真实世界的产品和12k 人工说明'，与上下文原文'拥有118 万件真实世界的产品和12k 人工说明'一致，无错误或多余推断。

### acceptance-zh-examples

预期行为为 answer。参考答案为 分别选取 6 和 3 个训练案例。

**legacy**

根据相关片段，对于 HotpotQA 和 Fever 的 ReAct 提示，分别随机选择了 **6 个**和 **3 个**训练案例，并手动构建 ReAct-format 轨迹以用作提示中的少数镜头样本。

回答准确给出 HotpotQA 6 个、Fever 3 个训练案例，与参考一致；上下文明确支持：“我们随机选择了6 和3 个案例2 并手动构建ReAct-format 轨迹以用作提示中的少数镜头样本”以及“对于HotpotQA 和发烧的反应提示，我们随机选择了6 和3 个案例”。回答直接、无多余推测，中文表述符合要求。

**grounded-v1**

资料明确提到：对于 HotpotQA 和 Fever 的 ReAct 提示，分别随机选择了 **6 个和 3 个案例**，并手动构建 ReAct-format 轨迹作为少数镜头样本。

回答准确给出 HotpotQA 和 Fever 分别选取 6 和 3 个案例，与参考一致；上下文明确支持：“对于HotpotQA 和发烧的反应提示，我们随机选择了6 和3 个案例2 并手动构建ReAct-format 轨迹以用作提示中的少数镜头样本。” 回答直接、无多余推测，主语言为中文。

**grounded-v2**

资料显示：用于 HotpotQA 和 Fever 的 ReAct 提示分别随机选择了 **6 个和 3 个案例**，并手动构建 ReAct-format 轨迹作为少数镜头样本。

依据原文：“对于HotpotQA 和发烧的反应提示，我们随机选择了6 和3 个案例2 并手动构建ReAct-format 轨迹以用作提示中的少数镜头样”。

答案准确给出 HotpotQA 和 Fever 分别选取 6 和 3 个案例，与参考一致；上下文明确支持：“我们随机选择了6 和3 个案例2 并手动构建ReAct-format 轨迹以用作提示中的少数镜头样本”。回答直接、无多余推测，主要使用中文。

**grounded-v3**

资料显示：用于 HotpotQA 和 Fever 的 ReAct 提示分别随机选择了 **6 个和 3 个案例**，并手动构建 ReAct-format 轨迹作为少数镜头样本。

回答准确给出 HotpotQA 和 Fever 分别选取 6 和 3 个案例，与参考一致；上下文明确支持：“我们随机选择了6 和3 个案例2 并手动构建ReAct-format 轨迹以用作提示中的少数镜头样本”。回答直接、无多余推测，主语言为中文。

**grounded-v4**

资料显示：HotpotQA 随机选择了 **6 个案例**，Fever 随机选择了 **3 个案例**，并手动构建 ReAct-format 轨迹作为提示中的少数镜头样本。

回答准确给出 HotpotQA 6 个、Fever 3 个训练案例，与参考一致；上下文明确支持：“我们随机选择了6 和3 个案例2 并手动构建ReAct-format 轨迹以用作提示中的少数镜头样本”以及“对于HotpotQA 和发烧的反应提示，我们随机选择了6 和3 个案例”。回答直接、无多余推测，中文表述符合要求。

**grounded-v5**

用于 HotpotQA 和 Fever 的 ReAct 提示分别随机选择了 **6 个**和 **3 个**训练案例（资料中称“案例”，用作提示中的少数镜头样本）。

答案准确给出 HotpotQA 6 个、Fever 3 个案例，与参考一致；上下文明确支持：“我们随机选择了6 和3 个案例2 并手动构建ReAct-format 轨迹以用作提示中的少数镜头样本”，以及“对于HotpotQA 和发烧的反应提示，我们随机选择了6 和3 个案例”。回答直接、无多余推测，中文表述符合要求。

### acceptance-en-gain

预期行为为 answer。参考答案为 34 and 10 percentage points, respectively.

**legacy**

ReAct improved success rates by **34 percentage points on ALFWorld** and **10 percentage points on WebShop**.

The answer matches the reference exactly (34 and 10 percentage points for ALFWorld and WebShop). It is directly supported by the context: 'with an absolute improvement of 34% and 10% in success rates respectively' and 'an absolute 10% improvement over the previous best success rate' on WebShop. The response is concise, in English, and directly answers the question.

**grounded-v1**

ReAct improved success rates by **34 percentage points on ALFWorld** and **10 percentage points on WebShop**, respectively. The document states this as “an absolute improvement of 34% and 10% in success rates respectively.”

The answer correctly reports 34 percentage points for ALFWorld and 10 for WebShop, matching the reference. It is directly supported by the context: 'with an absolute improvement of 34% and 10% in success rates respectively.' The response answers directly in English with no unsupported claims.

**grounded-v2**

ReAct improved success rates by **34 percentage points on ALFWorld** and **10 percentage points on WebShop**, respectively.

- ALFWorld: the document states "an absolute improvement of 34% ... in success rates" (also reflected in Table 3: best ReAct 71% vs. best Act 45%).
- WebShop: the document states "an absolute 10% improvement over the previous best success rate" (also reflected in Table 4: ReAct SR 40.0 vs. Act SR 30.1).

The answer correctly states 34 percentage points on ALFWorld and 10 on WebShop, matching the reference. It is directly supported by context: 'with an absolute improvement of 34% and 10% in success rates respectively' and 'an absolute 10% improvement over the previous best success rate.' The supporting table comparisons (71% vs 45%; 40.0 vs 30.1) are also present in the context.

**grounded-v3**

ReAct improved success rates by **34 percentage points on ALFWorld** and **10 percentage points on WebShop**. The source states "an absolute improvement of 34% and 10% in success rates respectively" for ALFWorld and WebShop.

The answer correctly assigns 34 percentage points to ALFWorld and 10 to WebShop, matching the reference. It is directly supported by the context: "an absolute improvement of 34% and 10% in success rates respectively" for ALFWorld and WebShop. The response answers directly in English with no unsupported claims.

**grounded-v4**

ReAct improved success rates by **34 percentage points on ALFWorld** and **10 percentage points on WebShop**, respectively. The document states this as "an absolute improvement of 34% and 10% in success rates respectively."

The answer correctly reports 34 percentage points for ALFWorld and 10 for WebShop, matching the reference. It is directly supported by the context: "with an absolute improvement of 34% and 10% in success rates respectively" and "an absolute 10% improvement over the previous best success rate" for WebShop. The response answers directly in English with no unsupported claims.

**grounded-v5**

ReAct improved success rates by **34 percentage points on ALFWorld** and **10 percentage points on WebShop**, respectively.

The answer exactly matches the reference (34 and 10 percentage points) and is directly supported by the context: 'with an absolute improvement of 34% and 10% in success rates respectively' for ALFWorld and WebShop. The response is concise, in English, and directly answers the question.

### acceptance-en-prompts

预期行为为 answer。参考答案为 6 prompts per task type.

**legacy**

根据相关片段，在 ALFWorld 实验中，针对每种任务类型构造了 **6 个 prompts**。片段中明确提到：“For robustness, we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.”

The answer correctly states 6 prompts per task type, directly supported by the context: 'we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.' It answers the question directly with no unsupported claims. However, the explanatory prose is in Chinese while the expected language is English, so language is 1 (mixed/other language dominant in prose, though the key fact and quote are in English).

**grounded-v1**

6 prompts were constructed for each task type.

The answer directly states '6 prompts were constructed for each task type,' matching the reference and supported by the context: 'we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.' No unsupported claims.

**grounded-v2**

The provided documents state: "we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate." Therefore, **6 prompts were constructed per task type** for the ALFWorld experiments.

The answer directly states 6 prompts per task type, matching the reference. It is supported by the context quote: "we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate." The response is in English and answers directly without speculation.

**grounded-v3**

6 prompts were constructed for each task type. The document states: "we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate."

The answer directly states '6 prompts were constructed for each task type,' matching the reference and quoting the supporting context: 'we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.' No unsupported claims are present.

**grounded-v4**

6 prompts were constructed for each task type.

The answer directly states '6 prompts were constructed for each task type,' matching the reference and supported by the context: 'we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.' No unsupported claims.

**grounded-v5**

6 prompts were constructed for each task type.

The answer directly states '6 prompts were constructed for each task type,' matching the reference and supported by the context: 'we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.'

### acceptance-en-products

预期行为为 answer。参考答案为 1.18 million products and 12 thousand human instructions.

**legacy**

根据相关片段，WebShop 环境包含 **1.18M（118万）个真实世界产品和 12k（1.2万）条人类指令**。

The answer correctly states 1.18M products and 12k human instructions, matching the reference and directly supported by context: 'WebShop ... with 1.18M real-world products and 12k human instructions.' Behavior is appropriate and direct. However, the main prose is in Chinese rather than the expected English, so language=1.

**grounded-v1**

The WebShop environment contains **1.18M real-world products** and **12k human instructions**.

The answer exactly matches the reference (1.18 million products, 12 thousand human instructions) and is directly supported by the context: 'WebShop (Yao et al., 2022), a recently proposed online shopping website environment with 1.18M real-world products and 12k human instructions.' The response answers directly in English with no unsupported extras.

**grounded-v2**

The WebShop environment contains **1.18M real-world products** and **12k human instructions**.

The answer accurately states the reference facts: '1.18M real-world products and 12k human instructions.' This is directly supported by the context: 'WebShop (Yao et al., 2022), a recently proposed online shopping website environment with 1.18M real-world products and 12k human instructions.' The response is direct, in English, and contains no unsupported claims.

**grounded-v3**

The WebShop environment contains **1.18M real-world products** and **12k human instructions**, according to the document.

The answer accurately states the reference facts: '1.18M real-world products and 12k human instructions.' This is directly supported by the context: 'WebShop ... with 1.18M real-world products and 12k human instructions.' The response answers directly in English.

**grounded-v4**

WebShop contains **1.18M real-world products** and **12k human instructions**.

The answer exactly matches the reference (1.18 million products, 12 thousand human instructions) and is directly supported by the context: 'WebShop (Yao et al., 2022), a recently proposed online shopping website environment with 1.18M real-world products and 12k human instructions.' The response is concise, in English, and directly answers the question.

**grounded-v5**

WebShop contains **1.18M real-world products** and **12k human instructions**.

The answer accurately states the reference facts: '1.18M real-world products and 12k human instructions.' This is directly supported by the context: 'WebShop (Yao et al., 2022), a recently proposed online shopping website environment with 1.18M real-world products and 12k human instructions.' The response is direct, in English, and contains no unsupported claims.

### acceptance-en-examples

预期行为为 answer。参考答案为 6 and 3 examples, respectively.

**legacy**

For HotpotQA and Fever, **6** and **3** training examples were randomly selected, respectively, and manually composed into ReAct-format trajectories as few-shot exemplars in the prompts.

The answer directly states 6 and 3 examples for HotpotQA and Fever, matching the reference. It is fully supported by the context: 'For HotpotQA and Fever, we randomly select 6 and 3 cases2 from the training set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts.' The response is in English and directly answers the question.

**grounded-v1**

根据资料，HotpotQA 的 ReAct prompt 随机选取了 **6** 个训练案例，Fever 选取了 **3** 个训练案例（“For HotpotQA and Fever, we randomly select 6 and 3 cases from the training set…”）。

The answer correctly states 6 HotpotQA and 3 Fever training examples, directly supported by the context: 'For HotpotQA and Fever, we randomly select 6 and 3 cases from the training set and manually compose ReAct-format trajectories'. No unsupported claims. However, the explanatory prose is in Chinese rather than the expected English, though the quoted source text remains English.

**grounded-v2**

For HotpotQA, **6** training cases were randomly selected. For Fever, **3** training cases were randomly selected. These were manually composed into ReAct-format trajectories as few-shot exemplars in the prompts.

The answer states 6 HotpotQA and 3 Fever training cases, matching the reference and directly supported by the context: 'For HotpotQA and Fever, we randomly select 6 and 3 cases2 from the training set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts.' No unsupported claims are present.

**grounded-v3**

For HotpotQA, 6 training examples were selected; for Fever, 3 training examples were selected. The document states: "For HotpotQA and Fever, we randomly select 6 and 3 cases from the training set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts."

The answer correctly states 6 examples for HotpotQA and 3 for Fever, matching the reference. It is directly supported by the context: "For HotpotQA and Fever, we randomly select 6 and 3 cases2 from the training set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts." The response answers directly in English with no unsupported claims.

**grounded-v4**

For HotpotQA, 6 training examples were selected; for Fever, 3 training examples were selected. The paper states: "For HotpotQA and Fever, we randomly select 6 and 3 cases from the training set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts."

The answer correctly states 6 examples for HotpotQA and 3 for Fever, matching the reference. It is directly supported by the context: "For HotpotQA and Fever, we randomly select 6 and 3 cases2 from the training set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts." The response answers directly in English with no unsupported claims.

**grounded-v5**

6 cases were selected for HotpotQA and 3 cases for Fever.

The answer matches the reference exactly: context states 'For HotpotQA and Fever, we randomly select 6 and 3 cases2 from the training set', supporting 6 for HotpotQA and 3 for Fever. Direct, supported answer in English.

### boundary-zh-gpu

预期行为为 abstain。参考答案为 资料未给出 GPU 小时数，应明确说明无法据此确定。

**legacy**

根据提供的片段，文中没有提到训练模型总共消耗了多少 GPU 小时的具体数字。片段中只提到进行了“初步的微调实验”以及讨论了模型规模（8b、62b、540b）的缩放结果，但未给出 GPU 小时消耗量。因此，无法从这些内容中得出该论文训练模型的总 GPU 小时数。

参考要求明确说明资料未给出 GPU 小时数、无法确定。回答准确指出片段未提及 GPU 小时消耗，仅提到“初步的微调实验”和“8b、62b、540b”规模缩放，未编造数字，符合 abstention 要求。

**grounded-v1**

资料中没有提供训练模型所消耗的 GPU 小时数，因此依据不足，无法回答该问题。资料仅提到进行了初步的微调实验，但未给出任何 GPU 小时或计算资源消耗数据。

参考要求明确说明资料未给出 GPU 小时数、无法确定。回答准确指出资料未提供 GPU 小时数，并说明仅有初步微调实验但无计算资源消耗数据，与上下文一致（如“进行了初步的微调实验”），未编造数字。

**grounded-v2**

资料中没有提供训练模型所消耗的 GPU 小时数，因此无法据此回答该问题。资料仅提到进行了“初步的微调实验”，并讨论了提示与微调的缩放结果，但未给出任何 GPU 小时或类似计算成本数据。

参考要求明确说明资料未给出 GPU 小时数、无法确定。回答准确指出资料未提供 GPU 小时数，并引用文中仅有的“初步的微调实验”和“提示与微调的缩放结果”作为相关但不足以回答的证据，未编造数值，符合 abstention 要求。

**grounded-v3**

资料中没有提到训练模型总共消耗了多少 GPU 小时，依据不足。文末“资料结束”前未出现任何 GPU 小时数或相关训练成本数据。

参考要求明确说明资料未给出 GPU 小时数、无法确定。回答正确指出资料中没有 GPU 小时数或训练成本数据，与上下文一致（上下文仅讨论 ReAct 方法、基准与成功率，未提及 GPU 小时）。回答直接且恰当地进行了弃答，未编造数字。

**grounded-v4**

资料中没有提供训练模型所消耗的 GPU 小时数，依据不足，无法回答该问题。

参考要求明确说明资料未给出 GPU 小时数、无法确定。回答正是如此，未编造数字。上下文中仅提及模型规模（8b/62b/540b）和微调实验，但未出现任何 GPU 小时数，因此该 abstention 有据可依。

**grounded-v5**

资料中没有提到训练模型总共消耗了多少 GPU 小时，依据不足，无法回答该问题。

参考要求明确说明资料未给出 GPU 小时数、无法确定。回答准确指出资料未提及 GPU 小时消耗并拒绝给出数字，与参考一致；上下文确实只涉及 ReAct 的基准、提示/微调与成功率，未出现任何 GPU 小时数据，因此该缺失声明有据可依。行为上直接、明确地承认信息缺失，未编造数字。语言为中文。

### boundary-en-funding

预期行为为 abstain。参考答案为 The acknowledgement lists a grant identifier but no dollar amount. State that the amount is unavailable.

**legacy**

根据提供的片段，美国国家科学基金会（NSF）的资助编号为2107048，但片段中并未给出具体的资助金额（美元数额）。因此，无法从上述内容中确定NSF资助的美元金额。

The reference is an abstention: the acknowledgement lists a grant identifier but no dollar amount. The answer correctly states that NSF grant 2107048 is mentioned but no dollar amount is given, matching the context ('这项工作得到了美国国家科学基金会2107048 的资助') and explicitly identifying the missing amount. However, the main explanatory prose is in Chinese, not the expected language English, so language=0.

**grounded-v1**

The provided material does not state an NSF funding amount in US dollars. It only says the work was supported by NSF award 2107048.

The reference defines the answer as an abstention: the acknowledgement lists a grant identifier but no dollar amount. The answer correctly states that no dollar amount is provided and cites the only funding detail present, '国家科学基金会2107048 的资助' (NSF award 2107048). It does not invent an amount, directly addresses the question, and is written in English.

**grounded-v2**

The document states that the work was supported by the U.S. National Science Foundation under grant **2107048**. It does not provide a funding amount in US dollars, so the dollar amount is not available in the provided material.

The answer correctly identifies the grant identifier (2107048) and explicitly states that no dollar amount is provided, matching the reference's abstention requirement. The context confirms '这项工作得到了美国国家科学基金会2107048 的资助' with no monetary figure, supporting the claim that the amount is unavailable.

**grounded-v3**

The provided material states that this work was supported by the U.S. National Science Foundation under award 2107048. However, it does not specify a funding amount in US dollars, so the monetary amount cannot be determined from the available evidence.

Directly relevant excerpt: “这项工作得到了美国国家科学基金会2107048 的资助。”

The reference is an abstention: the acknowledgement lists a grant identifier but no dollar amount. The answer correctly states the grant identifier (2107048) and explicitly says the dollar amount is unavailable, matching the reference. The context quote '这项工作得到了美国国家科学基金会2107048 的资助' supports the grant identifier and the absence of a dollar amount. The answer directly abstains from inventing an amount, satisfying expected_behavior=abstain. Main prose is in English.

**grounded-v4**

The NSF funding amount is not stated in US dollars. The document only says the work was supported by the U.S. National Science Foundation under award 2107048. The specific dollar amount is not provided.

The reference defines the answer as an abstention: the acknowledgement lists a grant identifier but no dollar amount. The answer correctly states that the dollar amount is not provided and cites the only funding detail present in the context: '这项工作得到了美国国家科学基金会2107048 的资助' (supported by NSF award 2107048). It does not invent an amount and explicitly acknowledges the missing information, matching expected_behavior=abstain.

**grounded-v5**

The NSF funding amount was **$2,107,048** (NSF award 2107048).

The context states only '这项工作得到了美国国家科学基金会2107048 的资助' — a grant identifier, not a dollar amount. The answer invents '$2,107,048' by treating the grant number as a monetary figure, which is unsupported and contradicts the reference requirement to state the amount is unavailable. No dollar amount appears in the context.

### boundary-zh-premise

预期行为为 correct_premise。参考答案为 纠正前提：思想不影响外部环境，也不产生观察反馈；其作用是更新上下文。

**legacy**

根据提供的片段，思想（即语言空间中的动作）**不影响外部环境，因此不会直接产生观察反馈**。片段中明确说明：“语言空间中的动作â_t∈L，我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈。”

思想的作用机制是：通过对当前上下文c_t进行推理来组成有用信息，并**更新上下文**c_{t+1}=(c_t, a_t)，以支持未来的推理或行动。也就是说，思想改变的是代理内部的上下文（推理轨迹），而非外部环境；观察反馈来自外部环境中的行动（action），而非思想本身。片段还指出，ReAct将思想与行动交替产生，解决任务的轨迹由多个“思想-行动-观察”步骤组成——观察对应的是行动作用于环境后的反馈，思想则为后续行动提供推理支持。

回答明确纠正了问题中的错误前提，指出思想不影响外部环境、不产生观察反馈，并说明思想的作用是更新上下文，与参考事实一致。引用片段“语言空间中的动作â_t∈L，我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈”和“更新上下文c_{t+1}=(c_t, a_t)”直接支持该结论。回答还正确区分了观察来自行动而非思想，未引入无依据的额外主张。

**grounded-v1**

资料明确指出：语言空间中的动作（即“思想”或“推理轨迹”）**不影响外部环境，从而导致没有观察反馈**。也就是说，思想本身不产生观察反馈；它通过更新上下文（ct+1 = (ct, at)）来支持未来的推理或行动。观察反馈来自环境中的行动，而非思想。

因此，问题前提“思想会改变外部环境”与资料矛盾：资料说思想不影响外部环境。资料能够支持的部分是：思想不产生观察反馈，只更新上下文以支持后续推理或行动。

回答明确纠正了错误前提，并准确复述了资料中的核心事实：'语言空间中的动作aˇt∈L，我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈'，以及'思想at 旨在通过对当前上下文ct 进行推理来组成有用的信息，并更新上下文ct+1 = (ct，at)以支持未来的推理或行动'。回答没有引入资料之外的额外事实，直接回应了问题并纠正了前提。

**grounded-v2**

资料先纠正了问题前提：思想（语言空间中的动作）**不影响外部环境，也不会产生观察反馈**。资料原文说：“语言空间中的动作aˇt∈L，我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈。”

资料能够支持的是：思想通过对当前上下文进行推理来组成有用信息，并更新上下文，以支持未来的推理或行动；而观察反馈来自与外部环境交互的行动，不是来自思想本身。资料还说明，在需要推理的任务中会交替产生思想、行动和观察，因此轨迹由多个“思想—行动—观察”步骤组成。

至于“思想如何产生观察反馈”这一机制，资料明确否定思想会产生观察反馈，未提供其他机制说明。

回答明确纠正了问题前提，准确引用原文“语言空间中的动作aˇt∈L，我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈”，并说明思想的作用是更新上下文（“更新上下文ct+1 = (ct，at)以支持未来的推理或行动”），观察反馈来自与外部环境交互的行动而非思想本身，与参考事实一致。回答还指出资料未提供其他机制，边界清晰，无编造内容。

**grounded-v3**

资料中的前提需要纠正：思想（语言空间中的动作）**不改变外部环境，因此不会产生观察反馈**。资料明确说：“语言空间中的动作……我们将称之为思想或推理轨迹，不影响外部环境，从而导致没有观察反馈。”

资料能够支持的部分是：思想作用于上下文，而不是环境——它“通过对当前上下文ct 进行推理来组成有用的信息，并更新上下文ct+1 = (ct，at)以支持未来的推理或行动”。也就是说，思想得到的是上下文更新，而非观察反馈；观察反馈来自会改变外部环境的行动。

资料未说明思想本身如何产生观察反馈，因为按其定义它不产生观察反馈。

回答明确纠正了错误前提，指出思想不影响外部环境、不产生观察反馈，并引用原文“不影响外部环境，从而导致没有观察反馈”支持；同时准确说明思想的作用是更新上下文（“更新上下文ct+1 = (ct，at)以支持未来的推理或行动”），与参考事实完全一致。

**grounded-v4**

资料先纠正了问题前提：语言空间中的动作（思想/推理轨迹）“不影响外部环境，从而导致没有观察反馈”；思想是通过更新上下文 \(c_{t+1}=(c_t,a_t)\) 来支持未来的推理或行动，而不是通过改变外部环境产生观察反馈。

资料能够支持的部分是：ReAct 将动作空间扩大到 \(A \cup L\)，其中语言空间 \(L\) 中的动作被称为思想或推理轨迹；这类动作不作用于外部环境，因此没有观察反馈。真正产生观察反馈的是代理在环境中采取的行动：代理在时间步骤 \(t\) 从环境接收观察 \(o_t\)，并依据上下文采取行动。资料还说明，对于推理至关重要的任务，会交替产生思想、行动和观察，轨迹由多个“思想—行动—观察”步骤组成。

至于“思想如何产生观察反馈”这一机制本身，资料依据不足：资料明确说思想不影响外部环境、没有观察反馈，未提供思想直接产生观察反馈的机制。

回答明确纠正了错误前提，并准确复述了上下文中的关键事实：语言空间中的动作（思想/推理轨迹）“不影响外部环境，从而导致没有观察反馈”，思想通过更新上下文 c_{t+1}=(c_t,a_t) 支持未来推理或行动；同时说明真正产生观察反馈的是环境中的行动（代理从环境接收观察 o_t）。回答还指出资料未提供“思想直接产生观察反馈”的机制，与上下文一致，未引入外部知识。

**grounded-v5**

资料明确区分了两类动作：语言空间中的动作（思想/推理轨迹）“不影响外部环境，从而导致没有观察反馈”；而行动作用于外部环境，代理在时间步骤t从环境接收观察 o_t。因此，思想本身不直接产生观察反馈，它通过更新上下文 c_{t+1}=(c_t,a_t) 支持未来的推理或行动，观察反馈来自随后与外部环境交互的行动。资料还说明，思想与行动是异步发生的，由语言模型自行决定。

资料未进一步说明思想影响外部环境后反馈的具体产生机制。

回答明确纠正了前提：引用“思想或推理轨迹，不影响外部环境，从而导致没有观察反馈”，并说明思想通过更新上下文 c_{t+1}=(c_t,a_t) 支持未来推理或行动，观察反馈来自与外部环境交互的行动（“代理从环境接收到观察 o_t”）。最后指出资料未说明思想影响外部环境后反馈的具体机制，与上下文一致。

### boundary-en-premise

预期行为为 correct_premise。参考答案为 Correct the premise: four benchmarks, HotPotQA, FEVER, ALFWorld and WebShop.

**legacy**

根据片段内容，ReAct 在实证评估中使用了 **四个** 基准（benchmarks），而非五个：

1. **HotPotQA**（问答，question answering）
2. **Fever**（事实核查，fact verification）
3. **ALFWorld**（文本游戏，text-based game）
4. **WebShop**（网页导航，webpage navigation）

片段中明确写道：“We conduct empirical evaluations of ReAct and state-of-the-art baselines on four diverse benchmarks: question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)。”

因此，就所提供的片段而言，无法列出“五个”基准；片段只支持上述四个基准。

The answer explicitly corrects the false premise (four, not five) and lists the four benchmarks HotPotQA, Fever, ALFWorld and WebShop, matching the reference. All facts are directly supported by the context: 'We conduct empirical evaluations of ReAct and state-of-the-art baselines on four diverse benchmarks: question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. However, the main explanatory prose is in Chinese rather than the expected English, so language is 1.

**grounded-v1**

资料不足以支持“五个基准”这一前提。资料明确说 ReAct 是在 **four diverse benchmarks** 上评估的，并列出这四个：**HotPotQA、Fever、ALFWorld、WebShop**。没有依据表明使用了五个基准。

The answer correctly rejects the false premise of five benchmarks and states the accurate fact from the context: 'four diverse benchmarks' with HotPotQA, Fever, ALFWorld, and WebShop. This matches the reference correction. Grounding is fully supported by the quoted context. Behavior is appropriate for a correct_premise task. However, the main explanatory prose is in Chinese, not the expected English, so language=1.

**grounded-v2**

The premise of the question is incorrect: the document states that ReAct was evaluated on **four** diverse benchmarks, not five. The four benchmarks named are:

1. **HotPotQA** (question answering)
2. **Fever** (fact verification)
3. **ALFWorld** (text-based game)
4. **WebShop** (webpage navigation)

The document does not name a fifth benchmark, so the requested list of five cannot be supported by the provided material.

The answer explicitly corrects the false premise ('four diverse benchmarks') and lists exactly the four benchmarks named in the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. It also correctly notes no fifth benchmark is named. All claims are supported by the context.

**grounded-v3**

The premise of five benchmarks is not supported: the document states that ReAct was evaluated on **four** diverse benchmarks — **HotPotQA, Fever, ALFWorld, and WebShop**. No fifth benchmark is identified in the provided material.

The answer explicitly corrects the false premise of five benchmarks and accurately lists the four benchmarks from the context: 'four diverse benchmarks: question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. It also correctly notes no fifth benchmark is identified in the provided material, which is supported by the context's enumeration of exactly four benchmarks.

**grounded-v4**

The premise of the question is incorrect: the document states that ReAct was evaluated on **four** diverse benchmarks, not five. Those four are:

1. **HotPotQA** (question answering)
2. **Fever** (fact verification)
3. **ALFWorld** (text-based game)
4. **WebShop** (webpage navigation)

The document does not list a fifth benchmark.

The answer explicitly corrects the false premise ('four diverse benchmarks, not five') and lists exactly the four benchmarks from the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. It also correctly notes no fifth benchmark is listed. All claims are supported by the context, the response directly addresses the question, and the prose is in English.

**grounded-v5**

The premise of the question is incorrect: the document states that ReAct was evaluated on **four** diverse benchmarks, not five. They are:

1. HotPotQA (question answering)
2. Fever (fact verification)
3. ALFWorld (text-based game)
4. WebShop (webpage navigation)

The document does not list a fifth benchmark.

The answer explicitly corrects the false premise ('four diverse benchmarks, not five') and lists all four benchmarks exactly as in the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. It also correctly notes no fifth benchmark is listed. All claims are supported by the context.

### boundary-zh-partial

预期行为为 partial。参考答案为 机构为普林斯顿大学计算机科学系、Google Research Brain team。片段未给出作者出生日期，不能推断。

**legacy**

根据提供的片段，可以确认的论文作者机构信息如下：

**论文《REACT: 协同推理和行动》**（发表于ICLR 2023）的作者机构为：
- **普林斯顿大学计算机科学系**（作者：Shunyu Yao、Karthik Narasimhan）
- **谷歌研究，大脑团队**（作者：Jeffrey Zhao、Dian Yu、Nan Du、Izhak Shafran、Yuan Cao）

**关于作者的出生日期：** 提供的片段中**没有任何关于作者出生日期的信息**。片段仅包含作者姓名、所属机构、论文标题、发表信息、致谢和参考文献等内容，未提及任何作者的出生日期。因此无法回答这一问题。

回答准确给出机构：普林斯顿大学计算机科学系与谷歌研究大脑团队，与上下文“1 普林斯顿大学计算机科学系 / 2 谷歌研究，大脑团队”一致；并明确说明片段未提供出生日期，符合参考中“片段未给出作者出生日期，不能推断”。未出现无依据的额外事实。

**grounded-v1**

资料能支持的机构信息只有：论文《REACT: 协同推理和行动》的作者署名机构为 **1 普林斯顿大学计算机科学系** 和 **2 谷歌研究，大脑团队**。资料中提到的其他作者条目未给出所属机构。

关于“这些作者的出生日期分别是什么”，资料中**没有任何作者出生日期信息**，因此依据不足，无法回答。

回答准确给出上下文支持的机构：'1 普林斯顿大学计算机科学系' 和 '2 谷歌研究，大脑团队'，并明确说明资料未提供作者出生日期，符合参考中'片段未给出作者出生日期，不能推断'的要求。所有事实性陈述均有上下文依据，无额外推断。

**grounded-v2**

资料中能确认的机构信息仅限论文《REACT:协同推理和行动》的作者署名：作者所属机构为**普林斯顿大学计算机科学系**和**谷歌研究，大脑团队**。资料未给出这些作者（或其他被引文献作者）的出生日期。因此，作者出生日期这一部分依据不足，无法回答。

回答准确给出机构为普林斯顿大学计算机科学系和谷歌研究大脑团队，与上下文署名一致（“1 普林斯顿大学计算机科学系”“2 谷歌研究，大脑团队”），并明确说明资料未给出出生日期、无法回答，符合参考中“片段未给出作者出生日期，不能推断”。

**grounded-v3**

资料能确认的机构信息仅有：论文《REACT:协同推理和行动》标注作者隶属“1 普林斯顿大学计算机科学系”和“2 谷歌研究，大脑团队”。资料未提供这些作者或其他列名作者的出生日期，因此无法回答出生日期部分。

回答准确给出参考中的两个机构（“1 普林斯顿大学计算机科学系”“2 谷歌研究，大脑团队”），并明确说明资料未提供出生日期、无法回答，符合参考的“片段未给出作者出生日期，不能推断”。所有事实均可在上下文中找到对应文字，无额外推断。

**grounded-v4**

根据资料，可确认的机构信息如下：

- 论文《REACT:协同推理和行动》的作者标注机构为：普林斯顿大学计算机科学系（作者1）和谷歌研究大脑团队（作者2）。

资料中未提供任何作者的出生日期，因此无法回答“这些作者的出生日期分别是什么”，该部分依据不足。

回答正确指出机构为普林斯顿大学计算机科学系和谷歌研究大脑团队，与参考一致（上下文：'1 普林斯顿大学计算机科学系'、'2 谷歌研究，大脑团队'），并明确说明资料未提供出生日期、无法推断，符合部分回答要求。

**grounded-v5**

资料中可确认的机构信息仅有：普林斯顿大学计算机科学系、谷歌研究大脑团队（该论文署名机构）。

资料未提供任何作者的出生日期，因此无法回答出生日期部分。

回答准确给出上下文中的机构“普林斯顿大学计算机科学系”和“谷歌研究，大脑团队”，并明确说明资料未提供作者出生日期，符合参考中“片段未给出作者出生日期，不能推断”的要求。

### boundary-en-partial

预期行为为 partial。参考答案为 List HotPotQA, FEVER, ALFWorld and WebShop, and explicitly state that GPU training time is not given.

**legacy**

根据提供的片段，ReAct 的评估基准包括四个：

1. **HotPotQA**（问答，Yang et al., 2018）
2. **Fever**（事实核查，Thorne et al., 2018）
3. **ALFWorld**（文本游戏，Shridhar et al., 2020b）
4. **WebShop**（网页导航，Yao et al., 2022）

关于 GPU 训练时间，片段中**没有提及**任何具体的 GPU 训练时长信息，因此无法提供该数据。

The answer correctly lists all four benchmarks (HotPotQA, Fever, ALFWorld, WebShop) matching the reference, and explicitly states that GPU training time is not mentioned in the context, which is accurate since the context contains no such information. However, the main explanatory prose is in Chinese, not the expected English, so language=0.

**grounded-v1**

**Evaluation benchmarks:** The four benchmarks are HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

**GPU training time:** The provided material does not state any GPU training time. Therefore, there is insufficient evidence to answer this part of the question.

The answer lists all four benchmarks exactly as in the context ('HotPotQA', 'Fever', 'ALFWorld', 'WebShop') and explicitly states that GPU training time is not given, matching the reference. The absence claim is supported by the context, which contains no GPU training time. No unsupported claims.

**grounded-v2**

The benchmarks listed are: HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

The provided material does not state any GPU training time. It mentions fine-tuning experiments on PaLM-8B/62B and scaling results (Figure 3), but gives no GPU training time figures, so that part of the question cannot be answered from the document.

The answer correctly lists all four benchmarks with their task types, matching the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. It also explicitly states that GPU training time is not given, which matches the reference requirement and is supported by the absence of any GPU training time in the context. The mention of fine-tuning on PaLM-8B/62B and Figure 3 scaling results is supported by the context ('Scaling results for prompting and finetuning on HotPotQA', 'PaLM-8/62B'). No unsupported claims.

**grounded-v3**

**Evaluation benchmarks:** The four benchmarks listed are HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

**GPU training time:** The provided material does not state any GPU training time. No figure for training duration or GPU hours appears in the document; it only mentions experiments done on PaLM and fine-tuning results, without timing details.

So the benchmarks can be answered, but the GPU training time is not supported by the material.

The answer lists all four benchmarks exactly as in the context ('HotPotQA, Yang et al., 2018', 'Fever, Thorne et al., 2018', 'ALFWorld, Shridhar et al., 2020b', 'WebShop, Yao et al., 2022') and explicitly states that GPU training time is not given, matching the reference. The absence claim is supported by the context, which contains no timing/GPU-hour figures. Behavior is appropriate for a partial reference: it answers the supported part and clearly identifies the missing part.

**grounded-v4**

The evaluation benchmarks are: HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

The document does not state the GPU training time; that information is not provided in the supplied material.

The answer lists all four benchmarks with correct task mappings, supported by the context: 'question answering (HotPotQA...), fact verification (Fever...), text-based game (ALFWorld...), and webpage navigation (WebShop...)'. It also explicitly states that GPU training time is not given, matching the reference's requirement to note the missing information. No unsupported claims are made.

**grounded-v5**

The evaluation benchmarks listed are: HotPotQA (question answering), Fever (fact verification), ALFWorld (text-based game), and WebShop (webpage navigation).

The provided material does not state a GPU training time, so there is insufficient evidence to answer that part of the question.

The answer lists all four benchmarks exactly as in the context ('HotPotQA', 'Fever', 'ALFWorld', 'WebShop') with correct task mappings ('question answering', 'fact verification', 'text-based game', 'webpage navigation'), matching the reference. It also explicitly states that GPU training time is not given ('The provided material does not state a GPU training time'), satisfying the partial-answer requirement. All claims are supported by the context, and the prose is in English.

### boundary-zh-date

预期行为为 abstain。参考答案为 片段仅有 ICLR 2023 等年份信息，不能确定首次公开的年月日。

**legacy**

根据提供的片段，无法确定这篇论文首次公开的具体日期。片段中只提到“Published as a conference paper at ICLR 2023”，没有给出具体的年、月、日。

The answer correctly abstains, matching the reference that the snippet only contains 'Published as a conference paper at ICLR 2023' and cannot determine a first-publication date. It explicitly identifies the missing information without inventing details, and the prose is in Chinese.

**grounded-v1**

依据不足。资料只显示该论文“Published as a conference paper at ICLR 2023”，没有给出首次公开的具体年月日。

回答正确指出资料仅有“Published as a conference paper at ICLR 2023”，无法确定首次公开的具体年月日，与参考的弃权结论一致；未编造日期，明确说明缺失信息，符合 abstain 行为；主要说明文字为中文。

**grounded-v2**

依据不足。资料仅显示该论文“Published as a conference paper at ICLR 2023”，未给出首次公开的具体年月日。

The reference defines the missing information as the exact first-publication date, and the answer appropriately abstains, noting that the context only shows 'Published as a conference paper at ICLR 2023' without a specific date. This matches the reference and is fully supported by the quoted context.

**grounded-v3**

资料不足以回答“首次公开的具体日期”。资料只显示“Published as a conference paper at ICLR 2023”，未给出具体的年、月、日。

回答正确指出资料仅有“Published as a conference paper at ICLR 2023”，无法确定首次公开的具体年月日，符合参考的弃答要求；未编造日期，直接说明缺失信息；主要表述为中文。

**grounded-v4**

资料没有给出这篇论文首次公开的具体日期。资料仅显示“Published as a conference paper at ICLR 2023”，不足以确定具体到哪年哪月哪日。

回答正确指出资料仅有“Published as a conference paper at ICLR 2023”，无法确定首次公开的具体年月日，与参考的弃权结论一致，且未编造日期。

**grounded-v5**

资料未提供该论文首次公开的具体年月日，仅标明“Published as a conference paper at ICLR 2023”。

回答正确指出资料未提供首次公开的具体年月日，仅引用“Published as a conference paper at ICLR 2023”，与参考的弃答要求一致，且完全基于上下文。

### boundary-en-seed

预期行为为 abstain。参考答案为 The context does not specify a random seed. Do not invent one.

**legacy**

根据提供的片段，无法确定选择 ALFWorld prompt trajectories 时使用的确切随机种子。片段中只提到“we randomly annotate three trajectories from the training set for each task type”以及“we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate”，但没有给出具体的随机种子数值。

The answer appropriately abstains, stating the exact random seed is not specified, which matches the reference. It accurately quotes the context ('we randomly annotate three trajectories...' and 'we construct 6 prompts...') and correctly notes no seed value is given. However, the main explanatory prose is in Chinese, while the expected language is English, so language=0.

**grounded-v1**

资料未说明用于选择 ALFWorld prompt trajectories 的具体随机种子。资料只提到“randomly annotate three trajectories from the training set for each task type”，以及用这 3 条标注轨迹的 2 条排列组合构造 6 个 prompts，但没有给出随机种子的数值。

The answer correctly abstains and states that the context does not specify a random seed, matching the reference. It accurately cites the context: 'randomly annotate three trajectories from the training set for each task type' and the construction of 6 prompts from permutations of 2 of the 3 annotated trajectories. No invented seed is given. However, the main explanatory prose is in Chinese while the expected language is English, so language is scored 1.

**grounded-v2**

The provided material does not state any random seed used to select the ALFWorld prompt trajectories. It only says: "To prompt ReAct, we randomly annotate three trajectories from the training set for each task type" and "we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate." No seed value is given, so the exact random seed cannot be determined from the document.

The answer correctly abstains, matching the reference that no seed is specified. It is grounded in the context quotes: 'we randomly annotate three trajectories from the training set for each task type' and 'we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.' No seed value is invented, and the response is in English.

**grounded-v3**

The provided material does not specify any exact random seed used to select the ALFWorld prompt trajectories. It only states that three trajectories were "randomly" annotated from the training set for each task type, without giving a seed value.

Relevant excerpt: "we randomly annotate three trajectories from the training set for each task type."

Therefore, the exact random seed is not available in the documentation.

The reference is an abstention: the context does not specify a random seed. The answer correctly states no seed is given and quotes the only relevant context ('we randomly annotate three trajectories from the training set for each task type'), which supports the absence of a seed value. It does not invent one, matching expected_behavior=abstain. Prose is in English.

**grounded-v4**

The provided material does not specify any exact random seed used to select the ALFWorld prompt trajectories. It only states that three trajectories were randomly annotated from the training set for each task type, and that 6 prompts were constructed via permutations of 2 of those 3 trajectories. No seed value is given.

The reference defines the missing information as an abstention target. The answer correctly states no seed is specified, quoting the context's 'randomly annotate three trajectories' and '6 prompts ... through each permutation of 2 annotated trajectories' without inventing a seed. This is fully supported and appropriately abstains.

**grounded-v5**

The provided material does not specify which exact random seed was used to select the ALFWorld prompt trajectories. It only states that three trajectories were randomly annotated from the training set for each task type, and that 6 prompts were constructed via permutations of 2 annotated trajectories from the 3. No seed value is given.

The answer correctly abstains, matching the reference that no seed is specified. It accurately cites the context: 'we randomly annotate three trajectories from the training set for each task type' and 'we construct 6 prompts for each task type through each permutation of 2 annotated trajectories from the 3 we annotate.' No invented seed is provided.

## 用量与限制

有效提示词对照结果报告输入 token 为 909928，输出 token 为 30788，包含生成及评分。校准及未计入有效结果的失败、重试调用另计，实际费用以服务账单为准。

- 固定片段实验控制了检索差异。它不能直接证明修改后完整检索链的总体正确率。
- 新边界题与原有问题来自同一论文，未覆盖其他语料、领域和复杂攻击。
- 模型评分存在误判。分歧保留供复核，当前评分适合诊断，尚不足以作为独立质量保证。

## 配置决策

项目默认提示词为 legacy。候选通过 RAG_PROMPT_VERSION 切换，正常入口从同一 prompts.json 读取模板，答案缓存键包含模板内容指纹。

候选明显改善语言与证据不足处理，但多轮迭代出现作者姓名补全、机构编号误读和项目编号转金额。候选的评分满分与 AI 逐条复核存在分歧，最终版本需要新题、重复生成和独立人工复核后再选定。

grounded-v4 另通过 FastAPI TestClient 对 /ask 的四道真实问答检查，覆盖英文作者机构、中文受控比较、中文作者机构及英文训练案例数量。入口检查不能消除冻结片段实验中已经记录的错误。
