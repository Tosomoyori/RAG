"""Prepare and run isolated modeling-paper retrieval ablations."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
LOCAL = ROOT / 'eval/corpora/modeling/local'
REPORT = ROOT / 'eval/reports/modeling'
RUN = REPORT / 'raw/study-v1'
HERE = Path(__file__).resolve().parent
DOCS = {
    'paper-b': ('B题省一论文.pdf', '生产决策与成本控制', list(range(1, 28))),
    'paper-c': ('C题省三论文.pdf', '蔬菜定价与补货', list(range(1, 18))),
    'statistics': ('统计建模论文.pdf', '数据泄露统计研究', [1, 2] + list(range(5, 30))),
}
VARIANTS = [
    dict(id='base', size=256, k=20, n=5, rerank=True),
    dict(id='k10', size=256, k=10, n=5, rerank=True),
    dict(id='k40', size=256, k=40, n=5, rerank=True),
    dict(id='n3', size=256, k=20, n=3, rerank=True),
    dict(id='n8', size=256, k=20, n=8, rerank=True),
    dict(id='no-rerank', size=256, k=20, n=5, rerank=False),
    dict(id='chunk128', size=128, k=20, n=5, rerank=True),
    dict(id='chunk384', size=384, k=20, n=5, rerank=True),
]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text):
    return re.sub(r'\s+', '', text)


def runtime():
    os.chdir(ROOT)
    os.environ.update(RAG_INDEX_DIR=str(ROOT / 'eval/indexes/modeling'), CACHE_BACKEND='memory',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', ANONYMIZED_TELEMETRY='False')
    import torch
    torch.set_num_threads(4)
    import rag_langchain as rag
    return rag


def metrics(case, docs):
    if not case['evidence']:
        return dict(coverage=None, complete=None, mrr=None)
    def found(location, selected):
        intervals = sorted((d.metadata['norm_start'], d.metadata['norm_end']) for d in selected
                           if d.metadata['doc'] == location['doc'] and d.metadata['page'] == location['page'])
        cursor = location['start']
        for a, b in intervals:
            if a <= cursor:
                cursor = max(cursor, b)
        return cursor >= location['end']
    groups = [any(found(loc, docs) for loc in group['locations']) for group in case['evidence']]
    first = next((i for i, d in enumerate(docs, 1)
                  if any(found(loc, [d]) for g in case['evidence'] for loc in g['locations'])), 0)
    return dict(coverage=sum(groups) / len(groups), complete=all(groups), mrr=1 / first if first else 0)


def prepare():
    import fitz
    from transformers import AutoTokenizer
    LOCAL.mkdir(parents=True, exist_ok=True)
    RUN.mkdir(parents=True, exist_ok=True)
    if (RUN / 'manifest.json').exists():
        raise RuntimeError('Study already prepared; use existing frozen inputs')
    tokenizer = AutoTokenizer.from_pretrained(str(ROOT / 'text2vec-base-chinese'), local_files_only=True)
    all_pages = []
    sources = []
    for key, (filename, title, included) in DOCS.items():
        path = ROOT / '数模论文' / filename
        pdf = fitz.open(path)
        sources.append(dict(doc=key, filename=filename, title=title, sha256=sha(path),
                            total_pages=len(pdf), included_pages=included))
        for page in included:
            text = re.sub(r'\n\s*\d+\s*$', '', pdf[page-1].get_text(sort=True)).strip()
            all_pages.append(dict(doc=key, source=filename, title=title, page=page,
                                  text=text, normalized=norm(text)))
    dump(LOCAL / 'pages.json', all_pages)
    from eval.modeling.question_specs import SPECS
    cases = []
    for key, number, question, reference, facts, kind in SPECS:
        evidence = []
        for quote in facts:
            quote = norm(quote)
            locations = []
            for p in all_pages:
                if p['doc'] != key:
                    continue
                for match in re.finditer(re.escape(quote), p['normalized']):
                    locations.append(dict(doc=key, page=p['page'], start=match.start(), end=match.end()))
            if not locations:
                raise ValueError(f'Unmatched evidence {key}-{number}: {quote}')
            evidence.append(dict(quote=quote, locations=locations))
        cases.append(dict(id=f'{key}-{number:02d}', doc=key, question=question, reference=reference,
                          type=kind, behavior='abstain' if not facts else 'answer', evidence=evidence))
    assert len(cases) == 24 and sum(not c['evidence'] for c in cases) == 3
    absence = {'paper-b': r'GPU|显存', 'paper-c': r'github\.com|gitee\.com', 'statistics': r'random_state|random_seed|seed\(|随机种子'}
    for key, pattern in absence.items():
        assert not re.search(pattern, ''.join(p['text'] for p in all_pages if p['doc']==key), re.I), key
    dump(RUN / 'cases.json', cases)
    dump(HERE / 'questions.json', cases)
    for size in [128, 256, 384]:
        chunks = []
        for p in all_pages:
            offsets = tokenizer(p['text'], add_special_tokens=False, return_offsets_mapping=True)['offset_mapping']
            for start in range(0, len(offsets), size-40):
                if start and start+40 >= len(offsets):
                    break
                a, b = offsets[start][0], offsets[min(start+size, len(offsets))-1][1]
                if a >= b:
                    continue
                text = p['text'][a:b]
                md = dict(index=len(chunks), source=p['source'], doc=p['doc'], page=p['page'],
                          chapter=f'PDF第{p["page"]}页', section=f'{p["doc"]}/page-{p["page"]}',
                          char_start=a, char_end=b, norm_start=len(norm(p['text'][:a])),
                          norm_end=len(norm(p['text'][:b])))
                chunks.append(dict(text=text, metadata=md))
        dump(LOCAL / f'chunks-{size}.json', chunks)
    identity_paths = [Path(__file__), HERE/'question_specs.py', ROOT/'retrieval.py', ROOT/'rag_langchain.py',
                      ROOT/'prompts.json', ROOT/'eval/promptfoo/semantic-rubric.txt']
    identity_paths += [ROOT/'text2vec-base-chinese/config.json', ROOT/'mmarco-mMiniLMv2-L12-H384-v1/config.json']
    manifest = dict(study='modeling-ablation-v1', status='prepared', documents=sources,
                    pages=len(all_pages), characters=sum(len(p['text']) for p in all_pages),
                    questions=24, answerable=21, no_answer=3, variants=VARIANTS,
                    candidate_mode='hybrid; production BM25 + vector RRF', neighbors=0, overlap=40,
                    generation=dict(model='deepseek-chat', temperature=0.7, max_tokens=512, prompt='legacy'),
                    grading=dict(model='deepseek-chat', temperature=0, max_tokens=700, kind='auxiliary automatic'),
                    execution='24 questions x 8 RAG configurations + 24 closed-book answers; all comparison questions; no holdout',
                    dataset_sha256=sha(RUN/'cases.json'),
                    code_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in identity_paths},
                    original_index_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'chroma_db').rglob('*') if p.is_file()})
    dump(RUN/'manifest.json', manifest)
    dump(REPORT/'inputs/manifest.json', manifest)
    tests = []
    variants = VARIANTS + [dict(id='closed-book')]
    for i, c in enumerate(cases):
        order = variants[i % len(variants):] + variants[:i % len(variants)]
        for v in order:
            tests.append(dict(description=f'{c["id"]}/{v["id"]}', vars=dict(case_id=c['id'], variant=v['id'])))
    dump(HERE/'tests.json', tests)
    dump(HERE/'promptfooconfig.json', dict(description='Private modeling papers: four controlled retrieval ablations',
        prompts=['{{case_id}} {{variant}}'],
        providers=[dict(id='http', config=dict(url='http://127.0.0.1:8005/evaluate', method='POST',
            headers={'Content-Type':'application/json'},body={'case_id':'{{case_id}}','variant':'{{variant}}'},
            transformResponse='json',timeout=240000))], tests='file://tests.json',
        defaultTest={'assert':[{'type':'javascript','value':'file://checks.cjs'}]}))
    print(json.dumps({k:manifest[k] for k in ['pages','characters','questions']},ensure_ascii=False),flush=True)


def retrieve_all():
    rag = runtime()
    import cache
    from langchain_chroma import Chroma
    from retrieval import retrieve_candidates
    embed = rag.get_embedding_model('zh')
    tokenizer = rag._get_tokenizer('zh')
    cases = load(RUN/'cases.json')
    stores = {}
    for size in [128, 256, 384]:
        rows = load(LOCAL/f'chunks-{size}.json')
        store = Chroma(collection_name=f'modeling_{size}', embedding_function=embed,
                       persist_directory=str(ROOT/f'eval/indexes/modeling/chunk-{size}'))
        if not store._collection.count():
            for start in range(0, len(rows), 128):
                batch = rows[start:start+128]
                store.add_texts([r['text'] for r in batch], [r['metadata'] for r in batch],
                                ids=[f'c-{r["metadata"]["index"]}' for r in batch])
        if store._collection.count() != len(rows):
            raise RuntimeError('Index identity mismatch')
        stores[size] = store
        print(f'Index size={size}, chunks={len(rows)}', flush=True)
    warm = retrieve_candidates(stores[256], '模型参数与计算结果', 20, 'hybrid')
    rag.rerank_cached('模型参数与计算结果', [d.page_content for d in warm])
    for i,c in enumerate(cases):
        variants = VARIANTS[i % 8:] + VARIANTS[:i % 8]
        for v in variants:
            dest = RUN/'retrieval'/f'{c["id"]}--{v["id"]}.json'
            if dest.exists():
                continue
            cache.clear(['embed','rerank'])
            t0=time.perf_counter()
            candidates=retrieve_candidates(stores[v['size']], c['question'], v['k'], 'hybrid')
            t1=time.perf_counter()
            if v['rerank']:
                scores=rag.rerank_cached(c['question'],[d.page_content for d in candidates])
                ordered=[d for d,_ in sorted(zip(candidates,scores),key=lambda pair:pair[1],reverse=True)]
            else:
                ordered=candidates
            selected=ordered[:v['n']]
            t2=time.perf_counter()
            sources=[dict(text=d.page_content,metadata=d.metadata) for d in selected]
            dump(dest,dict(case_id=c['id'],variant=v['id'],config=v,candidate_ids=[d.metadata['index'] for d in candidates],
                context_ids=[d.metadata['index'] for d in selected], candidate=metrics(c,candidates),context=metrics(c,selected),
                chunks=len(selected),body_tokens=sum(len(tokenizer.encode(d.page_content,add_special_tokens=False)) for d in selected),
                candidate_ms=(t1-t0)*1000,rerank_ms=(t2-t1)*1000,retrieval_ms=(t2-t0)*1000,sources=sources))
        print(f'Retrieved {i+1}/{len(cases)}: {c["id"]}',flush=True)
    print('RETRIEVAL_COMPLETE',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['prepare','retrieve'])
    args=p.parse_args()
    {'prepare':prepare,'retrieve':retrieve_all}[args.action]()
