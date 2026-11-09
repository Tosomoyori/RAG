const fs = require('node:fs');
const path = require('node:path');

module.exports = class SavedGenerationComparison {
  id() { return 'saved-paired-generation-comparison'; }
  async callApi(prompt) {
    const [id, variant] = prompt.trim().split(/\s+/);
    if (!/^tb-dev-\d{2}$/.test(id) || !/^hybrid-n[01]$/.test(variant)) throw new Error('Invalid saved observation');
    const run = process.env.THREEBODY_RUN_DIR;
    if (!run) throw new Error('Run directory required');
    return {output: JSON.parse(fs.readFileSync(path.join(run, `${id}-${variant}.json`), 'utf8'))};
  }
};
