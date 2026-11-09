const path = require('node:path');

const projectDirectory = path.resolve(__dirname, '../..');
const reportDirectory = process.env.RAG_EVAL_REPORT_DIR
  ? path.resolve(projectDirectory, process.env.RAG_EVAL_REPORT_DIR)
  : path.join(projectDirectory, 'eval/reports/react');

module.exports = {
  reportDirectory,
  rawDirectory: path.join(reportDirectory, 'raw'),
  inputDirectory: path.join(reportDirectory, 'inputs'),
};
