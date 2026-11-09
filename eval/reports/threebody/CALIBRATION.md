# 三体语义裁判受控检查

## 范围

8 个 AI 编制的受控样例，使用开发事实和人为控制的短上下文。期待分数不发送给裁判，实际评分与预设集合由 Promptfoo JavaScript 断言比较。未使用保留题，尚无独立人工评分或跨模型复核。

结果：8/8 符合预期，0 不符合，0 运行错误。

| 样例 | 情况 | 正确/依据/行为/语言 | 符合预期 |
|---|---|---|---|
| cal-01 | supported_correct | 2/2/2/2 | 是 |
| cal-02 | contradicted_answer | 0/0/0/2 | 是 |
| cal-03 | correct_but_unsupported | 2/0/0/2 | 是 |
| cal-04 | retrieval_insufficient_refusal | 0/2/2/2 | 是 |
| cal-05 | unanswerable_refusal | 2/2/2/2 | 是 |
| cal-06 | invented_price | 0/0/0/2 | 是 |
| cal-07 | corrected_false_premise | 2/2/2/2 | 是 |
| cal-08 | unsupported_extra_detail | 2/1/1/2 | 是 |

这些检查证明裁判在所选的简单控制样例上符合预设，不证明复杂小说问题评分无偏。开发基线中的失败和边界回答仍需逐题复核；同模型系列生成与评分的共同偏差仍然存在。
