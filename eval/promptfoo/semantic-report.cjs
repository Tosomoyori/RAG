const fs = require('node:fs');
const path = require('node:path');
const { reportDirectory, rawDirectory, inputDirectory } = require('./report-paths.cjs');
const study = path.join(rawDirectory, 'semantic-study');
const cases = JSON.parse(fs.readFileSync(path.join(inputDirectory, 'semantic-cases.json'), 'utf8'));
const dimensions = ['correctness', 'grounding', 'behavior', 'language'];
const reviewNoteTranslations = {
  "Retrieved passages lack author affiliations. The refusal is justified, but the document-level reference is unanswered. Main prose is Chinese.": "检索片段缺少作者所属机构信息。说明依据不足是合理的，但未给出原文中的事实答案。主要解释使用中文，与英文问题的语言要求不符。",
  "Required facts and explanatory statements agree with saved source passages.": "回答中的必答事实和解释与保存的来源片段一致。",
  "Affiliations are present, but the first author name is missing in the extracted header. The full Shunyu Yao name-to-affiliation mapping is not fully readable in these sources.": "片段包含机构信息，但抽取出的署名部分缺少第一作者姓名，现有片段未完整呈现 Shunyu Yao 与所属机构的对应关系。",
  "Sources omit matched trajectories and random training-set selection. GPT-3 appendix details and general ablations do not establish the requested ReAct-versus-Act controls.": "来源片段缺少使用相同轨迹、从训练集随机选取任务实例等关键安排。GPT-3 附录中的实验细节和一般性消融说明，无法支持问题所要求的 ReAct 与 Act 受控比较条件。"
};
const dimensionNames = { correctness: '正确性（C）', grounding: '依据一致性（G）',
  behavior: '证据边界行为（B）', language: '回答语言（L）' };
const scoreGuide = [
  '## 评分项与分值', '',
  'C/G/B/L 按固定顺序记录四项分数，即“正确性／依据一致性／证据边界行为／回答语言”。每项使用 0、1、2 分，2 分表示符合该项要求。', '',
  '| 缩写 | 中文名称 | 检查内容 | 2 分 | 1 分 | 0 分 |',
  '|---|---|---|---|---|---|',
  '| C | 正确性 | 是否完成参考答案要求的信息 | 必答信息完整且正确 | 只有部分必答信息 | 缺少所问的事实答案，或核心事实错误 |',
  '| G | 依据一致性 | 回答中的事实是否得到本次检索片段支持 | 所有事实有依据，合理说明缺失信息也可得 2 分 | 核心答案有依据，但额外细节支持不足 | 核心解释无依据或与片段矛盾 |',
  '| B | 证据边界行为 | 证据充分、缺失、部分充分或问题前提错误时如何处理 | 有证据则回答，缺失则明确说明，前提错误则纠正 | 边界表达含糊，或部分混入猜测 | 将缺少依据的内容当作确定答案，或接受错误前提 |',
  '| L | 回答语言 | 主要解释语言是否与问题要求一致 | 中文问题用中文，英文问题用英文 | 混用语言，要求的语言仍占主导 | 主要解释使用其他语言 |', '',
  '原有 20 道题的正确性对照原文事实答案。新增题中，若参考答案本身要求说明资料缺失，恰当说明依据不足也可获得正确性 2 分；部分答案题需同时给出有依据的部分和缺失说明。', '',
  '例如，en-01 的参考评分为 0/2/2/0。原文有作者机构信息，但这次检索片段没有提供，回答用中文说明无法确定。四项分数分别表示下列判断。', '',
  '| 项目 | 分数 | 本例含义 |',
  '|---|---|---|',
  '| 正确性 C | 0 | 没有完成原文中的作者机构问题 |',
  '| 依据一致性 G | 2 | 说明片段未给出机构，与本次资料相符 |',
  '| 证据边界 B | 2 | 承认证据不足，未猜测机构 |',
  '| 回答语言 L | 0 | 问题为英文，回答的主要解释为中文 |', '',
  '四项分开记录，能够同时呈现任务完成情况和证据处理方式。2/2/2/2 表示四项均满足本表的参考标准。', '',
];
const calibration = JSON.parse(fs.readFileSync(path.join(study, 'calibration.json'), 'utf8'));
const calibrationRows = calibration.results.results.map(result => {
  const output = result.response?.output;
  const test = cases.find(test => test.id === result.testCase.vars.case_id);
  return { id: test.id, expected: test.ai_review, actual: output?.grade,
    error: output ? undefined : result.error };
});
const lines = [
  '# 回答语义评估与提示词对照', '',
  '## 本轮评估的对象与分工', '',
  '本轮固定每道题的检索片段，再比较不同提示词生成的回答。这样控制了找资料的差异，观察提示词对回答正确性、资料使用、证据边界和语言的影响。', '',
  '保存回答的 AI 参考复核由项目中的 AI 证据审查形成。promptfoo 负责组织批量运行、保存回答和执行检查；DeepSeek 既生成回答，也在独立评分调用中根据评分标准给分。独立人工复核待完成。', '',
  ...scoreGuide,
  '## 评估定义', '',
  '- 正确性 C（correctness）检查参考答案要求的信息，依据一致性 G（grounding）检查回答中的全部事实是否得到当前片段支持。',
  '- 证据边界 B（behavior）检查证据充分、缺失、部分充分和错误前提下的回答方式，语言 L（language）检查主要解释语言。',
  '- 综合通过要求 G、B、L 均为 2。需要正常回答或纠正前提时，C 也须为 2。对上下文不足而应拒答的题，综合通过允许未完成原文中的事实问题，正确性分数单独报告。',
  '- 参考复核由 AI 完成，尚无独立人工标注。裁判和回答模型均使用 deepseek-chat，存在共同偏差。', '',
  '## 保存回答的参考复核与评分校准', '',
  '| 维度 | 与 AI 参考分数完全一致 | 有效评分数 |',
  '|---|---|---|',
];
for (const dimension of dimensions) {
  const valid = calibrationRows.filter(row => row.actual);
  const matches = valid.filter(row => row.actual[dimension] === row.expected[dimension]);
  lines.push(`| ${dimensionNames[dimension]} | ${matches.length}/${valid.length} | ${valid.length} |`);
}
lines.push('', '例如正确性一行的 19/20，表示 20 道题中有 19 道的模型裁判分数与 AI 参考分数完全一致。这张表用于观察评分一致程度。有效评分数之外的执行错误单独记录，独立人工验证待完成。', '',
  '| 题目 | AI 参考 C/G/B/L | 裁判 C/G/B/L |', '|---|---|---|');
for (const row of calibrationRows) {
  lines.push(`| ${row.id} | ${dimensions.map(key => row.expected[key]).join('/')} | ${row.actual ? dimensions.map(key => row.actual[key]).join('/') : '执行错误'} |`);
}
lines.push('', '### 分歧记录', '');
for (const row of calibrationRows.filter(row => !row.actual || dimensions.some(key => row.expected[key] !== row.actual[key]))) {
  lines.push(`- ${row.id}。参考复核为 ${reviewNoteTranslations[row.expected.note] || row.expected.note} 裁判理由为 ${row.actual?.reason || row.error}`);
}
const review = ['# 保存回答的 AI 证据复核', '',
  '本表逐项复核检索策略改进后保存的 20 道回答，为后续评分模型校准提供 AI 参考标注。复核同时查看问题、参考答案、实际回答和实际检索片段。独立人工复核待完成。', '',
  ...scoreGuide,
  '## 逐题参考评分', '',
  '题号 en、zh 分别表示英文题、中文题；acceptance 表示检索对照阶段预先冻结的验收题。复核理由说明给分依据，原始回答和评分模型的分歧见 [语义评估报告](SEMANTIC_EVALUATION.md)。', '',
  '| 题目 | 正确性 C | 依据一致性 G | 证据边界 B | 回答语言 L | 中文复核理由 |', '|---|---|---|---|---|---|',
  ...cases.filter(test => test.ai_review).map(test => {
    let note = reviewNoteTranslations[test.ai_review.note] || test.ai_review.note;
    if (test.lang === 'en' && test.ai_review.language === 0 && !note.includes('中文')) {
      note += ' 问题为英文，但回答主要使用中文，因此语言项为 0 分。';
    }
    return `| ${test.id} | ${dimensions.map(key => test.ai_review[key]).join(' | ')} | ${note} |`;
  }), ''];
fs.writeFileSync(path.join(reportDirectory, 'SEMANTIC_REVIEW.md'), review.join('\n'));
const comparisonPath = path.join(study, 'prompts.json');
if (fs.existsSync(comparisonPath)) {
  const comparison = JSON.parse(fs.readFileSync(comparisonPath, 'utf8'));
  const variants = ['legacy', 'grounded-v1'];
  const rawResults = [...comparison.results.results];
  const v2Path = path.join(study, 'prompts-v2.json');
  if (fs.existsSync(v2Path)) {
    variants.push('grounded-v2');
    rawResults.push(...JSON.parse(fs.readFileSync(v2Path, 'utf8')).results.results);
  }
  const v3Path = path.join(study, 'prompts-v3.json');
  if (fs.existsSync(v3Path)) {
    variants.push('grounded-v3');
    rawResults.push(...JSON.parse(fs.readFileSync(v3Path, 'utf8')).results.results);
  }
  const v4Path = path.join(study, 'prompts-v4.json');
  if (fs.existsSync(v4Path)) {
    variants.push('grounded-v4');
    rawResults.push(...JSON.parse(fs.readFileSync(v4Path, 'utf8')).results.results);
  }
  const v5Path = path.join(study, 'prompts-v5.json');
  if (fs.existsSync(v5Path)) {
    variants.push('grounded-v5');
    rawResults.push(...JSON.parse(fs.readFileSync(v5Path, 'utf8')).results.results);
  }
  const rows = rawResults.map(result => {
    const output = result.response?.output;
    const test = cases.find(test => test.id === result.testCase.vars.case_id);
    return { id: test.id, group: test.group, lang: test.lang,
      variant: output?.variant || result.provider.label, pass: result.success,
      grade: output?.grade, answer: output?.answer, error: output ? undefined : result.error,
      generation_usage: output?.generation_usage, grading_usage: output?.grading_usage };
  });
  fs.writeFileSync(path.join(study, 'reviewed.json'), JSON.stringify({ calibration: calibrationRows, prompts: rows }, null, 2) + '\n');
  lines.push('', '## 固定片段的提示词对照', '',
    '20 道原有问题与 8 道新增边界问题使用冻结片段。参考答案和行为标注只用于评分，生成模型只接收问题、片段和目标语言。各提示词版本分别新生成回答，每个回答由相同裁判评分。', '',
    'grounded-v1 增加证据不足、错误前提和部分回答规则。查看第一轮结果后，grounded-v2 进一步显式传入目标语言。第二版沿用相同问题，属于开发集上的迭代验证。', '',
    'grounded-v2 的 zh-01 仍补入缺损文本中不完整的作者姓名，模型裁判给了 grounding=2，AI 逐条复核将其判为 grounding=1。grounded-v3 据此限制回答范围、禁止补全缺损姓名，并缩短证据不足时的背景展开。第三版继续沿用本批问题，后续需要新题验证。', '',
    'grounded-v3 在 zh-01 给出机构集合后，又因逐位映射不完整而表达无法回答，裁判给 correctness=1。grounded-v4 进一步要求直接回答已有依据的部分，不把用户未要求的扩展细节作为回答条件。第四版同样属于本批开发题上的迭代。', '',
    'grounded-v4 在 boundary-zh-partial 把机构上标写成“作者1/作者2”，裁判未识别该语义变化。grounded-v5 要求机构问题只列机构名称，不将机构编号转写为作者序号。该问题说明裁判可能漏判细粒度语义错误。', '',
    'grounded-v5 在 boundary-en-funding 将 NSF 项目编号 2107048 当作资助金额 $2,107,048。该结果是实质性回归，裁判识别为 correctness=0、grounding=0、behavior=0。', '',
    '第一轮存在一次裁判 JSON 格式错误，重试配置还出现过一次绝对断言路径兼容错误。最终通过标准配置过滤重跑该题，原始与重试导出均保留。评分器增加了最多一次 JSON 格式修复，不更换被评回答。', '',
    '生成温度为 0.7，裁判温度为 0。单次生成与评分，promptfoo 响应缓存关闭。新增边界题包含资料缺失、部分答案和错误前提。', '',
    '| 题组 | 提示词 | 综合通过 | 正确性 2 分 | 依据 2 分 | 行为 2 分 | 语言 2 分 | 执行错误 |',
    '|---|---|---|---|---|---|---|---|');
  for (const group of ['saved', 'boundary']) {
    for (const variant of variants) {
      const selected = rows.filter(row => row.group === group && row.variant === variant);
      const counts = dimensions.map(key => `${selected.filter(row => row.grade?.[key] === 2).length}/${selected.length}`);
      const groupName = group === 'saved' ? '原有问题' : '新增边界题';
      lines.push(`| ${groupName} | ${variant} | ${selected.filter(row => row.pass).length}/${selected.length} | ${counts.join(' | ')} | ${selected.filter(row => !row.grade).length} |`);
    }
  }
  lines.push('', '## 逐题对照', '', `| 题目 | ${variants.map(variant => `${variant} C/G/B/L`).join(' | ')} |`,
    `|---|${variants.map(() => '---|').join('')}`);
  for (const test of cases) {
    const grades = variants.map(variant => {
      const row = rows.find(row => row.id === test.id && row.variant === variant);
      return row?.grade ? dimensions.map(key => row.grade[key]).join('/') : '执行错误';
    });
    lines.push(`| ${test.id} | ${grades.join(' | ')} |`);
  }
  lines.push('', '## 回答与评分理由', '');
  for (const test of cases) {
    lines.push(`### ${test.id}`, '', `预期行为为 ${test.expected_behavior}。参考答案为 ${test.reference_answer}`, '');
    for (const variant of variants) {
      const row = rows.find(row => row.id === test.id && row.variant === variant);
      lines.push(`**${variant}**`, '', row?.answer || row?.error || '缺失结果', '', row?.grade?.reason || '', '');
    }
  }
  const usage = rows.reduce((total, row) => {
    for (const usage of [row.generation_usage, row.grading_usage]) {
      total.input += usage?.input_tokens || 0;
      total.output += usage?.output_tokens || 0;
    }
    return total;
  }, { input: 0, output: 0 });
  lines.push('## 用量与限制', '',
    `有效提示词对照结果报告输入 token 为 ${usage.input}，输出 token 为 ${usage.output}，包含生成及评分。校准及未计入有效结果的失败、重试调用另计，实际费用以服务账单为准。`, '',
    '- 固定片段实验控制了检索差异。它不能直接证明修改后完整检索链的总体正确率。',
    '- 新边界题与原有问题来自同一论文，未覆盖其他语料、领域和复杂攻击。',
    '- 模型评分存在误判。分歧保留供复核，当前评分适合诊断，尚不足以作为独立质量保证。', '');
  lines.push('## 配置决策', '',
    '项目默认提示词为 legacy。候选通过 RAG_PROMPT_VERSION 切换，正常入口从同一 prompts.json 读取模板，答案缓存键包含模板内容指纹。', '',
    '候选明显改善语言与证据不足处理，但多轮迭代出现作者姓名补全、机构编号误读和项目编号转金额。候选的评分满分与 AI 逐条复核存在分歧，最终版本需要新题、重复生成和独立人工复核后再选定。', '',
    'grounded-v4 另通过 FastAPI TestClient 对 /ask 的四道真实问答检查，覆盖英文作者机构、中文受控比较、中文作者机构及英文训练案例数量。入口检查不能消除冻结片段实验中已经记录的错误。', '');
  for (const variant of variants) {
    const selected = rows.filter(row => row.variant === variant);
    console.log(variant, selected.filter(row => row.pass).length, '/', selected.length);
  }
}
fs.writeFileSync(path.join(reportDirectory, 'SEMANTIC_EVALUATION.md'), lines.join('\n'));
console.log('Calibration agreement', Object.fromEntries(dimensions.map(key => [key,
  calibrationRows.filter(row => row.actual?.[key] === row.expected[key]).length])));
