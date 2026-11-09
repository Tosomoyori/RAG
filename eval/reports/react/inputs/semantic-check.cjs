module.exports = (output, context) => {
  const grade = output.grade;
  const fail = [];
  for (const dimension of ['grounding', 'behavior', 'language']) {
    if (grade[dimension] !== 2) fail.push(`${dimension}=${grade[dimension]}`);
  }
  if (context.vars.expected_behavior !== 'abstain' && grade.correctness !== 2) {
    fail.push(`correctness=${grade.correctness}`);
  }
  return { pass: fail.length === 0, score: fail.length === 0 ? 1 : 0,
    reason: `${fail.join(', ') || 'All semantic dimensions passed'}. ${grade.reason}` };
};
