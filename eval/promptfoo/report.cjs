const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { reportDirectory, rawDirectory, inputDirectory } = require('./report-paths.cjs');
const check = require(path.join(inputDirectory, 'response-checks.cjs'));

const directory = __dirname;
const baseline = JSON.parse(fs.readFileSync(path.join(rawDirectory, 'baseline.json'), 'utf8'));
const cases = JSON.parse(fs.readFileSync(path.join(inputDirectory, 'cases.json'), 'utf8'));
const rows = baseline.results.results.map(result => {
  const test = cases.find(test => test.description === result.testCase.description);
  if (!test) throw new Error(`Unknown case ${result.testCase.description}`);
  const response = result.response?.output;
  if (!response) {
    return { id: test.description, pass: false, reason: result.error, execution_error: true };
  }
  const output = typeof response === 'string' ? JSON.parse(response) : response;
  const grade = check(output, { vars: test.vars });
  const evidenceIndices = test.metadata.evidence
    .filter(evidence => output.sources.some(source => source.trim() === evidence.text))
    .map(evidence => evidence.index);
  return {
    id: test.description,
    lang: test.vars.expected_lang,
    pass: grade.pass,
    original_pass: result.success,
    reason: grade.reason,
    evidence_indices_in_final_context: evidenceIndices,
    answer: output.answer,
    sources: output.sources,
    elapsed_ms: output.elapsed_ms,
  };
});
fs.writeFileSync(path.join(rawDirectory, 'reviewed.json'), JSON.stringify(rows, null, 2) + '\n');
const reviewManifest = {
  baseline_eval_id: baseline.evalId,
  reviewed_at: new Date().toISOString(),
  files_sha256: Object.fromEntries(['cases.json', 'response-checks.cjs', 'report.cjs'].map(name => [
    name, crypto.createHash('sha256').update(fs.readFileSync(
      path.join(name === 'report.cjs' ? directory : inputDirectory, name))).digest('hex'),
  ])),
};
fs.writeFileSync(path.join(rawDirectory, 'review-manifest.json'), JSON.stringify(reviewManifest, null, 2) + '\n');
const lines = [
  '# RAG 接口评测记录', '',
  '## 本轮检查范围与 promptfoo 的作用', '',
  '本轮从原有题库中选择中英各 6 道问题，共 12 道，运行“问题 → 检索片段 → DeepSeek 生成 → 最终回答”的完整流程。原有检索评测检查证据是否被找到，本轮继续检查生成结果是否包含必答事实。', '',
  'promptfoo 负责读取测试题、批量调用 /ask、收集实际回答和片段、执行配置的检查并保存结果。项目代码负责检索与缓存处理，DeepSeek 负责生成回答，事实标准由题库和规则提供。', '',
  '“通过”表示接口响应、检索语种路由、答案缓存绕过和必答事实匹配符合规则。这里的语种路由检查是否进入中英文库，实际回答语言在后续语义评估中单独检查。', '',
  `原始运行编号为 ${baseline.evalId}。`, '',
  '## 运行条件', '',
  '运行配置与语料、代码哈希见本次预检查生成的 raw/manifest.json。完整回答与片段见 raw/baseline.json。', '',
  '## 结果', '',
  `原始规则通过 ${rows.filter(row => row.original_pass).length}/12。按当前规则对保存的回答重评分后，通过 ${rows.filter(row => row.pass).length}/12。重评分复用原始回答。`, '',
  '原始评分见 baseline.json，当前规则的重评分见 reviewed.json。评分规则哈希记录于 review-manifest.json。', '',
  '| 题目 | 原始规则 | 修正规则 | 最终片段中的标准证据块 | 服务耗时 ms |',
  '|---|---|---|---|---|',
  ...rows.map(row => `| ${row.id} | ${row.original_pass ? '通过' : '失败'} | ${row.pass ? '通过' : '失败'} | ${row.evidence_indices_in_final_context?.join(', ') || '未命中'} | ${row.elapsed_ms ?? '执行错误'} |`), '',
  '## 失败案例', '',
  ...rows.filter(row => !row.pass).map(row => `- ${row.id} ${row.reason}`), '',
  '## 评测边界', '',
  '- 通过率表示响应协议、语言路由、答案缓存绕过和关键事实正则检查通过。完整语义正确性、事实间关系及依据一致性仍需单独评分。',
  '- 英文问题的部分回答使用中文。当前断言检查语言路由，回答语言单独记录为后续优化项。',
  '- 单次运行、12 题与 temperature=0.7 限制了结果稳定性判断。',
  '- HTTP 响应未暴露模型 token 用量，因此 promptfoo 中的零 token 统计无法用于费用核算。实际费用以模型服务账单为准。',
  '- 参考答案对照分块预览与当前库核对，尚未经独立人工审定或原 PDF 页面复核。', '',
  '## 逐题回答', '',
  ...rows.flatMap(row => [
    `### ${row.id}`, '',
    `参考答案为 ${cases.find(test => test.description === row.id).metadata.reference_answer}`, '',
    row.answer || row.reason, '',
    `规则结果为${row.pass ? '通过' : '失败'}。${row.reason}`, '',
  ]),
];
fs.writeFileSync(path.join(reportDirectory, 'BASELINE.md'), lines.join('\n'));
console.log(`Reviewed ${rows.length} cases, ${rows.filter(row => row.pass).length} passed`);
