"""Promptfoo adapter: generate once per frozen context and retain every grade."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from openai import OpenAI
from pydantic import BaseModel

from eval.modeling.study import ROOT, RUN, dump, load, sha
from eval.threebody.semantic_grading import validate_grade

load_dotenv(ROOT/'.env')
manifest=load(RUN/'manifest.json')
for filename, expected in manifest['code_sha256'].items():
    if sha(ROOT/filename) != expected:
        raise RuntimeError(f'Frozen input changed: {filename}')
if sha(RUN/'cases.json') != manifest['dataset_sha256']:
    raise RuntimeError('Question bank changed')
CASES={c['id']:c for c in load(RUN/'cases.json')}
PROMPT=load(ROOT/'prompts.json')['legacy']
RUBRIC=(ROOT/'eval/promptfoo/semantic-rubric.txt').read_text(encoding='utf-8')+'''
\nVerify every explicit source document, PDF page or chunk-ID against source_metadata.
Wrong source attribution requires correctness, grounding and behavior at most 1.
Citations are optional; missing citations are not an error. Return source_errors as an array.
Use the reference as the factual target, not as retrieved evidence. For answerable questions,
an honest insufficient-evidence response can be well grounded yet factually incomplete.
Return concise reasons (at most 100 Chinese characters) and no Markdown code fences.
'''
client=OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'],base_url=os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com'),timeout=90,max_retries=1)
app=FastAPI()
locks={}
guard=threading.Lock()


class Request(BaseModel):
    case_id: str
    variant: str


def render(sources, variant):
    labels=[]
    parts=[]
    for s in sources:
        m=s['metadata']
        label=dict(id=f'chunk-{m["index"]}',source=m['source'],page=m['page'])
        labels.append(label)
        parts.append('[SOURCE '+json.dumps(label,ensure_ascii=False)+']\n'+s['text']+'\n[/SOURCE]')
    return '\n\n'.join(parts),labels


def summary(result):
    return {k:result.get(k) for k in ['case_id','variant','status','grade','semantic_pass','strict_pass',
                                      'evidence_complete','generation_finish_reason','error']}


@app.get('/health')
def health():
    return dict(cases=len(CASES),contexts=len(list((RUN/'retrieval').glob('*.json'))),study=manifest['study'])


@app.post('/evaluate')
def evaluate(request:Request):
    if request.case_id not in CASES or request.variant not in [v['id'] for v in manifest['variants']]+['closed-book']:
        return dict(status='error',error='Unknown observation')
    key=f'{request.case_id}--{request.variant}'
    with guard:
        lock=locks.setdefault(key,threading.Lock())
    with lock:
        path=RUN/'answers'/f'{key}.json'
        if path.exists():
            result=load(path)
            if result['status']=='complete' or result.get('generation_error'):
                return summary(result)
        else:
            c=CASES[request.case_id]
            retrieval=load(RUN/'retrieval'/f'{key}.json') if request.variant!='closed-book' else None
            sources=retrieval['sources'] if retrieval else []
            context,labels=render(sources,request.variant)
            result=dict(case_id=c['id'],variant=request.variant,status='started',sources=sources,
                        rendered_context=context,source_metadata=labels,question=c['question'],
                        evidence_complete=retrieval['context']['complete'] if retrieval else None,
                        generation_prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),grading_attempts=[])
            dump(path,result)
        c=CASES[request.case_id]
        if 'answer' not in result:
            t=time.perf_counter()
            try:
                message=client.chat.completions.create(model='deepseek-chat',temperature=0.7,max_tokens=512,
                    messages=[dict(role='user',content=PROMPT.format(question=c['question'],context=result['rendered_context']))])
                result.update(answer=message.choices[0].message.content, generation_ms=(time.perf_counter()-t)*1000,
                              generation_usage=message.usage.model_dump() if message.usage else {},
                              generation_finish_reason=message.choices[0].finish_reason,model=message.model,status='generated')
                dump(path,result)
            except Exception as exc:
                result.update(status='error',generation_error=type(exc).__name__,error='generation failed')
                dump(path,result)
                return summary(result)
        payload=dict(question=c['question'],reference_answer=c['reference'],reference_kind='abstention' if c['behavior']=='abstain' else 'factual',
                     expected_behavior=c['behavior'],expected_language='zh',context=result['rendered_context'],
                     source_metadata=result['source_metadata'],answer=result['answer'])
        # At most two grading attempts; the generated answer is never replaced.
        while len(result['grading_attempts'])<2:
            attempt=dict(started_at=time.time())
            t=time.perf_counter()
            try:
                message=client.chat.completions.create(model='deepseek-chat',temperature=0,max_tokens=700,
                    response_format={'type':'json_object'},messages=[dict(role='system',content=RUBRIC),
                    dict(role='user',content=json.dumps(payload,ensure_ascii=False))])
                attempt.update(raw=message.choices[0].message.content,usage=message.usage.model_dump() if message.usage else {},
                               finish_reason=message.choices[0].finish_reason,model=message.model)
                grade=validate_grade(json.loads(attempt['raw']))
                if not isinstance(grade.get('source_errors'),list):
                    raise ValueError('Missing source_errors')
                if grade['source_errors'] and any(grade[k]>1 for k in ['correctness','grounding','behavior']):
                    raise ValueError('Source error penalty not applied')
                result['grade']=grade
                result['semantic_pass']=all(grade[k]==2 for k in ['correctness','grounding','behavior','language']) and not grade['source_errors']
                result['strict_pass']=result['semantic_pass'] and (c['behavior']=='abstain' or bool(result['evidence_complete']))
                result['status']='complete'
                attempt['valid']=True
            except Exception as exc:
                attempt.update(valid=False,error=type(exc).__name__)
                result.update(status='grading_error',error='grading failed; answer retained')
            attempt['elapsed_ms']=(time.perf_counter()-t)*1000
            result['grading_attempts'].append(attempt)
            dump(path,result)
            if result['status']=='complete':
                break
        return summary(result)
