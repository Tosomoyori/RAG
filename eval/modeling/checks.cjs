module.exports = output => {
  const x = typeof output === 'string' ? JSON.parse(output) : output;
  const valid = x.status === 'complete' && x.generation_finish_reason === 'stop';
  const pass = valid && (x.variant === 'closed-book' ? x.grade?.correctness === 2 : x.strict_pass === true);
  return {pass, score: pass ? 1 : 0,
    reason: !valid ? `Execution or output issue: ${x.status}/${x.generation_finish_reason}` :
      (x.variant === 'closed-book' ? `Closed-book correctness=${x.grade.correctness}; grounding excluded` :
        `Semantic=${x.semantic_pass}; annotated evidence=${x.evidence_complete}; ${x.grade.reason}`)};
};
