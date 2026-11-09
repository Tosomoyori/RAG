"""Local retrieval-only experiment using the production retrieval implementation."""
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
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.chdir(ROOT)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import cache
import rag_langchain as rag
from retrieval import retrieve_candidates, expand_context
from eval.threebody.evidence_metrics import evidence_metrics
from eval.threebody.source_context import render_sources

CASES = {c["id"]: c for c in json.loads((RUN / "cases.frozen.json").read_text(encoding="utf-8"))}
store = rag.load_store("zh")
tokenizer = rag._get_tokenizer("zh")
# Warm model weights, Chroma query path and both candidate-retrieval branches.
warm = retrieve_candidates(store, "检索预热", 20, "hybrid")
rag.rerank_cached("检索预热", [d.page_content for d in warm])
expand_context(store, warm[:5], tokenizer, radius=1, max_chunks=10, max_tokens=2560)
cache.clear(["embed", "rerank"])
app = FastAPI()
lock = threading.Lock()


class Request(BaseModel):
    case_id: str
    mode: Literal["vector", "hybrid"]
    neighbors: int = Field(ge=0, le=1)


def indexes(docs):
    return [d.metadata["index"] for d in docs]


@app.get("/health")
def health():
    return {"scope": "book1", "cases": len(CASES), "chunks": store._collection.count(), "models_warmed": True}


@app.post("/retrieve")
def retrieve(request: Request):
    if request.case_id not in CASES:
        raise HTTPException(404, "Unknown development case")
    case = CASES[request.case_id]
    variant = f"{request.mode}-n{request.neighbors}"
    target = RUN / f"{case['id']}-{variant}.json"
    with lock:
        if target.exists():
            raise HTTPException(409, "This observation is already recorded; use a new run")
        cache.clear(["embed", "rerank"])
        started = time.perf_counter()
        candidates = retrieve_candidates(store, case["question"], 20, request.mode)
        recalled = time.perf_counter()
        scores = rag.rerank_cached(case["question"], [d.page_content for d in candidates])
        seeds = [d for d, _ in sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)][:5]
        reranked = time.perf_counter()
        context = expand_context(store, seeds, tokenizer, radius=1, max_chunks=10, max_tokens=2560) if request.neighbors else seeds
        ended = time.perf_counter()
        details = [{"text": d.page_content, "metadata": d.metadata} for d in context]
        body_tokens = sum(len(tokenizer.encode(d.page_content, add_special_tokens=False)) for d in context)
        if len(context) > 10 or body_tokens > 2560:
            raise ValueError("Context budget exceeded")
        expected = {index for group in case["evidence"] for index in group["acceptable_indexes"]}
        first = next((rank for rank, d in enumerate(seeds, 1) if d.metadata["index"] in expected), 0)
        result = {
            "id": case["id"], "type": case["type"], "variant": variant,
            "mode": request.mode, "neighbors": request.neighbors,
            "candidate_ids": indexes(candidates), "seed_ids": indexes(seeds), "context_ids": indexes(context),
            "candidate_metrics": evidence_metrics(case, indexes(candidates)),
            "seed_metrics": evidence_metrics(case, indexes(seeds)),
            "context_metrics": evidence_metrics(case, indexes(context)),
            "seed_mrr": (1 / first if first else 0) if case["behavior"] != "abstain" else None,
            "context_chunks": len(context), "context_body_tokens": body_tokens,
            "context_labeled_tokens": len(tokenizer.encode(render_sources(details), add_special_tokens=False)),
            "candidate_ms": (recalled-started)*1000, "rerank_ms": (reranked-recalled)*1000,
            "expansion_ms": (ended-reranked)*1000, "retrieval_ms": (ended-started)*1000,
            "cache_stats": cache.get_stats(), "generation_api_calls": 0, "grading_api_calls": 0,
            "sources": details,
        }
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
