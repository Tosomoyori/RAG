# 文档评测档案

每份文档使用独立目录，集中保存报告、评测输入快照和原始运行记录。

| 文档编号 | 语料 | 档案 |
|---|---|---|
| react | ReAct 英文原文及中文译文 | [ReAct 评测档案](react/README.md) |
| modeling | 三篇数模论文正文；四项对照已完成 | [可点击图文报告](modeling/FINAL_EVALUATION.html)／[Markdown版](modeling/FINAL_EVALUATION.md)／[24道题](modeling/QUESTIONS.md)／[档案](modeling/README.md) |
| threebody | 三体 EPUB 第一册；本轮已完成 | [可点击图文报告](threebody/FINAL_EVALUATION.html)／[Markdown版](threebody/FINAL_EVALUATION.md)／[40道题](threebody/QUESTIONS.md)／[分阶段档案](threebody/README.md) |

## 目录约定

```text
eval/reports/<document-id>/
├── README.md
├── BASELINE.md
├── RETRIEVAL_BASELINE.md
├── RETRIEVAL_COMPARISON.md
├── SEMANTIC_REVIEW.md
├── SEMANTIC_EVALUATION.md
├── inputs/
└── raw/
```

`inputs/` 保存本轮题库、配置、评分标准及提示词快照。`raw/` 保存完整回答、片段、评分、运行清单和历史归档，已加入 Git 忽略规则。报告和输入快照可随仓库提交。

新增文档使用新的 document-id，并建立对应题库与配置。报告生成脚本支持环境变量 `RAG_EVAL_REPORT_DIR` 指定该文档的档案路径，默认路径为 `eval/reports/react`。脚本从指定目录的 `inputs/` 与 `raw/` 读取数据。

模型评测命令的测试配置和输出路径需要对应同一份文档。`package.json` 中 `eval:rag`、`eval:semantic:*` 对应 ReAct，`eval:threebody:*` 对应三体实验。ReAct 工具见 [promptfoo 目录](../promptfoo/README.md)，三体工具见 [threebody 方法档案](../threebody/README.md)。已完成的保留题不重复运行以选择更好结果。
