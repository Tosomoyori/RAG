# 评测目录

数模论文四项对照已完成，见[可点击图文报告](reports/modeling/FINAL_EVALUATION.html) / [Markdown报告](reports/modeling/FINAL_EVALUATION.md)。24道题比较候选数、精排保留数、精排开关与切块大小，保存192份RAG回答及24份无文档回答；[题目与参考答案](reports/modeling/QUESTIONS.md)、[实验工具与记录](modeling/README.md)分别保留。

《三体》EPUB 第一册长文档评测已完成，比较方法、参数、结果表和全部题目见 [可点击图文报告](reports/threebody/FINAL_EVALUATION.html) / [Markdown版](reports/threebody/FINAL_EVALUATION.md)。冻结后16道保留题严格通过15/16；[40道正式题及参考答案](reports/threebody/QUESTIONS.md)与[分阶段档案](reports/threebody/README.md)分别保留。

文档评测报告按语料分组，索引见 [文档评测档案](reports/README.md)。ReAct 英文原文及中文译文的报告、题库快照和原始记录集中于 [ReAct 档案](reports/react/README.md)。

## 运行入口

| 入口 | 功能 |
|---|---|
| `run_eval.py` | 当前中英文库的召回、最终片段命中和 MRR |
| `compare_retrieval.py` | 向量、融合检索及相邻块扩充的对照 |
| [promptfoo 工具](promptfoo/README.md) | 问答规则检查、语义评分、提示词实验和报告生成 |

当前检索题库为 `eval_set_zh.json`、`eval_set_en.json`，对应 ReAct 语料。正常运行入口如下。

```powershell
python eval/run_eval.py
python eval/run_eval.py zh
python eval/run_eval.py en -v
```

开启相邻块扩充时，脚本输出 `Hit@Ctx`，MRR 按最终上下文顺序计算。复现早期向量基线需要设置 `RETRIEVAL_MODE=vector`、`CONTEXT_NEIGHBORS=0`。早期基线、指标定义与标注局限见 [ReAct 检索基线记录](reports/react/RETRIEVAL_BASELINE.md)。
