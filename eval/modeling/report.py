"""Render saved modeling-paper experiments without retrieval or model calls."""
from collections import Counter
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import statistics
import sys
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from eval.modeling.study import RUN, REPORT, LOCAL, HERE, DOCS, VARIANTS, load, dump, sha


def e(x):
    return html.escape(str(x),quote=True)


def table(headers, rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+e(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def mdtable(headers,rows):
    def cell(x):return str(x).replace('|','\\|').replace('\n','<br>')
    return '\n'.join(['| '+' | '.join(map(cell,headers))+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(cell,row))+' |' for row in rows])


def usage(x):
    return x.get('total_tokens',0)


def diagram():
    nodes=[(20,20,1020,80,'三篇私有数模论文 → 71页正式正文','scope'),
           (20,140,480,95,'24道题：每篇8题，点击查看全文','questions'),
           (560,140,480,95,'原文位置标注：跨切块共用标准','metrics'),
           (20,280,225,100,'候选10 / 20 / 40','candidate'),
           (285,280,225,100,'精排保留3 / 5 / 8','retain'),
           (550,280,225,100,'精排开 / 关','rerank'),
           (815,280,225,100,'切块128 / 256 / 384','chunk'),
           (20,425,1020,80,'共8组配置：192次检索与回答；另24次无文档对照','closed-book'),
           (20,550,1020,80,'Promptfoo自动评分 → 四项对照结果、输入代价与配置建议','conclusion')]
    parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1060 655" role="img" aria-labelledby="flow-title"><title id="flow-title">四项RAG实验流程，点击节点查看题目和结果</title><defs><marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#60788d"/></marker></defs><rect width="1060" height="655" rx="18" fill="#f0f5fa"/>']
    for path in ['M260 100 V140','M800 100 V140','M260 235 V256 H132 V280','M260 256 H397 V280','M800 235 V256 H662 V280','M800 256 H927 V280',
                 'M132 380 V402 H530 V425','M397 380 V402','M662 380 V402 H530','M927 380 V402 H662','M530 505 V550']:
        parts.append(f'<path d="{path}" fill="none" stroke="#60788d" stroke-width="2" marker-end="url(#flow-arrow)"/>')
    for x,y,w,h,label,target in nodes:
        size=15 if w<250 else 20
        parts.append(f'<a href="#{target}" aria-label="{e(label)}，点击查看详情"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="white" stroke="#245578" stroke-width="2"/><text x="{x+15}" y="{y+44}" font-family="Microsoft YaHei,sans-serif" font-size="{size}" fill="#245578">{e(label)} ↗</text></a>')
    return '\n'.join(parts)+'</svg>'


def build():
    manifest=load(RUN/'manifest.json')
    cases=load(RUN/'cases.json')
    assert sha(RUN/'cases.json')==manifest['dataset_sha256']
    for f,h in manifest['code_sha256'].items():
        assert sha(ROOT/f)==h,f
    for f,h in manifest['original_index_sha256'].items():
        assert sha(ROOT/f)==h,f
    assert {p.relative_to(ROOT).as_posix() for p in (ROOT/'chroma_db').rglob('*') if p.is_file()}==set(manifest['original_index_sha256'])
    records={(x['case_id'],x['variant']):x for p in (RUN/'answers').glob('*.json') if (x:=load(p))}
    assert len(records)==216, f'Expected 216 saved answers, found {len(records)}'
    retrieval={(x['case_id'],x['variant']):x for p in (RUN/'retrieval').glob('*.json') if (x:=load(p))}
    assert len(retrieval)==192
    answerable=[c for c in cases if c['evidence']]
    summaries={}
    for v in VARIANTS:
        name=v['id']
        rr=[retrieval[c['id'],name] for c in cases]
        aa=[records[c['id'],name] for c in cases]
        ar=[retrieval[c['id'],name] for c in answerable]
        valid=[x for x in aa if x['status']=='complete']
        summaries[name]=dict(config=v,observations=len(rr),valid_grades=len(valid),
            candidate_complete=sum(x['candidate']['complete'] for x in ar),
            evidence_complete=sum(x['context']['complete'] for x in ar),coverage=statistics.mean(x['context']['coverage'] for x in ar),
            mrr=statistics.mean(x['context']['mrr'] for x in ar),
            semantic=sum(x.get('semantic_pass',False) and x.get('generation_finish_reason')=='stop' for x in aa),
            strict=sum(x.get('strict_pass',False) and x.get('generation_finish_reason')=='stop' for x in aa),
            correctness=sum(x.get('grade',{}).get('correctness')==2 and x.get('generation_finish_reason')=='stop' for x in aa),
            body_tokens=statistics.mean(x['body_tokens'] for x in rr),retrieval_ms=statistics.median(x['retrieval_ms'] for x in rr),
            generation_ms=statistics.median(x['generation_ms'] for x in aa if 'generation_ms'in x),
            input_tokens=sum(x.get('generation_usage',{}).get('prompt_tokens',0) for x in aa),
            output_tokens=sum(x.get('generation_usage',{}).get('completion_tokens',0) for x in aa),
            source_errors=sum(bool(x.get('grade',{}).get('source_errors')) for x in aa))
    closed=[records[c['id'],'closed-book'] for c in answerable]
    totals=dict(saved_answers=len(records),valid_grades=sum(x['status']=='complete' for x in records.values()),
        generation_tokens=sum(usage(x.get('generation_usage',{})) for x in records.values()),
        grading_tokens=sum(usage(t.get('usage',{})) for x in records.values() for t in x['grading_attempts']),
        grade_attempts=sum(len(x['grading_attempts']) for x in records.values()),
        invalid_grades=sum(not t['valid'] for x in records.values() for t in x['grading_attempts']),
        truncated_generations=sum(x.get('generation_finish_reason')=='length' for x in records.values()),
        closed_correct=sum(x.get('grade',{}).get('correctness')==2 for x in closed),closed_questions=21,
        original_index_unchanged=True)
    totals['promptfoo_replay_stats']=load(RUN/'promptfoo-replay.json')['results']['stats']
    dump(RUN/'summary.json',dict(variants=summaries,totals=totals))
    dump(REPORT/'results.json',dict(variants=summaries,totals=totals))
    blocks=[];md=[]
    def section(identifier,title):
        blocks.append(f'<section id="{identifier}"><h2>{e(title)}</h2>')
        md.extend([f'<a id="{identifier}"></a>',f'## {title}',''])
    def para(text):
        blocks.append('<p>'+e(text)+'</p>');md.extend([text,''])
    def tab(headers,rows):
        blocks.append(table(headers,rows));md.extend([mdtable(headers,rows),''])
    def end():blocks.append('</section>')
    blocks.append('<h1>数模论文RAG评测：四项检索实验</h1>')
    md+=['# 数模论文RAG评测：四项检索实验','']
    para('已完成 · 2026-11-06 · Promptfoo 0.125.1。本轮只比较候选数量、精排保留数量、精排开关和切块大小。24道题运行8组配置，并增加无文档对照；不进行额外调参。')
    para('主要结论：本题库保留精排、保留5块更合适；384-token切块提高证据完整性，但增加输入量；候选40比20多找齐1题，检索更慢。四项分别比较，没有验证这些取值组合后的效果。')
    blocks.append('<p><a href="#questions">全部24道题与逐题回答</a> · <a href="QUESTIONS.md">独立题目文档</a> · <a href="FINAL_EVALUATION.md">Markdown版</a> · <a href="results.json">结果数据</a></p>')
    section('scope','1. 用什么资料、怎样比较')
    para(f'三篇论文原文件共130页，正式纳入71页、{manifest["characters"]:,}字符。排除目录、空白页及代码、问卷、图像表格附录。三个文档混合检索，用来源标签区分；每篇8题，共21道有答案题、3道无答案题。全部用于条件比较，没有独立保留检验。')
    tab(['论文','原PDF页数','正式范围'],[[x['filename'],x['total_pages'], '第1—27页' if x['doc']=='paper-b' else '第1—17页' if x['doc']=='paper-c' else '第1—2、5—29页'] for x in manifest['documents']])
    para('表头说明：“原PDF页数”含附录；“正式范围”是参与所有实验的同一批页面。题目考察本文采用的数据、设置、数值和结论，不评价原论文数学模型本身是否正确。')
    chunk_counts={size:Counter(x['metadata']['source'] for x in load(LOCAL/f'chunks-{size}.json')) for size in [128,256,384]}
    tab(['论文','每块最多128 token','每块最多256 token（基准）','每块最多384 token'],
        [[x['filename'],*[f'{chunk_counts[size][x["filename"]]}块' for size in [128,256,384]]] for x in manifest['documents']]+
        [['切块总数',*[f'{sum(chunk_counts[size].values())}块' for size in [128,256,384]]]])
    para('表头说明：三列是同一批71页正文按不同块大小切分后的数量，每套都按PDF页分别切分、相邻块重叠40 token，页尾不足上限的内容保留。基准资料库共242块；除chunk128使用535块、chunk384使用163块外，其他配置均使用这套242块的资料库。这里是资料库的总块数，不是单次问答的输入块数；基准问答从242块中检索20块，精排后只交给生成模型5块。')
    blocks.append(diagram());md+=['![实验流程](assets/evaluation-flow.svg)','图文版流程节点可点击：题目、各实验、指标解释及结论均在同一HTML文件内。','']
    end()
    section('settings','2. 具体改了哪些参数')
    tab(['配置','切块token','候选数top_k','保留数top_n','精排'],[[v['id'],v['size'],v['k'],v['n'],'开'if v['rerank']else'关'] for v in VARIANTS])
    para('表头说明：配置是记录名称；切块token是每块正文长度上限；top_k是检索候选数量；top_n是最终交给生成模型的片段数；精排表示是否重新按问题与片段相关性排序。以上参数均发生在生成前。base是共用基准；各项实验只改变表中一个设置。')
    para('共同条件：向量与BM25等权RRF融合；向量模型text2vec-base-chinese，精排模型mmarco-mMiniLMv2-L12-H384-v1；相邻块扩充关闭，重叠40 token，按页切块。生成使用deepseek-chat、legacy提示词、温度0.7、最多512输出token，自动裁判温度0。切块大小不同会改变输入字数；保持片段数量相同，单列输入量，不宣称等输入预算比较。')
    para('关闭精排时保留同一融合候选顺序的前5块；相同切块与候选数的两组候选身份已核对。配置顺序逐题轮换，检索模型预热，每次清理应用向量／精排缓存；生成不复用旧答案，每条件采样一次。索引独立，原论文索引文件身份前后保持一致。')
    end()
    section('metrics','3. 结果表怎么读')
    para('“检索片段中找全答案依据的题数”：检查最初检索出的10、20或40个片段，统计其中包含全部已标注答案依据的题目数量。例如19/21表示：21道有答案的题中，有19道题所需的标注原文都进入了初步检索结果。统计单位是题，不是片段。')
    para('“最终交给模型的片段中，找全答案依据的题数”：检查最后实际交给生成模型的片段，统计其中有多少道题的标注答案依据是完整的。开启精排时，检查重新排序后保留的3、5或8块；关闭精排时，检查按原检索顺序直接保留的前5块。例如，关闭精排的9/21表示直接选出的前5块找全了9道题的标注原文；开启精排的基准组18/21表示精排选出的前5块找全了18道题的标注原文。')
    para('两项都只检查资料有没有找全，不检查模型是否答对。程序按论文、PDF页码与原文位置核对证据，更换切块大小后仍检查同一段原文；证据分布在多个片段中时，可以合起来检查。3道无答案题不计入这两项，分母均为21。')
    para('“事实锚点覆盖率”：每题已覆盖锚点数除以该题总锚点数，再对21题平均；“MRR”：最终片段中第一条独自完整覆盖任一锚点的片段排第1得1、第2得1/2，未找到得0，再对21题平均。它不衡量全部证据完整性。')
    para('“语义通过/24”：逐题检查正确性、依据、行为、语言是否全部为2分，并确认没有被裁判标记的来源错误；满足条件的题数记入这一列。四项分数可在HTML题目附录的“正确/依据/行为/语言”表头下查看。')
    para('“严格通过/24”的标准：同一道有答案题，既要语义通过，又要在最后保留的片段中找全全部标注答案依据，即这道题自己的证据覆盖率为100%。逐题检查这两个条件，同时满足才计1题，最后累加为严格通过题数。对应表头及要求如下：')
    tab(['对应表头','哪项数据要达到什么条件','与严格通过的关系'],[
        ['语义通过/24；附录“正确/依据/行为/语言”','同一道题的四项分数均为2，且没有来源错误','必须满足'],
        ['最终交给模型的片段中，找全答案依据的题数','同一道题的标注答案依据全部找全，即该题证据覆盖率100%','有答案题必须同时满足；按该组实际交给模型的片段判断，不要求一定经过精排'],
        ['事实锚点覆盖率','主结果表显示21道有答案题的平均值','不用整组平均值作门槛；严格通过要求的是该题覆盖率100%'],
        ['检索片段中找全答案依据的题数、MRR、输入token、检索ms','没有严格通过阈值','不直接参与严格通过判定']])
    para('表头说明：“对应表头”指报告中可查看的数据；“哪项数据要达到什么条件”说明逐题门槛；“与严格通过的关系”区分必需条件与仅供比较的指标。3道无答案题只要求语义通过，不要求找全证据。整组语义通过不必为24/24，整组平均覆盖率也不必为100%；严格通过统计的是其中同时满足条件的题数。')
    para('“输入token”是24次生成API记录的输入合计，含问题、正文和来源标签；“检索ms”是24次检索＋精排中位耗时，不含答案生成或评分。二者反映输入量与速度，不影响通过与否。')
    tab(['评分项','2分','1分','0分'],[
        ['正确性','所问事实完整正确／按无答案参考恰当拒答','部分正确或遗漏必要事实','核心错误或未回答'],
        ['依据','事实均有当前片段支持','核心有依据，附加信息支持不足','核心解释无依据或冲突'],
        ['行为','有据回答、准确指出缺失、纠正错误前提','边界模糊或混入猜测','编造缺失信息或接受错误前提'],
        ['语言','主体中文','混杂但中文为主','主体不是中文']])
    para('表头说明：四项独立评分，2分为满足要求，1分为部分满足，0分为未满足。回答诚实说明片段缺失可让依据与行为满分，但原书有答案时正确性仍可失分。语言检查语言选择，不评文采；引用可省略，写出的来源必须正确。裁判与生成来自同模型系列，结果属于辅助自动评分。')
    end()
    groups=[('candidate','4. 候选数量：10、20、40',['k10','base','k40']),
            ('retain','5. 精排保留数量：3、5、8',['n3','base','n8']),
            ('rerank','6. 精排开关',['no-rerank','base']),
            ('chunk','7. 切块大小：128、256、384 token',['chunk128','base','chunk384'])]
    heads=['配置','检索片段中找全答案依据的题数','最终交给模型的片段中，找全答案依据的题数','事实锚点覆盖率','MRR','语义通过/24','严格通过/24','输入token','检索ms']
    conclusions=[]
    for ident,title,vs in groups:
        section(ident,title)
        rows=[]
        for name in vs:
            s=summaries[name]
            rows.append([name,f'{s["candidate_complete"]}/21',f'{s["evidence_complete"]}/21',f'{s["coverage"]:.1%}',f'{s["mrr"]:.3f}',f'{s["semantic"]}/24',f'{s["strict"]}/24',f'{s["input_tokens"]:,}',f'{s["retrieval_ms"]:.0f}'])
        tab(heads,rows)
        para('表头说明沿用第3节：证据指标分母21，语义与严格通过分母24；输入为24题合计，耗时为单次观测的中位值。配置的参数值见第2节。')
        best=max(vs,key=lambda name:(summaries[name]['strict'],summaries[name]['semantic'],summaries[name]['evidence_complete'],-summaries[name]['input_tokens']))
        s=summaries[best]
        line=f'本组按严格通过数优先、同分比较语义通过与证据数量、再比较输入量，{best}表现较优：严格{s["strict"]}/24，找齐{s["evidence_complete"]}/21，生成输入{s["input_tokens"]:,} token。'
        para(line);conclusions.append(title.split('. ',1)[-1]+'：'+line)
        if ident=='candidate':
            para('判断：10候选相对20候选少找齐4题；40候选多找齐1题，但中位检索耗时从1.33秒增至2.30秒。证据优先可选40，时延优先保留20；本轮未测更大的候选数。')
        elif ident=='retain':
            para(f'判断：保留8块相对5块没有增加完整证据题数，严格通过也相同，生成输入增加{(summaries["n8"]["input_tokens"]/summaries["base"]["input_tokens"]-1):.1%}。本轮优先保留5块。三组都对20个候选打分，检索耗时的波动不能解释为保留8块本身更快。')
        elif ident=='rerank':
            para('判断：关闭精排明显减少本地检索阶段的计算，但完整证据从18题降至9题，严格通过从21题降至12题。本题库以质量为目标时保留精排；单次耗时观测不作统计显著性结论。')
        else:
            para(f'判断：384-token块相对256-token块多找齐2题，严格通过由21题增至23题，但生成输入增加{(summaries["chunk384"]["input_tokens"]/summaries["base"]["input_tokens"]-1):.1%}。质量优先可选384；输入量优先保留256。这里只比较块大小，未比较段落或语义切块算法。')
        if ident!='rerank':
            for name in vs:
                if name=='base':continue
                gains=[c['id'] for c in answerable if retrieval[c['id'],name]['context']['complete'] and not retrieval[c['id'],'base']['context']['complete']]
                losses=[c['id'] for c in answerable if not retrieval[c['id'],name]['context']['complete'] and retrieval[c['id'],'base']['context']['complete']]
                para(f'{name}相对base：新增找齐{len(gains)}题（{", ".join(gains) or "无"}）；丢失{len(losses)}题（{", ".join(losses) or "无"}）。')
        if ident=='rerank':
            para('实际例子paper-b-02：问题要求第9页的“平均抽样次数”。开启精排的输入包含第9页，回答222.303与122.246；关闭精排的回答使用摘要中的最少次数221与122，并误称它们来自第9页。这说明相关词命中并不足以区分“最少”与“平均”。')
            examples=[]
            for name in ['no-rerank','base']:
                x=records['paper-b-02',name]
                sources=retrieval['paper-b-02',name]['sources']
                chosen=next((s for s in sources if ('222.303' if name=='base' else '221') in s['text']),sources[0])
                normalized=re.sub(r'\s+','',chosen['text'])
                keyword='222.303' if name=='base'else'221'
                pos=normalized.find(keyword)
                excerpt=normalized[max(0,pos-30):pos+85]
                examples.append([name,f'PDF第{chosen["metadata"]["page"]}页：{excerpt}',x['answer']])
            tab(['配置','实际输入中的短原文','实际回答'],examples)
            para('表头说明：短原文只取自该组当时实际收到的片段；回答保持原样。完整片段、来源和评分在本地逐题档案中，题目附录可以展开两组的实际回答与评分理由。')
        end()
    section('closed-book','8. 不提供论文时，原问答提示词的表现')
    tab(['检查','结果'],[['有答案题正确性满分',f'{totals["closed_correct"]}/21'],['无答案题','另外3题，不计入论文事实命中数'],['无文档生成次数','24']])
    para('表头说明：只看21道有答案题的正确性是否为2，不使用无文档情况下的依据分判定知识命中。无文档组沿用同一legacy提示词，只把片段置空；该提示词仍要求基于片段且不编造，因此拒答不能证明模型没有相关知识。这是上下文移除对照，不是独立的闭卷知识测验，也不能证明训练语料归属。部分问题含限定或数值线索，单次猜中同样会计入。')
    end()
    section('conclusion','9. 本轮结论与边界')
    for line in conclusions:para(line)
    para('四项是共享基准的单因素比较，没有执行所有参数组合。不能把各项较优值拼接后当成已验证的最佳组合；生产默认设置未修改。全部24题用于比较，没有独立保留测试；单次采样不宣称统计显著或任意数学建模论文问答准确率。')
    para(f'共保存{totals["saved_answers"]}份回答，完成{totals["valid_grades"]}份有效评分；评分尝试{totals["grade_attempts"]}次，其中无效{totals["invalid_grades"]}次；输出达到长度上限{totals["truncated_generations"]}份，达到上限的输出不计通过。生成总token {totals["generation_tokens"]:,}，已记录裁判总token {totals["grading_tokens"]:,}。只重评无效评分对应的原答案，不重新生成挑选结果。')
    para('首次Promptfoo HTTP适配将完整对象直接作为响应，缺少工具所需的output字段，导致216项被工具记为“No output”；216份回答及模型评分实际均已保存。修正汇总路径后，使用本地文件provider重放同一批记录，得到150通过、66未通过、0工具错误，未再次调用模型。150/216混合了192份RAG严格检查和24份无文档正确性检查，不作为总体回答准确率。首次档案和离线重放档案均保留。')
    para('原PDF部分公式、表格和图片在文本提取中有缺失，本题库只选择可核对的文字证据，并抽查了原始页面；不据此评价图表问答能力。统计论文摘要与正文的测试案例数等口径存在差异，本轮问题避开未限定的冲突数字；按指定来源回答，不进行原研究有效性审查。题目与标注由AI整理，独立人工复核未完成。')
    end()
    section('questions','附录：全部24道题、参考与实际回答')
    para('每篇8题，全部为比较用题。题干完整列出，点击展开参考答案、原文锚点、8组实际回答及无文档回答。原文页码是PDF物理页码，原文件保留在本地私有目录。')
    qmd=['# 数模论文：24道比较题与参考答案','','[图文报告](FINAL_EVALUATION.html) · [Markdown报告](FINAL_EVALUATION.md)','']
    for doc, (_,title,_) in DOCS.items():
        blocks.append(f'<h3 id="questions-{doc}">{e(title)}：8题</h3>')
        qmd+=['## '+title,'']
        for c in cases:
            if c['doc']!=doc:continue
            kind={'numeric':'数值与配对','distinction':'区分易混信息','multi_fact':'综合多个事实','conditions':'条件与约束','paraphrase':'原意解释','detail':'具体细节','unanswerable':'正文未提供的信息'}[c['type']]
            blocks.append(f'<article id="{c["id"]}"><p class="qid">{c["id"]} · {e(kind)}</p><h3>{e(c["question"])}</h3><details><summary>参考答案、原文位置与各组实际回答</summary><p><strong>参考答案：</strong>{e(c["reference"])}</p>')
            qmd += [f'<a id="{c["id"]}"></a>','### '+c['id'],'',c['question'],'','参考答案：'+c['reference'],'']
            for g in c['evidence']:
                locs=sorted({loc['page'] for loc in g['locations']})
                filename=DOCS[c['doc']][0]
                links='、'.join(f'<a href="../../../数模论文/{e(filename)}#page={p}">PDF第{p}页</a>' for p in locs)
                blocks.append(f'<p>原文锚点：{e(g["quote"])}（{links}）</p>')
                qmd+=['- 原文锚点：'+g['quote']+'；PDF页码：'+','.join(map(str,locs))]
            if not c['evidence']:blocks.append('<p>无答案题：正文未报告所问信息，不标注正向事实锚点。</p>')
            score_rows=[]
            for v in [x['id'] for x in VARIANTS]+['closed-book']:
                x=records[c['id'],v];grade=x.get('grade',{})
                evidence_text={True:'是',False:'否',None:'不适用'}[x.get('evidence_complete')]
                strict_text='不适用（仅比较正确性）' if v=='closed-book' else ('通过' if x.get('strict_pass') else '未通过')
                score_rows.append([v,'/'.join(str(grade.get(k,'?'))for k in ['correctness','grounding','behavior','language']),evidence_text,strict_text])
            blocks.append(table(['配置','正确/依据/行为/语言','标注找齐','严格通过'],score_rows))
            for v in [x['id']for x in VARIANTS]+['closed-book']:
                x=records[c['id'],v]
                blocks.append(f'<details class="answer"><summary>{e(v)}：实际回答及评分理由</summary><p class="preserve">{e(x.get("answer","生成失败"))}</p><p>评分理由：{e(x.get("grade",{}).get("reason",x.get("error","")))}</p></details>')
            blocks.append('</details></article>')
            qmd+=['']
    end()
    REPORT.mkdir(parents=True,exist_ok=True)
    (REPORT/'QUESTIONS.md').write_text('\n'.join(qmd)+'\n',encoding='utf-8')
    (REPORT/'FINAL_EVALUATION.md').write_text('\n'.join(md[:md.index('<a id="questions"></a>')])+ '\n完整题目与参考答案见[题库](QUESTIONS.md)，各组实际回答见[图文版附录](FINAL_EVALUATION.html#questions)。\n',encoding='utf-8')
    (REPORT/'assets').mkdir(exist_ok=True)
    (REPORT/'assets/evaluation-flow.svg').write_text(diagram().replace('href="#','href="../FINAL_EVALUATION.html#'),encoding='utf-8')
    css='''body{margin:0;background:#f3f6fa;color:#20344d;font:16px/1.85 "Microsoft YaHei",sans-serif}*{box-sizing:border-box}html{scroll-padding-top:80px}header{position:sticky;top:0;background:#173753;padding:12px 22px;z-index:2}nav{max-width:1200px;margin:auto;display:flex;flex-wrap:wrap;gap:10px 22px}nav a{color:white;font-size:14px}main{max-width:1260px;margin:26px auto;background:white;border:1px solid #dbe5ed;border-radius:16px;padding:32px 38px}h1{font-size:30px}h2{font-size:24px;border-bottom:1px solid #dbe5ed;margin-top:38px;padding-bottom:12px}h3{font-size:18px}a,summary{color:#17648d}a{text-underline-offset:4px}svg{width:100%;height:auto;margin:18px 0}svg a:hover rect{fill:#e2eef7}a:focus-visible{outline:3px solid #2e8abd}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #dbe5ed;padding:10px 12px;text-align:left;vertical-align:top}th{background:#e9f0f7}tr:nth-child(even){background:#f8fafc}article{border:1px solid #dbe5ed;border-radius:12px;padding:18px 22px;margin:18px 0;scroll-margin-top:80px}.qid{font-size:13px;font-weight:bold;color:#17648d}summary{cursor:pointer}.answer{padding:10px 0;border-bottom:1px solid #e7eef4}.preserve{white-space:pre-wrap;overflow-wrap:anywhere}.back{position:fixed;right:20px;bottom:18px;background:#173753;color:white;padding:8px 16px;border-radius:24px}@media(max-width:700px){main{margin:10px;padding:18px}h1{font-size:24px}header{padding:8px}nav{gap:6px 12px}}'''
    content='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>数模论文RAG四项实验</title><style>'+css+'</style></head><body><header><nav><a href="#top">总览</a><a href="#settings">参数</a><a href="#candidate">候选数</a><a href="#retain">保留数</a><a href="#rerank">精排开关</a><a href="#chunk">切块</a><a href="#closed-book">无文档对照</a><a href="#questions">全部题目</a></nav></header><main id="top">'+''.join(blocks)+'</main><a class="back" href="#top">返回顶部 ↑</a></body></html>'
    (REPORT/'FINAL_EVALUATION.html').write_text(content,encoding='utf-8')
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.ids=[];self.hrefs=[]
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if 'id'in attrs:self.ids.append(attrs['id'])
            if 'href'in attrs:self.hrefs.append(attrs['href'])
    links=Links();links.feed(content)
    assert len(links.ids)==len(set(links.ids))
    for href in links.hrefs:
        target,_,anchor=href.partition('#')
        if not target:assert anchor in links.ids,href
        else:assert (REPORT/unquote(target)).exists(),href
    assert len(re.findall(r'<article id=',content))==24
    print(json.dumps(dict(totals=totals,report=str(REPORT/'FINAL_EVALUATION.html')),ensure_ascii=False),flush=True)


if __name__=='__main__':build()
