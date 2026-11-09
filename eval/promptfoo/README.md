# RAG 评测运行工具

ReAct 文档的报告、输入快照和原始记录集中于 [ReAct 评测档案](../reports/react/README.md)。

## 评测范围

本套件通过 HTTP 调用现有 `/ask` 接口，包含中英各 6 题。题型覆盖机构、基准、思想与行动区别、lookup 行为、评测游戏数量和受控比较。

参考答案已对照分块预览核对。`preflight.py` 进一步检查标准证据与当前 Chroma 对应块一致，并记录文档、代码、配置和集合内容哈希。

自动评分检查响应结构、语种路由、答案缓存绕过及必答事实的正则匹配。完整语义正确性和依据一致性需要补充语义评估。原始标注仍需独立人工复核。

## 运行条件

- Node.js 版本满足 promptfoo 0.125.1 的要求，使用 `npm ci` 安装锁定依赖。
- Python 使用项目既有运行环境，包含 requirements.txt 所列依赖。
- 本地模型、现有中英 Chroma 库及 DeepSeek 凭据可用。
- 服务运行期间保持文档、参数和索引固定。

## 执行流程

以下 PowerShell 命令从项目根目录执行。Python 路径对应当前验证环境。

终端一启动评测服务。

```powershell
$env:PYTHONUTF8 = '1'
$env:CACHE_BACKEND = 'memory'
$env:QUEUE_BACKEND = 'memory'
$env:QUEUE_WORKER_IN_APP = '0'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' -m uvicorn app:app --host 127.0.0.1 --port 8000
```

终端二核对证据并运行评测。预检查失败时需要先核对文档与标注。

```powershell
$env:PYTHONUTF8 = '1'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/promptfoo/preflight.py
if ($LASTEXITCODE -ne 0) { throw 'Evidence preflight failed' }
$env:PROMPTFOO_CONFIG_DIR = Join-Path $PWD 'eval\promptfoo\results\runtime'
$env:PROMPTFOO_DISABLE_TELEMETRY = '1'
$env:PROMPTFOO_EVAL_TIMEOUT_MS = '240000'
npm run eval:rag
npm run eval:rag:report
```

评测存在失败题时，promptfoo 返回非零退出码，同时写出结果文件。报告命令复用已保存的回答并应用当前规则。

本地浏览结果时，在同一终端执行以下命令，沿用相同配置目录。

```powershell
npx promptfoo view
```

## 交付文件

| 文件 | 内容 |
|---|---|
| cases.json | 问题、参考答案、证据和事实匹配规则 |
| promptfooconfig.yaml | HTTP 接入和断言配置 |
| response-checks.cjs | 响应与事实规则 |
| preflight.py | 当前库的证据一致性检查和运行清单 |
| report.cjs | 保存回答的重评分与报告生成 |
| ../reports/react/BASELINE.md | 首批运行结果及失败复核 |
| ../reports/react/raw/baseline.json | 完整原始回答、检索片段和评分 |
| ../reports/react/raw/reviewed.json | 按当前规则重评分后的逐题结果 |
| ../reports/react/raw/manifest.json | 运行前语料、代码及配置哈希 |

`eval/reports/*/raw/` 已加入 Git 忽略规则。下一轮运行会覆盖同名原始结果、清单及报告，需要保留的运行应提前归档。

## 检索对照实验

当前服务默认使用 `RETRIEVAL_MODE=language`、`CONTEXT_NEIGHBORS=1`。对照基线使用 `RETRIEVAL_MODE=vector`、`CONTEXT_NEIGHBORS=0`。四组开发检索实验与两组端到端结果见 [检索对照报告](../reports/react/RETRIEVAL_COMPARISON.md)。原始首轮结果已归档至本地 `eval/reports/react/raw/archives/initial-baseline/`。

开发检索实验从项目根目录执行，并为每次运行指定新的输出目录。

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/compare_retrieval.py --output-dir eval/reports/react/raw/retrieval-study-new
```

两种端到端配置均运行 `promptfooconfig.compare.yaml`，包含 12 道开发题及 8 道冻结验收题。每种服务配置启动后，分别运行以下命令，并将 `<variant>` 替换为 `vector` 或 `candidate`。

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/promptfoo/preflight.py --cases cases.json acceptance.json --output-dir eval/reports/react/raw/retrieval-study/<variant>
npx promptfoo eval -c eval/promptfoo/promptfooconfig.compare.yaml --no-cache --max-concurrency 1 --no-share --no-table --output eval/reports/react/raw/retrieval-study/<variant>/end-to-end.json
```

完成两组后执行 `node eval/promptfoo/compare-report.cjs` 生成对照报告。预检查与评测须使用相同环境配置，结果目录需要对应本次实验。标准结果路径会被后续运行覆盖。

## 回答语义评估

语义评估使用冻结片段，包含 20 道保存回答和 8 道边界问题。参考答案与 AI 参考评分仅提供给裁判，生成模型只接收问题、片段及目标语言。正确性、依据一致性、证据边界行为和主要回答语言分别评分。

参考复核见 [AI 证据复核表](../reports/react/SEMANTIC_REVIEW.md)，校准分歧、提示词对照和失败案例见 [语义评估报告](../reports/react/SEMANTIC_EVALUATION.md)。参考标注由 AI 完成，独立人工复核待完成。裁判与生成均为 deepseek-chat，评分存在共同偏差。

```powershell
New-Item -ItemType Directory -Force eval/reports/react/raw/semantic-study | Out-Null
$env:PROMPTFOO_CONFIG_DIR = Join-Path $PWD 'eval\promptfoo\results\runtime'
$env:PROMPTFOO_DISABLE_TELEMETRY = '1'
$env:PYTHONUTF8 = '1'
npm run eval:semantic:calibrate
npm run eval:semantic
npm run eval:semantic:report
```

`eval:semantic` 比较 legacy 和 grounded-v1。后续候选使用各自的 `promptfooconfig.semantic-v2.json` 至 `promptfooconfig.semantic-v5.json`，导出至 `eval/reports/react/raw/semantic-study/prompts-v2.json` 等对应文件，再执行报告命令。每个候选运行 28 题，每题包含一次生成与一次评分。评分不通过会返回非零退出码，导出仍可供复核。

Python provider 使用已验证的 conda RAG 解释器路径，其他机器需在配置中指定对应的已安装环境。运行需要现有 DeepSeek 凭据，会产生模型调用费用。后续运行会覆盖同名结果，需保留的运行应先归档。

正常服务和实验共用项目根目录的 `prompts.json`。`RAG_PROMPT_VERSION` 默认 `legacy`，候选版本可显式配置后重启服务。答案缓存键包含模板内容指纹。候选曾出现项目编号转金额等退步，本轮未选定新的默认提示词。

## 已知边界

- `use_cache=false` 跳过答案缓存，向量缓存与精排缓存仍可生效。
- `lang` 表示检索路由。当前规则尚未强制回答使用提问语言。
- 正则可以漏识别同义表达，也可以匹配到否定句或错误关联。首批结果保留了 en-19 的规则修订记录。
- 现有检索脚本按任一标准块命中计分。需要多块证据的问题仍可能出现检索命中、答案不完整。
- 本轮调用实际生成模型，费用以 DeepSeek 账单为准。HTTP 接口未返回 token 用量。
- 当前温度为 0.7，单次运行结果需要通过重复实验评估波动。

## 文档档案路径

三个报告生成命令默认从 `eval/reports/react/inputs/` 和 `eval/reports/react/raw/` 读取数据，并将 Markdown 报告写入 `eval/reports/react/`。其他文档可设置 `RAG_EVAL_REPORT_DIR`，同时提供该目录的输入快照与原始结果。当前模型评测命令仍使用 ReAct 题库及输出路径。
