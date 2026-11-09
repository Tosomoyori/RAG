"""Build the readable report from archived results without model or service calls."""

from pathlib import Path
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval/reports/threebody"


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def esc(value):
    return html.escape(str(value), quote=True)


def save(name, text):
    (OUT / name).parent.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(text.rstrip() + "\n", encoding="utf-8")


def svg_diagram(nodes, arrows, height, title, external=False):
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 {height}" role="img" aria-labelledby="title-{height}">',
             f'<title id="title-{height}">{esc(title)}</title>',
             f'<defs><marker id="arrow-{height}" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#71849b"/></marker></defs>',
             '<rect width="1100" height="100%" rx="18" fill="#f3f6fa"/>']
    for path in arrows:
        parts.append(f'<path d="{path}" fill="none" stroke="#71849b" stroke-width="2" marker-end="url(#arrow-{height})"/>')
    for x, y, w, h, label, lines, anchor, color in nodes:
        href = ("../FINAL_EVALUATION.html" if external else "") + "#" + anchor
        parts.extend([f'<a href="{href}" aria-label="{esc(label)}：点击查看详情">',
                      f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="white" stroke="{color}" stroke-width="2"/>',
                      f'<text x="{x+20}" y="{y+30}" font-family="Microsoft YaHei, sans-serif" font-size="19" font-weight="700" fill="{color}">{esc(label)} ↗</text>'])
        for i, line in enumerate(lines):
            parts.append(f'<text x="{x+20}" y="{y+56+i*25}" font-family="Microsoft YaHei, sans-serif" font-size="16" fill="#334155">{esc(line)}</text>')
        parts.append('</a>')
    parts.append('</svg>')
    return "\n".join(parts)


FLOW_NODES = [
    (20, 20, 1060, 82, '第一册《三体》：36章 → 865个文本块', ['只评第一册；EPUB文件内的另两册未做效果评测。'], 'scope', '#203d65'),
    (20, 142, 510, 82, '24道开发题：用于比较方案', ['22道有答案 + 2道无答案；点击展开全部题目。'], 'development', '#1d6187'),
    (570, 142, 510, 82, '16道保留题：用于最后检验', ['14道有答案 + 2道无答案；开发时不用于选方案。'], 'holdout', '#276956'),
    (20, 266, 510, 100, '实验一：4组检索条件', ['向量 / 混合 × 不扩充 / 补相邻原文', '每组都是：先取20块 → 精排留5块。'], 'retrieval', '#1d6187'),
    (570, 266, 510, 82, '12个裁判检查样例（辅助）', ['检查评分是否合理，不计入40道正式题。'], 'controls', '#775524'),
    (20, 408, 510, 100, '实验二：2组输入，各生成24份回答', ['同一DeepSeek模型：混合不扩充 vs 混合扩充', '正确性、依据、行为、语言分别评分。'], 'generation', '#1d6187'),
    (570, 408, 510, 100, '保留题等待配置固定', ['开发阶段不运行保留题；不用于选择方案。', '题目分组与原始内容见附录。'], 'term-splits', '#276956'),
    (20, 552, 510, 82, '选定并固定配置', ['候选20、精排5、扩充最多10块 / 2560 token。'], 'parameters', '#203d65'),
    (570, 552, 510, 82, '固定方案后运行16道保留题', ['严格通过15/16；每题生成一次，结果后未再调参。'], 'holdout-results', '#276956'),
    (20, 676, 1060, 82, '评测完成：结论与使用边界', ['证据更完整，输入更多；未证明总体准确率提升。'], 'conclusion', '#203d65'),
]
FLOW_ARROWS = ['M275 102 V142', 'M825 102 V142', 'M275 224 V266', 'M275 366 V408',
               'M275 508 V552', 'M825 224 V245 H1090 V386 H825 V408',
               'M570 307 H550 V458 H530', 'M530 593 H570', 'M825 508 V552', 'M825 634 V676']
EXAMPLE_NODES = [
    (20, 20, 1060, 82, '开发题16：为什么让“审判日”号白天通过？', ['同一道问题、同一混合检索、同样先取20块并精排留5块。'], 'tb-dev-16', '#203d65'),
    (20, 142, 510, 158, 'hybrid-n0：不扩充，输入5块', ['已取到块729，原文在半句处截断：', '“夜里船上的人睡觉啊，都是躺着的，', '五十厘米的空当……”', '回答有“站立、走动”等推断。'], 'example', '#775524'),
    (570, 142, 510, 158, 'hybrid-n1：补相邻原文，输入10块', ['新增块730，接上原文：', '“五十厘米的空当太大了，白天他们', '就是坐着或蹲着，也够了。”', '回答可以直接依据完整解释。'], 'example', '#276956'),
    (20, 342, 1060, 82, '这里的“扩充”是补原书相邻段落；“语义评分”是回答之后的评分', ['两组本题自动评分都满分，因此还需要核对具体原文，不能只看通过率。'], 'term-expansion', '#203d65'),
]
EXAMPLE_ARROWS = ['M275 102 V142', 'M825 102 V142', 'M275 300 V342', 'M825 300 V342']


def inline(text):
    text = esc(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)


def markdown_html(text):
    """Render the small, explicit Markdown subset used by this report."""
    lines = text.splitlines()
    parts = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('<a id='):
            parts.append(line)
        elif line.startswith('!['):
            name = re.search(r'\(([^)]+)\)', line).group(1)
            if name.endswith('evaluation-flow.svg'):
                parts.append(svg_diagram(FLOW_NODES, FLOW_ARROWS, 778, '评测流程'))
            else:
                parts.append(svg_diagram(EXAMPLE_NODES, EXAMPLE_ARROWS, 444, '扩充实例'))
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', x) for x in cells):
                    tag = 'th' if not rows else 'td'
                    rows.append('<tr>' + ''.join(f'<{tag}>{inline(x)}</{tag}>' for x in cells) + '</tr>')
                i += 1
            parts.append('<div class="table-wrap"><table>' + ''.join(rows) + '</table></div>')
            continue
        elif line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            parts.append(f'<h{level}>{inline(line[level:].strip())}</h{level}>')
        elif line.startswith('- '):
            items = []
            while i < len(lines) and lines[i].strip().startswith('- '):
                items.append('<li>' + inline(lines[i].strip()[2:]) + '</li>')
                i += 1
            parts.append('<ul>' + ''.join(items) + '</ul>')
            continue
        elif line.startswith('> '):
            parts.append('<blockquote>' + inline(line[2:]) + '</blockquote>')
        else:
            parts.append('<p>' + inline(line) + '</p>')
        i += 1
    return '\n'.join(parts)


def build():
    development = read('eval/corpora/threebody/question-bank-v1/development.json')
    holdout = read('eval/corpora/threebody/question-bank-v1/holdout.json')
    controls = read('eval/threebody/calibration_sources.json')
    profile = read('eval/threebody/frozen_profile_v1.json')
    assert (len(development), len(holdout), len(controls)) == (24, 16, 12)
    # Verify frozen inputs before rendering; no evaluation code is imported.
    for filename, expected in profile['dataset_sha256'].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == expected, filename
    retrieval = read('eval/reports/threebody/raw/retrieval-study-20261105-02/summary.json')
    generation = read('eval/reports/threebody/raw/generation-comparison-20261105-01/summary.json')
    final = read('eval/reports/threebody/raw/holdout-20261106-01/summary.json')
    rrows = []
    names = {'vector-n0': '向量，不扩充', 'vector-n1': '向量，补相邻原文',
             'hybrid-n0': '混合，不扩充', 'hybrid-n1': '混合，补相邻原文'}
    for r in retrieval['summaries']:
        rrows.append(f"| {names[r['variant']]}（`{r['variant']}`） | {r['candidate_all']}/22 | {r['seed_all']}/22 | {r['context_all']}/22 | {r['context_group_coverage']:.1%} | {r['seed_mrr']:.3f} | {r['mean_body_tokens']:,.0f} | {r['median_ms']:.0f} ms |")
    g0, g1 = generation['summaries']
    grows = []
    for label, key, denom in [('自动语义通过', 'semantic_passes', '/24'),
                              ('严格通过', 'strict_passes', '/24'),
                              ('找齐标注证据', 'all_annotated_evidence', '/22'),
                              ('生成输入 token', 'generation_input_tokens', ''),
                              ('生成输出 token', 'generation_output_tokens', ''),
                              ('生成总 token', 'generation_total_tokens', '')]:
        grows.append(f"| {label} | {g0[key]:,}{denom} | {g1[key]:,}{denom} |")
    grows.append(f"| 生成中位耗时 | {g0['median_generation_ms']/1000:.2f} s | {g1['median_generation_ms']/1000:.2f} s |")
    report = '''# 《三体》第一册 RAG 评测报告

**已完成 · 2026-11-06 · Promptfoo 编排**

本轮回答两个问题：**怎样更完整地找到原文证据？补上相邻原文后，回答有什么变化、输入增加多少？** 最终采用“混合检索 + 相邻原文扩充”，固定配置后16道保留题严格通过15题。这个数字是本题库的自动评测结果，尚未经独立人工审核。

[打开可点击图文版](FINAL_EVALUATION.html) · [全部40道题及参考答案](QUESTIONS.md) · [12个裁判检查样例](JUDGE_CONTROLS.md)

<a id="scope"></a>
## 1. 评测范围与流程

正式语料是第一册《三体》：36章、187,784字符、865个文本块。EPUB文件实际包含三册，本轮只评第一册。正式题共40道：24道开发题用于比较方案；16道保留题在方案固定后检验，不再用于调参。早期8道试运行题包含在24题内；12个裁判检查样例另计。

![评测流程；点击图文版中的节点可跳转到题目、实验和术语](assets/evaluation-flow.svg)

图中每个方框均有详情链接。**在HTML图文版中点击方框即可跳转**；Markdown内嵌图片的节点点击取决于阅读器，可使用本文的文字链接。

<a id="parameters"></a>
## 2. 具体比较了什么、改了什么

| 实验 | 比较方法 | 实际改变 | 保持相同 |
|---|---|---|---|
| 一：检索对照 | 向量不扩充、向量扩充、混合不扩充、混合扩充，共4组 | 检索方式；是否补同节相邻原文 | 24题、语料、切块、向量模型、精排模型；候选20块、精排留5块 |
| 二：生成对照 | `hybrid-n0` vs `hybrid-n1`，各24份回答 | 给生成模型的原文片段：5个精排块 vs 补邻居后的最多10块 | 问题、模型、提示词、温度、来源标签、评分规则；直接使用实验一保存的片段 |
| 三：保留检验 | 固定最终配置后回答16题 | 换成未用于选方案的16道题 | 只用混合检索并扩充；不再比较或调整配置 |

**表头说明：**“比较方法”是同批问题分别运行的方案；“实际改变”是实验变量；“保持相同”是控制条件。第三项检验选定方案，不是新增一组调参对照。

**向量检索**按意思相近查找；**混合检索**把向量结果与BM25关键词结果等权融合后取候选。`n0`表示不补邻居；`n1`表示允许补精排块前后各一块原文，限同一节，受总量上限约束。扩充读取原书文字。

| 参数或设置 | 本轮取值 | 是否比较过不同值 |
|---|---|---|
| 检索候选数 `top_k` | 20块 | 否 |
| 精排保留数 `top_n` | 5块 | 否 |
| 相邻块半径 `neighbors` | 对比0与1；最终为1 | 是 |
| 最终上下文上限 | 10块、正文合计2560 token | 否 |
| 切块大小 / 重叠 | 256 / 40 token | 否 |
| 向量模型 / 精排模型 | text2vec-base-chinese / mmarco-mMiniLMv2-L12-H384-v1 | 否 |
| 生成模型 / 温度 / 模板 | deepseek-chat / 0.7 / legacy | 否 |
| 自动裁判模型 / 温度 | deepseek-chat / 0 | 否 |

**表头说明：**“本轮取值”是运行时采用的设置，“是否比较过不同值”表示有没有通过对照验证该数值。**本轮没有寻找最优top_k或top_n，也没有比较不同生成模型或生成采样top_k。** 上表top_k属于检索候选数，top_n属于精排，都在生成之前。来源标签格式用于实验，未替换普通问答接口的默认格式。

<a id="retrieval"></a>
## 3. 实验一：原文证据有没有找全

24道开发题中22道有答案；下面证据指标只统计这22道。四组共96次检索观测。

| 检索方案 | 候选20块找齐 | 精排5块找齐 | 最终输入找齐 | 必要事实覆盖率 | 首条证据排名分MRR | 平均正文token | 检索中位耗时 |
|---|---:|---:|---:|---:|---:|---:|---:|
''' + '\n'.join(rrows) + '''

**表头说明：**

- **检索方案：**向量或混合检索，以及扩充开关。括号内是原始记录的配置名。
- **候选20块找齐 / 精排5块找齐 / 最终输入找齐：**分别在三个阶段数有多少题找到了全部已标注必要事实的证据。每个事实有多个可接受位置时，找到其中一个即可。比如18/22表示22道有答案题中，18题的标注证据齐全。
- **必要事实覆盖率：**每题“找到的必要事实数 ÷ 该题必要事实总数”，再对22题取平均。若题目需两个事实、只找到一个，该题是50%；它不算“找齐”。此指标不是检索了全书多少文字，也不直接等于回答正确率。
- **首条证据排名分MRR：**精排5块中，第一条标注相关证据排第1得1分、排第2得1/2、排第3得1/3，没找到得0；对22题取平均。越大表示第一条证据越靠前，不代表多项证据都齐全。
- **平均正文token：**24题最终交给模型的原文片段长度均值，用向量模型的分词器计算，不含来源标签和提示词，不是API计费输入量。
- **检索中位耗时：**24题检索、精排及扩充耗时的中间值，不含答案生成和评分。

**结果：**关闭扩充时，混合检索比向量检索多找齐2题（18 vs 16）；在混合检索基础上补相邻原文，又多找齐3题（21 vs 18）。代价是正文输入接近翻倍。模型预热、逐次清理应用检索缓存并轮换顺序；每题每条件只测一次，耗时不作显著性结论。扩充可读取候选20块之外的邻居。

<a id="example"></a>
## 4. 一个真实例子：扩充到底补了什么

[开发题16](QUESTIONS.md#tb-dev-16)要求解释：为什么让“审判日”号白天经过，且必须联系纳米丝最小间距。

![开发题16：不扩充与补相邻原文的实际差异](assets/expansion-example.svg)

块729有“拉丝的间距最小就是五十厘米，再小材料不够了”，但后面的解释截断在“夜里船上的人睡觉啊，都是躺着的，五十厘米的空当”。新增块730接上：“五十厘米的空当太大了，白天他们就是坐着或蹲着，也够了。”

不扩充时实际输入块为734、733、742、729、728；扩充后再加735、732、741、743、730。两组本题自动评分都满分，但扩充后有直接的完整原文支持；不扩充回答中的“站立、走动”带有推断。**补证据的效果，不能只用自动满分来判断。**

<a id="generation"></a>
## 5. 实验二：同一个模型，换输入片段

只比较“混合不扩充”和“混合扩充”。各使用实验一保存的片段生成24份答案，合计48份，不重新检索。没有“语义扩充”步骤；**语义评分是回答生成之后，按意思检查答案。**

| 指标 | 混合不扩充 hybrid-n0 | 混合扩充 hybrid-n1 |
|---|---:|---:|
''' + '\n'.join(grows) + '''

**表头与指标说明：**两列分别是相同24题、相同生成条件下的两套输入。自动语义通过要求正确性、依据、行为、语言四项均为2分，且没有被裁判标记的来源错误；严格通过还要求找齐全部标注证据，无答案题不要求证据块。“找齐标注证据”只统计22道有答案题。输入、输出、总token是24份生成的API用量合计，总量为输入加输出，不含裁判；生成中位耗时只含生成，不含检索与评分。

**结果：**扩充后输入token增加85.7%，生成总token增加79.4%，严格通过从20题变成23题。自动语义分仅第6题有差异，但原文复核发现裁判存在来源归属判断不一致，因此不据此认定总体回答准确率提高。第16题的完整原文补充则可直接核对。

有1次裁判输出无效，只重评已保存答案，没有再生成；异常前记录保留。该次无效评分用量缺失，因此不汇总全部费用。来源标签另有补充实验，但评分规则也发生变化，不作为本表的单变量结论，见[来源实验](SOURCE_ATTRIBUTION.md)。

<a id="scoring"></a>
### 四项评分分别查什么

| 项目 | 2分 | 1分 | 0分 |
|---|---|---|---|
| 正确性 correctness | 答对参考答案所需事实，符合纠错或拒答要求 | 只答对一部分，或遗漏必要事实 | 核心错误，或没有回答该答的事实 |
| 依据 grounding | 每个事实断言都有当前输入片段支持 | 核心有依据，但附加细节、因果或来源支持不足 | 核心解释无依据或与原文冲突 |
| 行为 behavior | 有依据就回答；缺什么明确说；错误前提明确纠正 | 笼统说不确定，或部分作答混入猜测 | 编造缺失信息，或接受错误前提 |
| 语言 language | 主体按要求用中文，术语与引文可保留原语言 | 中外文混杂，但中文仍为主 | 主体没有用要求的语言 |

**表头说明：**“项目”是互相独立的检查维度，后三列是0、1、2分的判定含义。语言项检查语言选择，不评文采。引用可省略，但一旦标明章节或块号就必须正确；来源标错按[来源规则](../../threebody/source-grading-rules.txt)限制相关得分。例如原书有答案、检索却漏了一半时，诚实说明缺失可以让依据和行为得2分，正确性仍只有1分。原始标准见[评分规则](../../promptfoo/semantic-rubric.txt)。

<a id="holdout-results"></a>
## 6. 最后检验：16道保留题

固定“混合检索 + 相邻原文扩充”后，每题生成一次；查看答案后没有再改配置、改题或补标。

| 检查项 | 结果 |
|---|---:|
''' + f'''| 回答及有效评分完成 | {final['complete_grades']}/16 |
| 自动语义通过 | {final['automatic_semantic_passes']}/16（93.75%） |
| 严格通过 | {final['strict_passes']}/16（93.75%） |
| 有答案题找齐标注证据 | {final['all_annotated_evidence']}/14 |
| 无答案题恰当拒答并语义通过 | {final['abstention_semantic_passes']}/2 |
| 无效评分次数 | {final['invalid_grading_attempts']} |
| 生成总token / 裁判总token | {final['generation_tokens']:,} / {final['all_grading_attempt_tokens']:,} |
''' + '''
**表头说明：**“检查项”列出完成数量、答案质量、证据完整性与用量，“结果”为对应计数或合计。自动语义与严格通过沿用上节定义；证据项分母为14道有答案题，拒答项分母为2道无答案题，两类分开计算。生成token用于回答，裁判token用于评分，分别列出。

未通过的是[保留题01](QUESTIONS.md#tb-test-01)：问脱水原因和恢复生产条件。检索找到了严寒和脱水，却漏掉“当较长的恒纪元到来时，再集体浸泡复活，生产和建设”的块119/120。回答只完成前半问，并说明当前片段不足以回答后半问。**原书有答案，是检索没找齐；如实说明不足仍然会失去正确性分。** [16题逐项结果及复核](HOLDOUT.md)保留全部成绩与问题说明。

<a id="conclusion"></a>
## 7. 结论：本轮给出的配置建议

- **证据完整优先：**在本题库中采用混合检索、开启同节相邻原文扩充。相对混合不扩充，开发题完整证据由18/22增至21/22。
- **输入量优先：**保留混合不扩充作为较低输入的候选。两组生成输入分别为30,705与57,021 token；不能只看通过数而忽略输入增长。
- **参数结论的边界：**20个候选、精排5块是本轮采用值，未证明是最优值；没有不同top_k、top_n、切块大小或生成模型的比较结果。

16题保留检验严格通过15题，不能外推为全书任意问题准确率93.75%。题目、参考答案与原文复核由AI完成，独立人工审核未完成；同模型系列生成和评分、每条件单次采样及小样本都会限制结论。已记录第9题附加表述范围偏窄、第15题参考漏记店名等问题，未事后改分。评测已结束。

<a id="glossary"></a>
## 8. 术语与证据入口

<a id="term-expansion"></a>
**相邻原文扩充：**找到块729后，允许补同一节的728与730；有重复则去重，并受10块、2560正文token上限约束。没有改写问题或生成新内容。

<a id="term-semantic"></a>
**语义评分：**模型读问题、参考答案、当前片段和当前回答，按意思评分。发生在生成之后；不是第二次扩充资料，也不是Promptfoo必须默认执行的固定步骤，而是本项目配置的评分检查。

<a id="term-retrieval"></a>
**召回 → 精排 → 上下文：**先从865块中取20个候选，再按问题与片段的相关性重新排序并留5块；可补邻居，得到最终给生成模型阅读的资料。BM25按词匹配，向量按语义相似；混合使用RRF合并两套排名。[具体实现与实验](RETRIEVAL_COMPARISON.md)。

<a id="term-splits"></a>
**开发题 / 保留题：**开发题可用于比较和选方案；保留题在方案固定后才运行，只报告最终效果。本轮24+16合计40题；最初8题属于开发组子集。12个裁判检查样例用已知好坏回答检查评分器，不计入40题。

题目全文与标准：[40题及参考答案](QUESTIONS.md)；[12个裁判检查样例](JUDGE_CONTROLS.md)。实验档案：[检索](RETRIEVAL_COMPARISON.md)、[生成](GENERATION_COMPARISON.md)、[原文复核](SOURCE_REVIEW_AND_FREEZE.md)、[保留结果](HOLDOUT.md)、[固定配置](../../threebody/frozen_profile_v1.json)、[方法与命令](../../threebody/README.md)。完整电子书、索引及原始输出保存在本地忽略目录，不随报告提交。
'''
    # Keep the previous report as evidence rather than silently deleting its detail.
    old = OUT / 'FINAL_EVALUATION.md'
    archive = OUT / 'FINAL_EVALUATION_ARCHIVE.md'
    if old.exists() and not archive.exists():
        archive.write_bytes(old.read_bytes())
    save('FINAL_EVALUATION.md', report)
    save('assets/evaluation-flow.svg', svg_diagram(FLOW_NODES, FLOW_ARROWS, 778, '评测流程：各节点可打开题目或术语', True))
    save('assets/expansion-example.svg', svg_diagram(EXAMPLE_NODES, EXAMPLE_ARROWS, 444, '开发题16的相邻原文扩充示例', True))

    qmd = ['# 《三体》第一册：全部40道评测题', '',
           '[返回最终报告](FINAL_EVALUATION.md) · [可点击图文版](FINAL_EVALUATION.html)', '',
           '题目与参考答案逐字来自固定题库，未因结果改写。24道开发题用于比较方案，16道保留题用于最后检验；最初8道试运行题已包含在开发题中。各题另列预期行为和标注证据块，通用四项评分见[最终报告](FINAL_EVALUATION.md#scoring)。标注由AI完成，独立人工审核未完成。', '']
    qhtml = []
    behavior_names = {'answer': '依据片段回答', 'abstain': '说明缺失，不猜测',
                      'correct_premise': '纠正错误前提后回答', 'partial': '回答有依据部分并指出缺失'}
    type_names = {'detail': '细节', 'paraphrase': '换一种说法', 'distinction': '区分易混内容',
                  'multi_evidence': '综合多处证据', 'multi_fact': '多项事实', 'unanswerable': '指定范围无答案',
                  'false_premise': '错误前提'}
    for split, label, questions, source in [('development', '24道开发题', development, 'development.json'),
                                            ('holdout', '16道保留题', holdout, 'holdout.json')]:
        qmd += [f'<a id="{split}"></a>', f'## {label}', '', f'[固定原始题库](../../corpora/threebody/question-bank-v1/{source})', '']
        qhtml += [f'<section id="{split}"><h2>{label}</h2><p>原始题库：<a href="../../corpora/threebody/question-bank-v1/{source}">{source}</a> · <a href="#top">返回报告开头</a></p>']
        for q in questions:
            evidence = '；'.join(' / '.join('chunk-' + str(n) for n in e['acceptable_indexes']) for e in q.get('evidence', [])) or '不适用（无答案题）'
            expected = behavior_names.get(q['behavior'], q['behavior'])
            kind = type_names.get(q['type'], q['type'])
            note = ''
            if q['id'] == 'tb-test-15':
                note = '复核记录：原参考漏记了实际存在的咖啡馆名称；本题询问的街道及门牌号仍缺失。保留原参考与原分数，未事后修改。'
            qmd += [f'<a id="{q["id"]}"></a>', f'### {q["id"]} · {kind}', '', q['question'], '',
                    f'**参考答案：**{q["reference"]}', '', f'**预期行为：**{expected}。', '',
                    f'**标注证据：**{evidence}。分号分隔不同必要事实，同一事实的多个可接受块用斜线分隔。', '']
            if note:
                qmd += [note, '']
            qhtml += [f'<article class="question" id="{q["id"]}"><p class="qid">{q["id"]} · {esc(kind)}</p><h3>{esc(q["question"])}</h3>',
                      f'<details><summary>参考答案、预期行为与标注位置</summary><p><strong>参考答案：</strong>{esc(q["reference"])}</p>',
                      f'<p><strong>预期行为：</strong>{esc(expected)}。</p><p><strong>标注证据：</strong>{esc(evidence)}。分号分隔不同必要事实；斜线表示同一事实的替代位置。</p>',
                      f'<p>{esc(note)}</p>' if note else '', '</details></article>']
        qhtml += ['</section>']
    save('QUESTIONS.md', '\n'.join(qmd))

    cmd = ['# 12个裁判检查样例', '', '[返回最终报告](FINAL_EVALUATION.md)', '',
           '这些是固定“问题＋给定资料＋待评分回答”的受控样例，用于检查裁判是否按规则打分，不是新增的12道小说检索题，不计入40题效果。前8个来自初始检查，后4个增加来源归属检查。给定资料为检查输入，不应一律视为小说逐字引文。', '',
           '[原始完整样例](../../threebody/calibration_sources.json)。预期分数用“或”表示允许范围；未列维度表示该样例未对该维度限定。', '']
    chtml = ['<section id="controls"><h2>12个裁判检查样例（辅助）</h2><p>固定问题、资料和好坏回答，用来检查评分器；不计入40道正式题。给定资料是检查输入，不一律代表小说逐字引文。<a href="JUDGE_CONTROLS.md">打开独立样例文档</a>。</p>']
    for c in controls:
        score = '；'.join({'correctness': '正确性', 'grounding': '依据', 'behavior': '行为', 'language': '语言'}[k] + '=' + '或'.join(str(x) for x in v) for k, v in c['expected_scores'].items())
        source_rule = '须识别来源错误' if c.get('require_source_errors') else ('须无来源错误' if c.get('require_no_source_errors') else '未另设来源错误断言')
        cmd += [f'## {c["id"]} · {c["kind"]}', '', f'**问题：**{c["question"]}', '', '**给定资料：**', '',
                c['context'], '', f'**待评分回答：**{c["answer"]}', '', f'**参考答案：**{c["reference_answer"]}', '', f'**预期分数：**{score}；{source_rule}。', '']
        chtml += [f'<article class="question" id="{c["id"]}"><p class="qid">{c["id"]} · {esc(c["kind"])}</p><h3>{esc(c["question"])}</h3>',
                  '<details><summary>给定资料、待评分回答及预期分数</summary>',
                  f'<p><strong>给定资料：</strong></p><pre>{esc(c["context"])}</pre>',
                  f'<p><strong>待评分回答：</strong>{esc(c["answer"])}</p><p><strong>参考答案：</strong>{esc(c["reference_answer"])}</p>',
                  f'<p><strong>预期分数：</strong>{esc(score)}；{source_rule}。未列维度未限定分数。</p></details></article>']
    chtml += ['</section>']
    save('JUDGE_CONTROLS.md', '\n'.join(cmd))
    body = markdown_html(report)
    # Prefer in-page destinations in the portable HTML; original data links stay external.
    body = re.sub(r'href="QUESTIONS.md#([^"]+)"', r'href="#\1"', body)
    body = body.replace('href="QUESTIONS.md"', 'href="#development"').replace('href="JUDGE_CONTROLS.md"', 'href="#controls"')
    body = body.replace('href="FINAL_EVALUATION.html"', 'href="#top"')
    css = '''
    :root{color-scheme:light;--ink:#20344d;--muted:#526278;--line:#dce4ed}
    *{box-sizing:border-box}html{scroll-padding-top:80px}
    body{margin:0;background:#f3f6fa;color:var(--ink);font:16px/1.8 "Microsoft YaHei",system-ui,sans-serif}
    header{position:sticky;top:0;z-index:2;background:#142e4b;color:white;padding:12px 24px}
    nav{max-width:1140px;margin:auto;display:flex;flex-wrap:wrap;gap:10px 24px}nav a{color:#e4efff;font-size:14px}
    main{max-width:1200px;margin:30px auto;padding:36px 40px;background:white;border:1px solid var(--line);border-radius:18px}
    h1{font-size:32px;margin:0 0 20px;line-height:1.4}h2{font-size:24px;margin:44px 0 16px;padding-bottom:10px;border-bottom:1px solid var(--line)}
    h3{font-size:18px;line-height:1.7}p{margin:14px 0}a{color:#17648d;text-underline-offset:4px}a:hover{color:#a55c12}
    code{font:14px Consolas,monospace;background:#edf2f7;padding:2px 5px;border-radius:4px}strong{color:#153d64}
    svg{width:100%;height:auto;display:block;margin:24px 0}svg a:hover rect,svg a:focus rect{fill:#e8f2fa;stroke-width:3}
    .table-wrap{overflow-x:auto;margin:18px 0}table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.65}
    th,td{text-align:left;vertical-align:top;padding:12px 13px;border:1px solid var(--line)}th{background:#eaf0f7;color:#193c61}tr:nth-child(even){background:#f8fafc}
    blockquote{border-left:4px solid #4387aa;background:#f2f7fb;margin:16px 0;padding:12px 20px}
    li{margin:8px 0}.question{border:1px solid var(--line);border-radius:10px;padding:18px 22px;margin:16px 0;scroll-margin-top:80px}
    .qid{color:#17648d;font-size:13px;font-weight:700;margin:0}.question h3{margin:6px 0 12px}
    summary{cursor:pointer;color:#17648d;font-size:14px}details[open]{margin-top:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 inherit;background:#f3f6fa;padding:16px}
    .appendix{border-top:4px solid #203d65;margin-top:48px;padding-top:16px}.back{position:fixed;right:18px;bottom:18px;background:#203d65;color:white;padding:8px 16px;border-radius:20px;text-decoration:none}
    @media(max-width:700px){main{margin:10px;padding:22px 16px}h1{font-size:25px}h2{font-size:21px}header{padding:10px 16px}th,td{padding:8px}nav{gap:5px 14px}}
    @media print{header,.back{display:none}main{max-width:none;margin:0;padding:0;border:0}h2{break-after:avoid}.question,svg,tr{break-inside:avoid}details{display:block}}
    '''
    save('FINAL_EVALUATION.html', '<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>《三体》第一册 RAG 评测报告</title><style>' + css + '</style></head><body><header><nav aria-label="报告导航"><a href="#top">总览</a><a href="#parameters">比较与参数</a><a href="#retrieval">检索结果</a><a href="#generation">生成结果</a><a href="#holdout-results">最终结果</a><a href="#development">24道开发题</a><a href="#holdout">16道保留题</a><a href="#glossary">术语</a></nav></header><main id="top">' + body + '<div class="appendix"><h2>附录：全部题目与参考标准</h2><p>所有题目均完整显示。点击每题下方展开参考答案、行为要求与标注位置。题库及标准保持原样。</p>' + ''.join(qhtml) + ''.join(chtml) + '</div></main><a class="back" href="#top">返回顶部 ↑</a></body></html>')
    validate()


def validate():
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = []
            self.links = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if 'id' in attrs:
                self.ids.append(attrs['id'])
            if 'href' in attrs:
                self.links.append(attrs['href'])

    parser = Links()
    parser.feed((OUT / 'FINAL_EVALUATION.html').read_text(encoding='utf-8'))
    # Embedded SVG titles/markers use distinct prefixes to keep DOM IDs unique.
    assert len(parser.ids) == len(set(parser.ids)), 'Duplicate HTML IDs'
    for href in parser.links:
        path, _, anchor = href.partition('#')
        if not path:
            assert anchor in parser.ids, href
        else:
            assert (OUT / path).exists(), href
    for name in ['QUESTIONS.md', 'JUDGE_CONTROLS.md', 'FINAL_EVALUATION.md']:
        text = (OUT / name).read_text(encoding='utf-8')
        for href in re.findall(r'\]\(([^)]+)\)', text):
            path, _, anchor = href.partition('#')
            target = OUT / path
            assert target.exists(), (name, href)
            if anchor and path.endswith('.md'):
                assert f'id="{anchor}"' in target.read_text(encoding='utf-8'), (name, href)
    for name in ['evaluation-flow.svg', 'expansion-example.svg']:
        tree = ET.parse(OUT / 'assets' / name)
        for a in tree.findall('.//{http://www.w3.org/2000/svg}a'):
            assert a.attrib['href'].split('#')[1] in parser.ids
    assert len([x for x in parser.ids if re.fullmatch(r'tb-dev-\d+', x)]) == 24
    assert len([x for x in parser.ids if re.fullmatch(r'tb-test-\d+', x)]) == 16
    assert len([x for x in parser.ids if re.fullmatch(r'cal-\d+', x)]) == 12
    print('Report built: 24 development + 16 holdout questions; 12 separate judge controls. Links and frozen question hashes verified. No model calls.')


if __name__ == '__main__':
    build()
