const fs = require('node:fs');
const path = require('node:path');

module.exports = class PilotReplay {
  id() { return 'threebody-saved-answer-replay'; }
  async callApi(prompt) {
    const run = process.env.THREEBODY_RUN_DIR;
    const annotations = process.env.THREEBODY_ANNOTATION_DIR;
    if (!run || !annotations) throw new Error('Run and annotation directories are required');
    const cases = JSON.parse(fs.readFileSync(path.join(annotations, 'cases.frozen.json'), 'utf8'));
    const item = cases.find(c => c.id === prompt);
    if (!item) throw new Error('Unknown case');
    const saved = JSON.parse(fs.readFileSync(path.join(run, `${item.id}.json`), 'utf8'));
    if (item.behavior === 'abstain') {
      return {output: {...saved, expected_behavior: 'abstain', evidence_groups_hit: [],
        evidence_coverage: null, all_evidence_found: null, evidence_applicable: false,
        replay: true, annotation_review: item.annotation_review}};
    }
    const indexes = new Set(saved.sources.map(s => s.metadata.index));
    const hits = item.evidence.map(e => e.acceptable_indexes.some(i => indexes.has(i)));
    return {output: {...saved, evidence_groups_hit: hits,
      evidence_coverage: hits.filter(Boolean).length / hits.length, all_evidence_found: hits.every(Boolean),
      replay: true, annotation_review: item.annotation_review}};
  }
};
