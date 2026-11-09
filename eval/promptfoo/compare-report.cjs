const fs = require('node:fs');
const path = require('node:path');
const { reportDirectory, rawDirectory, inputDirectory } = require('./report-paths.cjs');
const check = require(path.join(inputDirectory, 'response-checks.cjs'));

const study = path.join(rawDirectory, 'retrieval-study');
const retrieval = JSON.parse(fs.readFileSync(path.join(study, 'retrieval.json'), 'utf8'));
const cases = ['cases.json', 'acceptance.json'].flatMap(name =>
  JSON.parse(fs.readFileSync(path.join(inputDirectory, name), 'utf8')));
const outputs = {};
for (const variant of ['vector', 'candidate']) {
  const raw = JSON.parse(fs.readFileSync(path.join(study, variant, 'end-to-end.json'), 'utf8'));
  outputs[variant] = raw.results.results.map(result => {
    const test = cases.find(test => test.description === result.testCase.description);
    if (!test) throw new Error(`Unknown case ${result.testCase.description}`);
    const response = result.response?.output;
    if (!response || result.error && !result.gradingResult) {
      return { id: test.description, lang: test.vars.expected_lang, pass: false, error: result.error };
    }
    const output = typeof response === 'string' ? JSON.parse(response) : response;
    return { id: test.description, lang: test.vars.expected_lang,
      ...check(output, { vars: test.vars }), answer: output.answer,
      sources: output.sources, elapsed_ms: output.elapsed_ms,
      source_count: output.sources.length,
    };
  });
  if (outputs[variant].length !== cases.length) throw new Error(`Incomplete run ${variant}`);
}
fs.writeFileSync(path.join(study, 'comparison.json'), JSON.stringify(outputs, null, 2) + '\n');
const percent = value => `${(value * 100).toFixed(1)}%`;
const lines = [
  '# 检索策略对照实验', '',
  '## 比较对象与评测流程', '',
  '本轮比较检索方式变化后，能否找到更多答案证据，以及最终回答能否改善。两组使用相同问题、文档、生成模型和提示词。', '',
  '检索指标由 Python 脚本计算。端到端问答由 promptfoo 批量调用 /ask，并按配置的事实规则检查回答。实际检索由项目代码执行，实际回答由 DeepSeek 生成。', '',
  '| 名称 | 候选片段的来源 | 精排后的处理 |',
  '|---|---|---|',
  '| 原向量方案（vector） | 向量检索找出 20 块 | 保留精排前 5 块，作为生成资料 |',
  '| 改进检索方案（候选） | 中文使用 hybrid，英文使用 vector | 先保留精排前 5 块，再补相邻块，最多 10 块且片段总长不超过 2560 token |', '',
  '逐题记录中的“vector 回答”指原向量方案生成的答案，“候选回答”指改进检索方案生成的答案。“候选”是实验阶段的名称，这套检索组合后来被采用为默认配置。', '',
  '## vector、hybrid 与 language 的含义', '',
  '- vector 是向量检索。embedding 模型将问题和文档片段转换为数字向量，Chroma 按相似程度选择片段。相关表达即使用词不同，也可能被找到；效果取决于模型和语料。',
  '- BM25 是词法检索，主要根据问题和片段共享的词项评分，同时考虑词项出现频率、区分度和片段长度。本实现的英文使用字母数字词项，中文使用连续汉字二元组，例如“评测游戏”拆成“评测”“测游”“游戏”。',
  '- hybrid 是融合检索。向量检索与 BM25 各找出 20 块，用 RRF 将两路排名折算成分数并相加，保留融合排名前 20 块，再进行精排。同一片段同时出现在两路结果中时，会累计两边的排名分数。',
  '- language 是按问题语种选择检索方式的配置开关。中文走 hybrid，英文走 vector。', '',
  '```text',
  'vector    问题 → 向量检索 20 块 → 精排选出 5 块',
  'hybrid    问题 → 向量检索 20 块 ＋ BM25 检索 20 块',
  '                → RRF 融合保留 20 块 → 精排选出 5 块',
  'language  中文选择 hybrid，英文选择 vector',
  '```', '',
  '## 精排种子、相邻块与长度预算', '',
  '精排模型重新比较问题与候选片段的相关程度。精排保留的前 5 块称为“种子”，即优先放入生成资料的核心片段。', '',
  '相邻块按同一文档的切块编号确定。半径为 1 时，选中第 13 块后，可补充第 12、14 块；半径为 0 时只使用精排结果。相邻块有助于接回被切块边界截断的说明。', '',
  '```text',
  '文档顺序    第 12 块 ← 第 13 块 → 第 14 块',
  '处理方式      可补充    核心块     可补充',
  '```', '',
  '扩充时先保留精排种子，再从精排第一名开始，依次尝试加入其前一块、后一块，然后处理后续种子。重复片段去重。达到数量或长度限制后停止添加，因此各个种子的邻块可能只补入一部分。', '',
  '数量限制为最多 10 块，长度限制为这些片段各自 token 数之和最多 2560。token 是模型计算文本长度的单位。预算仅统计片段，完整生成输入还包括用户问题和提示词。', '',
  '## 实验条件', '',
  '- 同一中英文语料、切块、embedding、精排模型、生成提示词和题目。开发检索集为中英各 22 题。',
  '- 向量与 BM25 各召回 20 条，等权 RRF 的常数为 60，融合后保留 20 条，cross-encoder 精排至 5 条。',
  '- BM25 使用 k1=1.5、b=0.75。英文按字母数字词项，中文按连续汉字二元组，单个汉字保留为词项。词项未做语义扩展。',
  '- 相邻块半径为 1，优先保留精排种子，再按种子排名添加同文档邻块，上限 10 块、片段 token 总和 2560。预算不含提示词和问题。',
  '- 端到端基线使用 vector、相邻块半径 0。候选使用 language、相邻块半径 1，其中中文 hybrid、英文 vector。',
  '- 端到端串行调用相同 deepseek-chat，temperature=0.7。答案缓存与 promptfoo 响应缓存关闭，向量和精排缓存可生效。',
  '- 8 道新验收问题在查看检索实验结果前冻结。它们来自同一论文，部分证据与开发题重叠。', '',
  '## 检索指标的计分方法', '',
  '标注块是题库预先标记的答案相关证据块。候选片段是第一轮检索找出的资料；在本实验中，其数量上限为 20。最终上下文是实际交给 DeepSeek 的全部片段。', '',
  '| 表中指标 | 检查阶段 | 一道题如何计分 |',
  '|---|---|---|',
  '| 初筛命中率，即候选任一标注块命中 | 精排之前的前 20 块 | 找到至少一个标注块记为命中，再计算命中题数占全部题数的比例 |',
  '| 精排命中率，即种子 top-5 命中 | 精排留下的 5 个核心片段 | 找到至少一个标注块记为命中 |',
  '| 精排 MRR，即种子 MRR | 精排留下的 5 块及其排名 | 每题取第一个标注块排名的倒数，再对所有题平均。第 1 名得 1，第 2 名得 0.5，前 5 块未找到得 0 |',
  '| 最终资料命中率，即上下文任一标注块命中 | 补充相邻块之后的全部生成资料 | 找到至少一个标注块记为命中 |',
  '| 平均资料长度，即平均片段 token | 最终生成资料 | 统计每题片段的 token 总和，再求平均，用于观察输入量增加多少 |', '',
  '计分示例采用中文四基准题，其标注证据为第 13、14 块。下表说明“任一标注块命中”的计分规则。', '',
  '| 假设初筛结果 | 初筛是否命中 |',
  '|---|---|',
  '| 包含第 13 块，未包含第 14 块 | 是 |',
  '| 两块都包含 | 是 |',
  '| 两块都未包含 | 否 |', '',
  '中文 vector 的初筛命中率为 59.1%，对应 22 道题中有 13 道至少找到一个标注块。四基准题需要跨块信息才能完整回答，找到其中一块后仍可能遗漏 WebShop，答案完整性由后面的问答检查继续判断。', '',
  '## 检索结果', '',
  'zh 表示中文，en 表示英文。每一行在对应语种的 22 道检索题上统计，邻块半径 0、1 分别表示关闭、开启前后各一块的扩充。', '',
  '| 语种 | 检索方式 | 邻块半径 | 初筛命中率（20 块） | 精排命中率（5 块） | 精排 MRR | 最终资料命中率 | 平均资料长度（token） |',
  '|---|---|---|---|---|---|---|---|',
  ...retrieval.summary.map(row => `| ${row.lang} | ${row.mode} | ${row.neighbors} | ${percent(row.candidate_hit)} | ${percent(row.seed_hit)} | ${row.seed_mrr.toFixed(3)} | ${percent(row.context_hit)} | ${row.context_tokens.toFixed(0)} |`), '',
  '标注块可能提供替代证据，也可能分担不同答案要点。任一块命中和标注块覆盖率均不能直接代表答案完整。邻块方案的上下文更大，种子 top-5 指标用于保持相同候选规模的比较。', '',
  '## 候选选择与逐题变化', '',
  '中文使用 hybrid 加邻块。英文 hybrid 的种子 top-5 命中从 19/22 降至 18/22，因此英文候选采用 vector 加邻块。候选选择依据开发集表现。', '',
];
for (const lang of ['zh', 'en']) {
  const baseline = retrieval.rows.filter(row => row.lang === lang && row.mode === 'vector' && row.neighbors === 0);
  const candidate = retrieval.rows.filter(row => row.lang === lang && row.mode === (lang === 'zh' ? 'hybrid' : 'vector') && row.neighbors === 1);
  const gains = candidate.filter(row => row.context_hit && !baseline.find(base => base.id === row.id).context_hit);
  const losses = candidate.filter(row => !row.context_hit && baseline.find(base => base.id === row.id).context_hit);
  lines.push(`- ${lang} 的上下文新增命中题为 ${gains.map(row => row.id).join('、') || '无'}，退步题为 ${losses.map(row => row.id).join('、') || '无'}。`);
}
lines.push('', '## 端到端规则检查', '',
  '端到端检查从输入问题开始，经过检索与生成，检查最终回答。此阶段使用 12 道开发题及 8 道预先冻结的验收题，共 20 题。检索表中的 44 题与本节的 20 题分别用于不同层次的评估。', '',
  '本节“通过”表示响应格式、检索语种路由、答案缓存绕过和必答事实规则均通过。语种路由检查是否进入预期的中英文库；实际回答使用哪种语言，在后续语义评估中另行评分。', '',
  '实际案例 zh-02 中，原向量方案的最终片段包含第 13 块，缺少后续的第 14 块，回答遗漏 WebShop。改进方案补入所需资料后，最终回答完整列出 HotPotQA、FEVER、ALFWorld 和 WebShop。', '',
  '| 题组 | 原向量方案（vector） | 改进检索方案（候选） |', '|---|---|---|');
for (const [label, predicate] of [
  ['开发题', row => !row.id.startsWith('acceptance-')],
  ['验收题', row => row.id.startsWith('acceptance-')],
]) {
  const values = ['vector', 'candidate'].map(variant => {
    const rows = outputs[variant].filter(predicate);
    return `${rows.filter(row => row.pass).length}/${rows.length}`;
  });
  lines.push(`| ${label} | ${values[0]} | ${values[1]} |`);
}
lines.push('', '| 题目 | 原向量方案（vector） | 改进检索方案（候选） | 原方案片段数 | 改进方案片段数 |', '|---|---|---|---|---|');
for (const baseline of outputs.vector) {
  const candidate = outputs.candidate.find(row => row.id === baseline.id);
  lines.push(`| ${baseline.id} | ${baseline.pass ? '通过' : '失败'} | ${candidate.pass ? '通过' : '失败'} | ${baseline.source_count ?? '-'} | ${candidate.source_count ?? '-'} |`);
}
lines.push('', '## 适用范围', '',
  '- 结果来自小规模、同论文开发与验收题，指标针对当前标注。验收题未用于配置选择，但证据主题并非全部独立。',
  '- 生成结果为单次采样。规则检查覆盖必答模式，完整正确性与依据一致性仍需独立语义复核。',
  '- 扩充上下文增加了输入量。服务端未返回 token 账单数据，无法据此计算实际费用。',
  '- 英文回答语言仍由当前提示词与模型决定。',
  '- 词法统计按请求读取当前 collection 重新计算，避免文档更新后复用旧词法快照。大语料场景需要另行评估开销。', '',
  '## 采用配置', '',
  '默认采用 RETRIEVAL_MODE=language、CONTEXT_NEIGHBORS=1、CONTEXT_MAX_CHUNKS=10、CONTEXT_MAX_TOKENS=2560。旧基线通过显式设置 RETRIEVAL_MODE=vector、CONTEXT_NEIGHBORS=0 复现。', '',
  '候选结果为开发题 10/12、验收题 8/8，基线分别为 8/12 和 7/8。英文作者机构 en-01 与中文受控比较 zh-19 仍未完成。zh-19 缺少关键证据时生成了较长的概括，需继续检查回答依据。', '',
  '## 逐题回答对照', '');
for (const baseline of outputs.vector) {
  const candidate = outputs.candidate.find(row => row.id === baseline.id);
  const test = cases.find(test => test.description === baseline.id);
  lines.push(`### ${baseline.id}`, '', `问题为 ${test.vars.query}`, '',
    `参考答案为 ${test.metadata.reference_answer}`, '',
    '**vector 回答（原向量方案）**', '', baseline.answer || baseline.error,
    '', '**候选回答（改进检索方案）**', '', candidate.answer || candidate.error,
    '', `候选规则检查结果为${candidate.pass ? '通过' : '失败'}。${(candidate.reason || candidate.error || '')
      .replaceAll('Required fact pattern missing: ', '缺少必答事实匹配，规则为 ')
      .replaceAll('Response structure, route, cache bypass and required fact patterns passed', '响应结构、语种路由、答案缓存绕过和必答事实检查均通过')}`, '');
}
fs.writeFileSync(path.join(reportDirectory, 'RETRIEVAL_COMPARISON.md'), lines.join('\n'));
for (const variant of ['vector', 'candidate']) {
  console.log(variant, outputs[variant].filter(row => row.pass).length, '/', outputs[variant].length);
}
