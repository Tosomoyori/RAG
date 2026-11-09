"""Execute each frozen holdout question once and retain every grading attempt."""
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RUN = Path(os.environ["THREEBODY_RUN_DIR"]).resolve()
PROFILE = json.loads((RUN / "profile.frozen.json").read_text(encoding="utf-8"))
os.environ.update(RAG_INDEX_DIR=str(ROOT / PROFILE["index"]["directory"]), CACHE_BACKEND="memory",
                  HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", ANONYMIZED_TELEMETRY="False",
                  RAG_PROMPT_VERSION=PROFILE["generation"]["prompt"],
                  RETRIEVAL_MODE=PROFILE["retrieval"]["mode"], CONTEXT_NEIGHBORS=str(PROFILE["retrieval"]["neighbors"]),
                  CONTEXT_MAX_CHUNKS=str(PROFILE["retrieval"]["max_chunks"]),
                  CONTEXT_MAX_TOKENS=str(PROFILE["retrieval"]["max_body_tokens"]))
os.chdir(ROOT)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.runnables import RunnableLambda
from langchain_deepseek import ChatDeepSeek
import cache
import rag_langchain as rag
from eval.threebody.evidence_metrics import evidence_metrics
from eval.threebody.semantic_grading import validate_grade
from eval.threebody.source_context import render_sources, source_metadata

CASES = {c["id"]: c for c in json.loads((RUN / "cases.frozen.json").read_text(encoding="utf-8"))}
assert rag.RETRIEVE_K == PROFILE["retrieval"]["candidate_k"] and rag.RERANK_TOP_N == PROFILE["retrieval"]["rerank_top_n"]
assert rag.CHUNK_TOKENS == PROFILE["index"]["chunk_tokens"] and rag.CHUNK_OVERLAP_TOKENS == PROFILE["index"]["chunk_overlap_tokens"]
RUBRIC = (ROOT / PROFILE["auxiliary_grader"]["base_rubric"]).read_text(encoding="utf-8") + (ROOT / PROFILE["auxiliary_grader"]["source_rules"]).read_text(encoding="utf-8")
store = rag.load_store("zh")
retriever = rag.make_retriever(store, lang="zh")
chain = rag.make_chain(retriever)
grader = ChatDeepSeek(model=PROFILE["auxiliary_grader"]["model"], temperature=0, timeout=90, max_retries=1).bind(response_format={"type": "json_object"})
# Warm the pipeline without executing a holdout question.
retriever.invoke("模型预热")
cache.clear(["embed", "rerank"])
lock = threading.Lock()
app = FastAPI()


class Request(BaseModel):
    case_id: str


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/health")
def health():
    return {"split": "holdout", "cases": len(CASES), "models_warmed": True, "profile": PROFILE["version"]}


@app.post("/evaluate")
def evaluate(request: Request):
    if request.case_id not in CASES:
        raise HTTPException(404, "Unknown frozen holdout case")
    with lock:
        marker = RUN / f"{request.case_id}.started.json"
        if marker.exists():
            raise HTTPException(409, "Holdout case already started; inspect saved stages, do not regenerate")
        case = CASES[request.case_id]
        save(marker, {"id": case["id"], "generation_observation": 1})
        path = RUN / f"{case['id']}.json"
        cache.clear(["embed", "rerank"])
        started = time.perf_counter()
        docs = retriever.invoke(case["question"])
        retrieval_ms = (time.perf_counter()-started)*1000
        sources = [{"text": d.page_content, "metadata": d.metadata} for d in docs]
        context = render_sources(sources)
        metrics = evidence_metrics(case, [d.metadata["index"] for d in docs])
        result = {"id": case["id"], "split": "holdout", "type": case["type"], "expected_behavior": case["behavior"],
                  "sources": sources, **metrics, "retrieval_ms": retrieval_ms, "stage": "retrieved"}
        save(path, result)
        usage = UsageMetadataCallbackHandler()
        fixed = RunnableLambda(lambda _: docs)
        answer_chain = RunnableLambda(lambda payload: {**payload, "context": context}) | chain
        generation_started = time.perf_counter()
        response = rag.query(case["question"], fixed, answer_chain.with_config(callbacks=[usage]), use_cache=False, lang="zh")
        result.update(response=response, generation_usage=usage.usage_metadata,
                      generation_ms=(time.perf_counter()-generation_started)*1000, stage="generated",
                      generation_observations=1, grading_attempts=[])
        save(path, result)
        payload = {"question": case["question"], "expected_language": "zh", "reference_answer": case["reference"],
                   "reference_kind": {"correct_premise": "correct_premise", "abstain": "abstention"}.get(case["behavior"], "factual"),
                   "expected_behavior": case["behavior"], "context": context,
                   "source_metadata": source_metadata(sources), "answer": response["answer"]}
        for attempt in range(2):
            message = grader.invoke([("system", RUBRIC), ("human", json.dumps(payload, ensure_ascii=False))])
            record = {"attempt": attempt + 1, "raw": message.content, "usage": message.usage_metadata or {}}
            result["grading_attempts"].append(record)
            save(path, result)
            try:
                grade = validate_grade(json.loads(message.content))
                if "source_errors" not in grade:
                    raise ValueError("Missing source_errors")
                result.update(grade=grade, grading_usage=message.usage_metadata or {}, stage="complete")
                break
            except (ValueError, TypeError) as exc:
                record["validation_error"] = str(exc)
                save(path, result)
                if attempt == 1:
                    raise HTTPException(502, "Both grading attempts invalid; saved answer retained") from exc
        result["pipeline_with_grading_ms"] = (time.perf_counter()-started)*1000
        save(path, result)
        return result
