# 数模论文RAG四项对照

本轮已完成。使用三篇论文的71页正文、24道比较题，比较候选数量、精排保留数量、精排开关和切块大小。8组配置共192份RAG回答，另有24份无文档回答；全部使用问题在运行前固定，未设置独立保留集。

阅读入口：[可点击图文报告](../reports/modeling/FINAL_EVALUATION.html)、[Markdown报告](../reports/modeling/FINAL_EVALUATION.md)、[24道题与参考](../reports/modeling/QUESTIONS.md)、[固定实验方案](PLAN.md)。HTML附录可展开所有配置的实际答案和自动评分理由。

## 数据与隔离

- 原始PDF在本地 `数模论文/`，已忽略；完整提取文本、切块在 `eval/corpora/modeling/local/`，索引在 `eval/indexes/modeling/`，均已忽略。
- 完整检索片段、回答、每次评分和API用量在 `eval/reports/modeling/raw/study-v1/`，已忽略。正式报告、题库、实验配置可本地审查；本轮未上传或共享Promptfoo运行结果。
- 输入身份见 `eval/reports/modeling/inputs/manifest.json`。原论文 `chroma_db/` 的文件集合与哈希在实验前后保持一致；未切换生产检索配置。
- 来源页码为PDF物理页码。原文锚点用文档、页码和去空白后的字符位置表示，跨三种切块共用。

## 工具入口

使用项目已选定的conda RAG环境，无新增依赖。以下命令均在项目根目录执行。

```powershell
# 离线重建报告：核验输入，读取已保存结果，不调用模型
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' -X utf8 eval/modeling/report.py

# 离线重放Promptfoo断言：不需要启动服务，不调用模型
$env:PROMPTFOO_CONFIG_DIR = 'D:\Project\RAG\eval\reports\modeling\raw\promptfoo-config'
$env:PROMPTFOO_DISABLE_TELEMETRY = '1'
$env:PROMPTFOO_DISABLE_UPDATE = '1'
node node_modules/promptfoo/dist/src/entrypoint.js eval -c eval/modeling/promptfooconfig.replay.json --no-cache --max-concurrency 2 --no-share --no-progress-bar --no-table
```

`study.py prepare`固定题目与正文，已完成后拒绝覆盖原manifest；`study.py retrieve`构建隔离索引并保存检索，已有观测不重复执行。`server.py`仅绑定本机接口，按题号与配置保存一次生成，已有完整结果直接返回；无效评分最多再尝试一次。服务调用生成与评分API，离线报告及本地重放不调用。

## Promptfoo适配修正记录

首次实际运行使用 `promptfooconfig.json`，HTTP响应转换错误地返回对象本身，没有放入provider要求的`output`字段，工具将216项记为“No output”。216份实际模型回答和评分均已保存。初始配置及运行结果保留，用于复核。

`promptfooconfig.http-fixed.json`已修正为 `({output: json})`，并用已有记录验证接口转换成功，没有重新生成。最终全部216项的断言由 `promptfooconfig.replay.json` 与本地文件provider `replay.cjs`核验，结果150通过、66未通过、0工具错误。该总数混合不同检查口径，不当作回答准确率；各实验成绩以最终报告分表为准。

本轮4次裁判响应格式／规则校验失败均保留原始返回及用量，只对原答案重试，220次评分尝试最终得到216份有效评分。没有截断回答，没有重新生成挑选答案。

## 结果边界

本轮为单因素、小样本、每条件单次采样；比较用题不作独立泛化测试。原论文自身的模型、数值或排版问题不作为本轮修订对象。自动裁判及AI原文核对不等同于独立人工准确率。各单因素较优值的组合没有执行，不宣称获得全局最优参数。
