"""Generate and grade answers from two fixed hybrid retrieval contexts."""
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RUN = Path(os.environ["THREEBODY_RUN_DIR"]).resolve()
os.environ["RAG_INDEX_DIR"] = str(ROOT / "eval/indexes/threebody/book1")
os.environ["CACHE_BACKEND"] = "memory"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["RAG_PROMPT_VERSION"] = "legacy"
os.chdir(ROOT)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langchain_deepseek import ChatDeepSeek
import rag_langchain as rag
from eval.threebody.evidence_metrics import evidence_metrics
from eval.threebody.semantic_grading import grade_answer
from eval.threebody.source_context import render_sources, source_metadata

CASES = {c["id"]: c for c in json.loads((RUN / "cases.frozen.json").read_text(encoding="utf-8"))}
RUBRIC = (ROOT / "eval/promptfoo/semantic-rubric.txt").read_text(encoding="utf-8") + (ROOT / "eval/threebody/source-grading-rules.txt").read_text(encoding="utf-8")
grader = ChatDeepSeek(model="deepseek-chat", temperature=0, timeout=90, max_retries=1).bind(response_format={"type": "json_object"})
app = FastAPI()
lock = threading.Lock()


class Request(BaseModel):
    case_id: str
    variant: Literal["hybrid-n0", "hybrid-n1"]


@app.get("/health")
def health():
    return {"cases": len(CASES), "variants": ["hybrid-n0", "hybrid-n1"], "live_retrieval": False}


@app.post("/evaluate")
def evaluate(request: Request):
    if request.case_id not in CASES:
        raise HTTPException(404, "Unknown development case")
    output_path = RUN / f"{request.case_id}-{request.variant}.json"
    with lock:
        if output_path.exists():
            raise HTTPException(409, "Observation already saved; use a new run")
        case = CASES[request.case_id]
        saved = json.loads((RUN / "contexts" / output_path.name).read_text(encoding="utf-8"))
        sources = saved["sources"]
        context = render_sources(sources)
        docs = [Document(page_content=s["text"], metadata=s["metadata"]) for s in sources]
        retriever = RunnableLambda(lambda _: docs)
        chain = RunnableLambda(lambda payload: {**payload, "context": context}) | rag.make_chain(retriever)
        usage = UsageMetadataCallbackHandler()
        started = time.perf_counter()
        response = rag.query(case["question"], retriever, chain.with_config(callbacks=[usage]), use_cache=False, lang="zh")
        generation_ms = (time.perf_counter() - started) * 1000
        result = {"id": case["id"], "variant": request.variant, "type": case["type"],
                  "expected_behavior": case["behavior"], "response": response, "sources": sources,
                  "generation_ms": generation_ms, "generation_usage": usage.usage_metadata,
                  "recorded_retrieval_ms": saved["retrieval_ms"], "live_retrieval": False,
                  "context_body_tokens": saved["context_body_tokens"],
                  "context_labeled_tokens": saved["context_labeled_tokens"],
                  "prompt_fingerprint": rag.PROMPT_FINGERPRINT,
                  **evidence_metrics(case, saved["context_ids"]), "grading_status": "pending"}
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        payload = {"question": case["question"], "expected_language": "zh", "reference_answer": case["reference"],
                   "reference_kind": {"correct_premise": "correct_premise", "abstain": "abstention"}.get(case["behavior"], "factual"),
                   "expected_behavior": case["behavior"], "context": context,
                   "source_metadata": source_metadata(sources), "answer": response["answer"]}
        grading_started = time.perf_counter()
        try:
            result.update(grade_answer(grader, RUBRIC, payload))
            result["grading_status"] = "complete"
        except Exception as exc:
            result.update(grading_status="error", grading_error=type(exc).__name__)
            output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            raise HTTPException(502, "Grading failed; answer saved") from exc
        result["grading_ms"] = (time.perf_counter() - grading_started)*1000
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
