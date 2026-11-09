module.exports = (output) => {
  const value = typeof output === 'string' ? JSON.parse(output) : output;
  const failures = [];
  for (const [key, allowed] of Object.entries(value.expected_scores || {})) {
    if (!allowed.includes(value.grade?.[key])) failures.push(`${key}=${value.grade?.[key]}; expected ${allowed}`);
  }
  if (value.require_unsupported_claims && !value.grade?.unsupported_claims?.length) {
    failures.push('Unsupported added detail was not identified');
  }
  if (value.require_source_errors && !value.grade?.source_errors?.length) failures.push('Source attribution error was not identified');
  if (value.require_no_source_errors && value.grade?.source_errors?.length) failures.push('Valid attribution was rejected');
  return {pass: !failures.length, score: failures.length ? 0 : 1,
    reason: `${failures.join('; ') || 'Controlled case expectations matched'}. ${value.grade?.reason || ''}`};
};
