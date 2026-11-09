# 三体语料与实验索引

**本轮已完成（2026-11-06）。** 总结、验收边界和复现条件见 [最终评测报告](../reports/threebody/FINAL_EVALUATION.md)。本文件保留各阶段方法与命令，不是待办清单。正式评测范围为第一册；三册全集仅完成索引准备，规模对照为未执行的独立扩展，不影响本轮完成。

## 范围与信息边界

第一阶段建立第一册及三册全集两份固定语料与独立索引，随后完成开发检索及生成对照、来源复核和配置冻结。题库v1包含24道开发题和16道保留题，保留评测已完成，严格规则及自动语义通过均为15/16。8道开发试运行题的历史结果、标注修订和边界见 [试运行报告](../reports/threebody/PILOT.md)。

24 道开发题的首轮基线已完成，原始结果为 23/24 通过、0 运行错误；见 [开发基线](../reports/threebody/DEVELOPMENT_BASELINE.md)。8 个裁判受控样例均符合预设，见 [裁判检查](../reports/threebody/CALIBRATION.md)。原文复核发现章节错引未被裁判识别，自动语义满分不能解释为实际完全正确；原始结果和题库保持不变。

固定语料统计（字符数包含标点及标题）：

| 语料 | 分节数 | 文本块数 | 字符数 |
|---|---:|---:|---:|
| 第一册 | 36 | 865 | 187,784 |
| 全集 | 76 | 4,014 | 876,412 |

全集中的第一册 865 块与单册语料逐块一致，册名、位置及文本哈希相同，仅 `corpus` 范围标签不同。

输入为本地 `The Three-Body Problem.epub`，版本身份由 `corpus_config.json` 中的 SHA-256 固定。该文件与提取的完整正文不纳入版本管理。

| 语料 | 纳入资源 | 边界 |
|---|---|---|
| 第一册 | `part0004.xhtml` 至 `part0039.xhtml` | 36 章，包含尾声 |
| 第二册 | `part0044.xhtml` 至 `part0047.xhtml` | 序章、上部、中部、下部 |
| 第三册 | `part0051.xhtml` 至 `part0057.xhtml` | 纪年表、小说内虚构序言与六部正文 |

排除资源及原因逐项记录于配置中，包括目录、版权页、获奖感言、作者后记、独立脚注页及出版宣传。小说内《时间之外的往事》序言及节选属于叙事内容，予以保留。纪年表作为正文辅助内容保留。独立脚注页不参与检索，后续题库不得依赖这些脚注；正文中的脚注标记仍保留。

基础 HTML 标题作为分节边界；正文中独占一行的 `【…】` 时间／场景标记作为额外边界。未标示的场景不推断为章节，第二册的三部仍保留较大的节范围。标题、父章节、册名、资源地址、父节内字符范围与文本哈希均保存。字符位置指规范化提取文本，非 EPUB 原始字节位置。资源范围及标记已由程序核对，全文逐段人工复核尚未完成。

## 隔离配置

| 内容 | 路径 |
|---|---|
| 第一册索引 | `eval/indexes/threebody/book1/` |
| 全集索引 | `eval/indexes/threebody/trilogy/` |
| 本地正文、切块与验证记录 | `eval/corpora/threebody/local/<scope>/` |
| 可审查的语料清单 | `eval/corpora/threebody/<scope>.manifest.json` |

服务使用 `RAG_INDEX_DIR` 选择索引目录，默认仍为项目根目录的 `chroma_db`。答案缓存按索引绝对路径区分命名空间。上传产生的分块预览可通过 `RAG_ARTIFACT_DIR` 指向实验目录。两项配置均在新进程启动时设置。

## 重建及核验

从项目根目录运行，Python 使用既有 conda RAG 环境，无需新增依赖。所有嵌入操作使用本地模型，关闭联网下载，缓存使用内存后端；不调用回答模型或语义裁判。

```powershell
$env:PYTHONIOENCODING = 'utf-8'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_corpus.py prepare --scope book1
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_corpus.py build --scope book1
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_corpus.py prepare --scope trilogy
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_corpus.py build --scope trilogy
```

`prepare` 固定正文、切块、解析代码、模型文件哈希、模型配置与关键包版本。`build` 仅向空实验集合批量写入；已有集合仅验证，不清空或覆盖，内容不一致时退出。构建中断产生的非完整索引需要另行处理后重建，脚本不自动删除。`verify` 独立核对语料身份、已固定文件及索引全部正文和元数据：

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_corpus.py verify --scope book1
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_corpus.py verify --scope trilogy
```

后续评测服务应使用独立终端及端口，并在启动前选择语料。例如第一册实验服务：

```powershell
$env:RAG_INDEX_DIR = Join-Path $PWD 'eval/indexes/threebody/book1'
$env:RAG_ARTIFACT_DIR = Join-Path $PWD 'eval/corpora/threebody/local/book1'
$env:CACHE_BACKEND = 'memory'
$env:QUEUE_BACKEND = 'memory'
$env:QUEUE_WORKER_IN_APP = '0'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' -m uvicorn app:app --host 127.0.0.1 --port 8001
```

冻结评测期间不通过 `/upload` 修改索引。现有 ReAct Promptfoo 配置仍针对论文语料；三体测试集和配置在后续阶段单独建立，不直接复用论文题目或证据块号。

## Promptfoo 开发试运行

`pilot_cases.json` 包含 8 道开发题。每项必要事实有一组可接受证据位置，同义支持允许多个位置，组间要求全部覆盖。01 与 07 使用同一个基础事实。参考答案和事实标注仅由评测适配服务用于评分，不传入回答模型。

`pilot_server.py` 是本地评测适配服务，调用实际的 `make_retriever()`、`query()` 和生成链，保留完整上下文与元数据。使用 legacy 提示词和当前默认检索配置，单并发运行；不经过普通 `/ask` HTTP 路由，因此本轮不验证生产 HTTP 响应结构。证据覆盖和语义分数共同决定通过。语义裁判使用现有 rubric，但尚未经独立人工校准。

首次终端先使用一个全新的结果目录完成预检查并启动服务：

```powershell
$env:THREEBODY_RUN_DIR = Join-Path $PWD 'eval/reports/threebody/raw/pilot-next'
$env:PYTHONIOENCODING = 'utf-8'
$env:ANONYMIZED_TELEMETRY = 'False'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/pilot_preflight.py --output-dir $env:THREEBODY_RUN_DIR
if ($LASTEXITCODE -ne 0) { throw 'Pilot evidence preflight failed' }
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' -m uvicorn eval.threebody.pilot_server:app --host 127.0.0.1 --port 8002
```

第二终端指定相同结果目录，运行项目本地 NPM 安装的 Promptfoo：

```powershell
$runDirectory = Join-Path $PWD 'eval/reports/threebody/raw/pilot-next'
$env:PROMPTFOO_CONFIG_DIR = Join-Path $runDirectory 'promptfoo-runtime'
$env:PROMPTFOO_DISABLE_TELEMETRY = '1'
$env:PROMPTFOO_EVAL_TIMEOUT_MS = '300000'
npm run eval:threebody:pilot -- --output (Join-Path $runDirectory 'promptfoo.json')
```

当前配置的 HTTP 超时为 300 秒。生成和裁判步骤会产生 API 用量；Promptfoo HTTP provider 顶层 token=0 不能解释为免费。每题原始回答、实际上下文及裁判评分独立保存。首轮 8 题仅记录裁判 token；当前适配服务通过生成回调同时采集生成与裁判 token，并在裁判前保存已生成回答。模型异常会计为运行错误，不能计为正常答错。

若开发阶段修订了证据标注，可以将 `pilot_preflight.py` 输出到新的注释目录，然后使用保存回答重评分：

```powershell
$env:THREEBODY_RUN_DIR = $runDirectory
$env:THREEBODY_ANNOTATION_DIR = Join-Path $runDirectory 'reviewed-annotations'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/pilot_preflight.py --output-dir $env:THREEBODY_ANNOTATION_DIR
if ($LASTEXITCODE -ne 0) { throw 'Revised evidence preflight failed' }
npm run eval:threebody:replay -- --output (Join-Path $runDirectory 'promptfoo-reviewed.json')
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/pilot_report.py --run-dir $runDirectory --output eval/reports/threebody/PILOT.md
```

重评分不重新生成答案，也不重新调用语义裁判。报告校验答案、上下文和裁判分数未变，并分别保留首轮与修订结果。标注修订带来的通过率变化不能表述为检索改善。每次重新生成应使用新的目录，避免覆盖原始结果。

## 40 题题库 v1

[题库说明与开发题复核表](../reports/threebody/QUESTION_BANK.md)记录知识点分组与信息边界。可审查的数据位于 `eval/corpora/threebody/question-bank-v1/`，包括 `development.json`、`holdout.json` 与文件哈希清单。参考标注由 AI 对照本版正文完成，独立人工复核仍待完成。

既有 8 道试运行题全部归开发组，标记为已评测。知识点组不跨开发／保留边界；同一书籍背景仍会共享，分组隔离不代表领域外泛化。4 道无答案题各限定章节或信息范围，不能外推为全书信息缺失。无答案题不计算检索证据覆盖率，以参考缺失字段、实际上下文和裁判的正确性、依据、行为、语言四项检查为准。

题库编制阶段仅静态核验，随后执行了 24 道开发题基线。题库中的 `previously_evaluated` 标记记录编制时的历史（8 道试运行题），当前执行历史以独立运行档案为准，不回写冻结题库。16 道保留题仍未调用检索模型、生成模型或裁判，也未生成可默认执行的 Promptfoo 配置。后续模型与参数选择仅使用开发题；独立人工审阅可以查看保留标注，但不得将保留题的模型结果用于调参后仍称其为未见测试。

重新编制及开发集预检查命令如下。预检查读取 Chroma 中的全部文本及元数据核对一致性，不执行相似度检索或模型推理。

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/build_question_bank.py
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/question_bank_preflight.py --output-dir eval/reports/threebody/raw/development-next
```

开发评测沿用本地适配服务，将 `THREEBODY_RUN_DIR` 指向上面预检查创建的目录。服务器只读取该目录的 `cases.frozen.json`，随后在相同结果目录设置 Promptfoo 环境并执行：

```powershell
npm run eval:threebody:dev -- --output (Join-Path $env:THREEBODY_RUN_DIR 'promptfoo.json')
```

运行时应使用 `promptfooconfig.development.yaml` 的 24 个 ID，不使用 8 题试运行配置。`pilot_report.py` 仅处理原 8 题首轮／重评分档案，不能直接用于 24 题开发报告。修改题库后重新编制会改变身份哈希；正式比较期间须固定题库版本，后续修订应另行归档。

## 裁判受控检查与开发基线

开发预检查会同时冻结 `calibration_cases.json`，其中是开发事实与人为控制上下文，不是小说新测试题。预设分数仅用于 JavaScript 断言，不发送给裁判；当前检查覆盖正确支持、直接矛盾、事实正确但缺少支持、检索缺失时拒答、无答案时拒答、虚构金额、纠正前提及额外无依据细节。

服务启动后先执行受控检查，再执行开发基线，沿用相同新结果目录和 Promptfoo 环境：

```powershell
npm run eval:threebody:calibrate -- --output (Join-Path $env:THREEBODY_RUN_DIR 'calibration.json')
if ($LASTEXITCODE -ne 0) { throw 'Controlled grader checks need review' }
npm run eval:threebody:dev -- --output (Join-Path $env:THREEBODY_RUN_DIR 'promptfoo.json')
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/development_report.py --run-dir $env:THREEBODY_RUN_DIR
```

开发题存在失败时 Promptfoo 返回非零退出码，同时保存结果；报告阶段读取已保存结果，不重新调用模型。报告核对运行输入与题库哈希、开发题 ID 集合及原论文索引文件身份。当前原文复核记录保存在 `development_review.json`，仅适用于其声明的运行版本，不混入其他运行。

受控检查不是独立人工校准。原开发基线暴露了来源核验缺口：其上下文只传正文，没有把片段的真实章节元数据传给生成与裁判；模型可能把其他章节的同义证据错误归到问题指定章节，而裁判仍给满分。该缺口已在以下来源实验中补充，生产默认行为尚未修改。

## 来源标签与冻结上下文对照

来源实验结果见 [来源核验报告](../reports/threebody/SOURCE_ATTRIBUTION.md)。实验适配服务新增可选来源模式，生产管道的默认格式与提示词未改动。`source_context.py` 将真实册名、父章节、section 和 chunk-ID 与正文一起展示；来源规则同时用于裁判，显式声明的章节或片段引用必须匹配实际来源，未要求所有答案强制添加引用。

本轮12个来源受控样例全部符合预设。用来源裁判重评旧答案为22/24通过，标记2处来源问题；同一冻结片段下的标签条件新答案为23/24通过，未被来源裁判标记来源错误。第6题与第21题已对照实际章节元数据复核。第21题仍因原标注位置未命中而失败；题库未修订。旧答案重评中存在1例来源扣分规则执行不一致，原始分数保留。以上是开发集单次对照，不代表整体准确率或检索改善。

新实验目录预检查使用以下选项，复制原基线的每题上下文和答案到本地实验快照，并校验每个片段与固定索引一致：

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/question_bank_preflight.py --source-labels --frozen-source-run eval/reports/threebody/raw/development-baseline-20261105-01 --output-dir eval/reports/threebody/raw/source-labels-next
$env:THREEBODY_RUN_DIR = Join-Path $PWD 'eval/reports/threebody/raw/source-labels-next'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' -m uvicorn eval.threebody.pilot_server:app --host 127.0.0.1 --port 8002
```

第二终端设置同一结果目录及前述 Promptfoo 环境后，依次运行：

```powershell
npm run eval:threebody:calibrate:sources -- --output (Join-Path $env:THREEBODY_RUN_DIR 'calibration.json')
npm run eval:threebody:regrade:sources -- --output (Join-Path $env:THREEBODY_RUN_DIR 'regrade.json')
npm run eval:threebody:dev -- --output (Join-Path $env:THREEBODY_RUN_DIR 'promptfoo.json')
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/source_report.py --run-dir $env:THREEBODY_RUN_DIR
```

来源受控样例共12个，前8个保留基础行为检查，新增错误章节、正确章节、虚构片段ID和不写引用的正确回答。新增上下文是由开发案例缩写的控制材料，不使用保留题。来源规则执行不一致也单独统计，不将识别到错误等同于可靠执行分值。

重评步骤只调用裁判，保留旧答案不变；生成步骤不执行相似度检索，复用完全相同的片段、顺序和元数据，仅改变上下文来源展示及前导说明。正文片段预算保持原配置，但标签增加额外token；该实验不是相同总token预算的检索对照，也没有单独识别格式和前导说明的影响。旧基线报告与档案不被重评分报告覆盖。

## 四组检索开发对照

[检索对照报告](../reports/threebody/RETRIEVAL_COMPARISON.md)记录了24题×4组配置的96次观测，不调用生成或语义裁判。22道可回答题参与证据指标；2道无答案题只执行链路结构检查，不能由此判断拒答质量。16道保留题未运行。

四组为向量／混合召回各搭配关闭／开启同节相邻块扩充；候选20、精排5、正文上限10块及2560 token。模型与查询路径预热后，每次观测清空实验进程内embedding及精排缓存；单并发，配置顺序逐题轮换。缓存清空不影响生产服务或Redis。系统和Chroma底层缓存保留，单次耗时不用于显著性结论。

本轮完整已标注证据覆盖依次为16/22、18/22、18/22和21/22。混合扩充组正文平均约2496 token，混合不扩充约1278 token。当前默认组的24题最终片段ID序列与原基线逐题一致；所有配置的标注及题库保持不变。建议下一阶段优先比较混合召回的扩充开关，验证额外输入对实际回答质量与用量的影响。

新目录预检查与服务启动：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_retrieval_study.py --output-dir eval/reports/threebody/raw/retrieval-next
$env:THREEBODY_RUN_DIR = Join-Path $PWD 'eval/reports/threebody/raw/retrieval-next'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' -m uvicorn eval.threebody.retrieval_server:app --host 127.0.0.1 --port 8003
```

预检查保存题库、代码与精排模型文件身份，生成96项Promptfoo开发测试，并将执行计划另存为本地快照。待 `/health` 返回 `models_warmed=true` 后，在另一个终端设置同一运行目录和前述Promptfoo环境，执行：

```powershell
npm run eval:threebody:retrieval -- --output (Join-Path $env:THREEBODY_RUN_DIR 'promptfoo.json')
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/retrieval_report.py --run-dir $env:THREEBODY_RUN_DIR
```

缺少完整已标注证据时Promptfoo会返回非零退出码并保留轨迹；这类失败不是接口错误。96次汇总中包含8次无答案题结构检查，不能把整体通过率作为问答准确率。报告单独核验执行顺序、零缓存命中、上下文预算、同模式候选及精排顺序一致性和原论文索引身份。正文及标签token均使用中文embedding tokenizer计数，实际生成计费用量需要在端到端评测中采集。

## 混合检索扩充开关的生成对照

[生成对照报告](../reports/threebody/GENERATION_COMPARISON.md)比较24道开发题的两份固定上下文。重新生成48个答案，不重新检索；来源标签、legacy模板、生成模型和来源裁判协议相同，配置执行顺序逐题交错。之前12个来源受控样例检查按代码、规则与上下文格式哈希一致性复用，不重复调用校准模型。

本轮自动语义通过为关闭扩充23/24、开启扩充24/24；同时要求命中全部已标注证据的严格通过为20/24、23/24。唯一自动语义分差在第6题，原文复核发现两组的章节归属判断存在宽严差异，因此不能据此认定扩充实际提升回答质量。第16题扩充补齐了被截断的原文解释，但两组均获自动满分，进一步说明评分对证据完整性的区分仍有限。

实际生成输入token分别为30,705和57,021，生成总token分别为33,115和59,401。生成耗时中位约1.52秒和1.63秒，不含本轮未执行的实时检索或裁判。每题每配置只采样一次，独立人工复核待完成；暂保留现有扩充默认配置，关闭扩充保留为低输入候选，保留题继续未运行。

预检查会核对检索实验、题库、索引与共享评分协议身份，复制48份固定上下文到新目录，并生成48项Promptfoo测试：

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/prepare_generation_comparison.py --retrieval-run eval/reports/threebody/raw/retrieval-study-20261105-02 --output-dir eval/reports/threebody/raw/generation-comparison-next
$env:THREEBODY_RUN_DIR = Join-Path $PWD 'eval/reports/threebody/raw/generation-comparison-next'
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' -m uvicorn eval.threebody.generation_comparison_server:app --host 127.0.0.1 --port 8004
```

待服务 `/health` 就绪后，在另一个终端设置相同目录与前述Promptfoo环境，执行：

```powershell
npm run eval:threebody:generation:compare -- --output (Join-Path $env:THREEBODY_RUN_DIR 'promptfoo.json')
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/generation_comparison_report.py --run-dir $env:THREEBODY_RUN_DIR
```

本次有1份裁判输出未通过校验，生成答案已先保存。HTTP错误正文被Promptfoo记录为断言失败，顶层errors=0不能解释为没有评分异常。`repair_generation_grade.py`仅重试出错答案的评分，先保留原异常记录及重试原始响应，不重新生成；随后用`eval:threebody:generation:replay`重放已保存结果，不新增模型调用。首次Promptfoo档案保留，报告核对恢复前后的答案、来源及生成用量完全一致。首次无效评分的用量未保存，因此评分token汇总存在缺口，不能声称为实际全部费用。

`generation_comparison_review.json`记录特定运行的初步原文复核，不覆盖原始自动分数。后续已完成下述逐项AI原文复核与配置冻结，不将其称为独立人工审核。

## 逐项原文复核与配置冻结

[原文复核与冻结报告](../reports/threebody/SOURCE_REVIEW_AND_FREEZE.md)核对了第6、16、21、22题的8份答案，验证25处证据引用、答案锚点和输入可见性。复核区分模型实际收到的片段与全书其他位置：后者仅用于核查事实和解释检索缺口，不充当生成依据。

第6题两组均有来源表达问题，扩充组另有省略比较成分后以推论充当直接引语的情况；第16题扩充补齐了关键原文，关闭扩充组包含已说明语境的推断；第21题两组均有替代证据并正确披露指定章节缺失，原参考还加入了问题未明确要求的制造者信息；第22题两组核心数字及呈现方式均有支持，扩充增加了具体译码操作句。结论与原始自动评分分别保存，没有追加证据位置或事后调分。

`source_review_v1.json`保存逐项核对记录，`review_protocol_v1.json`固定必要事实、当前依据、来源归属、引文忠实度与范围处理的独立记录口径。既有来源裁判仍作为辅助分数，自动满分不视为事实审核完成。

选定的评测配置固定在`frozen_profile_v1.json`：混合召回20、精排5、同节相邻块半径1、最多10块和2560正文token、带来源标签的上下文、legacy模板、deepseek-chat温度0.7及来源辅助裁判。选择依据是证据完整性和减少自行推断，未声称总体准确率已提高；生产默认行为未修改。配置记录题库、代码、模型及原始输出身份，并将关闭扩充保留为低输入候选。

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/review_and_freeze.py verify
```

冻结后校验若发现配置、依赖或题库变化会失败，不静默覆盖同一版本。下一阶段按冻结配置一次执行16道保留题，分开报告检索、自动语义分数及来源复核。查看保留结果后若修改配置或评分口径，该批题转为开发材料。独立人工审核尚未完成，不作为继续评测的必要依赖，不报告人工准确率。

## 冻结配置保留题结果

2026-11-06已完成16道保留题的单次评测，见[保留题报告](../reports/threebody/HOLDOUT.md)。严格规则及自动语义通过均为15/16；14道可回答题找齐标注证据13/14，两道无答案题均自动通过。原始数值未按复核结论重写，没有在查看保留输出后调参或修改标注。

未通过的tb-test-01找到了严寒及脱水情节，但未找回块119/120中较长恒纪元时浸泡复活、恢复生产的条件；回答仅给出前半问并正确披露缺少后半问依据。AI原文复核覆盖16份答案，另外记录了第9题将虫子总体描述缩窄为蝗虫的措辞问题，以及第15题参考答案漏记实际存在的咖啡馆名称。店名存在不代表街道门牌也已给出，原问题的无答案范围仍成立。

`holdout_source_review_v1.json`是按冻结review-protocol-v1进行的AI原文复核，不是独立人工准确率。完整原始片段、逐题开始标记、答案与全部评分尝试保存在`eval/reports/threebody/raw/holdout-20261106-01/`；单次执行台账位于`eval/reports/threebody/raw/holdout-v1-ledger.json`。台账阻止重新建立v1执行档案，服务也会拒绝重复生成已启动题目。

执行入口为`prepare_holdout.py`、`holdout_server.py`和`npm run eval:threebody:holdout`。该轮已经完成，不重复执行以选择更好结果。评分响应在校验前保存，最多允许一次格式／一致性失败后的评分重试，生成答案不重做；本轮16份评分均首次校验通过。离线重建报告不调用模型：

```powershell
& 'D:\MyProgramFiles\Miniforge\envs\RAG\python.exe' eval/threebody/holdout_report.py --run-dir eval/reports/threebody/raw/holdout-20261106-01
```

配置冻结档案保留创建时的状态，实际执行状态以保留题台账和报告为准。本轮已完成并结项。第一册与全集的规模对照未执行，不纳入本轮完成条件；若另行开展，相同问题的对照属于压力测试，不是新的独立测试。依据保留题调整配置或评分口径后，须另建测试集。
