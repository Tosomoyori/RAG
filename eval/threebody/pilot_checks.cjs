module.exports = (output) => {
  const value = typeof output === 'string' ? JSON.parse(output) : output;
  const fail = [];
  if (!value.response?.answer?.trim()) fail.push('Missing answer');
  if (value.response?.cache_hit !== false) fail.push('Answer cache was not bypassed');
  if (!Array.isArray(value.sources) || !value.sources.length) fail.push('Missing source trace');
  if (value.expected_behavior === 'abstain') {
    if (value.evidence_applicable !== false || value.evidence_coverage !== null) {
      fail.push('Abstention evidence coverage must be not applicable');
    }
  } else if (!value.all_evidence_found) fail.push(`Evidence coverage=${value.evidence_coverage}`);
  for (const key of ['correctness', 'grounding', 'behavior', 'language']) {
    if (value.grade?.[key] !== 2) fail.push(`${key}=${value.grade?.[key]}`);
  }
  return {pass: fail.length === 0, score: fail.length ? 0 : 1,
    reason: `${fail.join('; ') || 'All pilot checks passed'}. ${value.grade?.reason || ''}`};
};
