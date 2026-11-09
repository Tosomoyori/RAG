module.exports = (output, context) => {
  const response = typeof output === 'string' ? JSON.parse(output) : output;
  const failures = [];
  if (typeof response.answer !== 'string' || !response.answer.trim()) {
    failures.push('Missing answer');
  }
  if (!Array.isArray(response.sources) || !response.sources.length ||
      response.sources.some(source => typeof source !== 'string' || !source.trim())) {
    failures.push('Missing or invalid source passages');
  }
  if (response.lang !== context.vars.expected_lang) failures.push('Unexpected language route');
  if (response.cache_hit !== false || response.cache_type !== 'miss') {
    failures.push('Expected answer-cache bypass');
  }
  if (!Number.isFinite(response.elapsed_ms) || response.elapsed_ms < 0) {
    failures.push('Invalid elapsed time');
  }
  for (const pattern of JSON.parse(context.vars.required_patterns)) {
    if (!new RegExp(pattern, 'iu').test(response.answer || '')) {
      failures.push(`Required fact pattern missing: ${pattern}`);
    }
  }
  return {
    pass: failures.length === 0,
    score: failures.length === 0 ? 1 : 0,
    reason: failures.join(' | ') || 'Response structure, route, cache bypass and required fact patterns passed',
  };
};
