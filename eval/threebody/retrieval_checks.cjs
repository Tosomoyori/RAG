module.exports = (output) => {
  const x = typeof output === 'string' ? JSON.parse(output) : output;
  const fail = [];
  if (!Array.isArray(x.candidate_ids) || !x.candidate_ids.length || x.candidate_ids.length > 20) fail.push('Invalid candidates');
  if (!Array.isArray(x.seed_ids) || x.seed_ids.length > 5) fail.push('Invalid reranked seeds');
  if (x.context_chunks > 10 || x.context_body_tokens > 2560) fail.push('Context budget exceeded');
  if (!Number.isFinite(x.retrieval_ms)) fail.push('Missing timing');
  if (x.generation_api_calls !== 0 || x.grading_api_calls !== 0) fail.push('Unexpected model API call');
  if (x.context_metrics?.evidence_applicable && !x.context_metrics.all_evidence_found) {
    fail.push(`Incomplete annotated evidence: ${x.context_metrics.evidence_coverage}`);
  }
  return {pass: !fail.length, score: fail.length ? 0 : 1,
    reason: fail.join('; ') || (x.context_metrics?.evidence_applicable ? 'All annotated evidence found' : 'Structural checks only; abstention quality not evaluated')};
};
