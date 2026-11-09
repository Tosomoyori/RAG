const fs = require('node:fs');
const path = require('node:path');

module.exports = class SavedModelingStudy {
  id() { return 'saved-modeling-paper-study'; }
  async callApi(prompt) {
    const [caseId, variant] = prompt.trim().split(/\s+/);
    if (!/^(paper-[bc]|statistics)-\d{2}$/.test(caseId) ||
        !['base', 'k10', 'k40', 'n3', 'n8', 'no-rerank', 'chunk128', 'chunk384', 'closed-book'].includes(variant)) {
      throw new Error('Invalid observation identity');
    }
    const file = path.resolve(__dirname, '../reports/modeling/raw/study-v1/answers', `${caseId}--${variant}.json`);
    const result = JSON.parse(fs.readFileSync(file, 'utf8'));
    return {output: result};
  }
};
