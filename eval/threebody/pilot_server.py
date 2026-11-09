"""Local evaluation adapter for the production retriever and answer pipeline."""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RUN = Path(os.environ["THREEBODY_RUN_DIR"]).resolve()
os.environ["RAG_INDEX_DIR"] = str(ROOT / "eval/indexes/threebody/book1")
os.environ["CACHE_BACKEND"] = "memory"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["RAG_PROMPT_VERSION"] = "legacy"
os.environ["RETRIEVAL_MODE"] = "language"
os.environ["CONTEXT_NEIGHBORS"] = "1"
os.environ["CONTEXT_MAX_CHUNKS"] = "10"
os.environ["CONTEXT_MAX_TOKENS"] = "2560"
os.chdir(ROOT)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.runnables import RunnableLambda
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.documents import Document
from langchain_deepseek import ChatDeepSeek
import rag_langchain as rag
from eval.threebody.evidence_metrics import evidence_metrics
from eval.threebody.semantic_grading import grade_answer
from eval.threebody.source_context import render_sources, source_metadata

CASES = {c["id"]: c for c in json.loads((RUN / "cases.frozen.json").read_text(encoding="utf-8"))}
CALIBRATION = {c["id"]: c for c in json.loads((RUN / "calibration.frozen.json").read_text(encoding="utf-8"))} if (RUN / "calibration.frozen.json").exists() else {}
RUBRIC = (ROOT / "eval/promptfoo/semantic-rubric.txt").read_text(encoding="utf-8")
MANIFEST = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))
SOURCE_LABELS = MANIFEST.get("source_labels", False)
if SOURCE_LABELS:
    RUBRIC += (ROOT / "eval/threebody/source-grading-rules.txt").read_text(encoding="utf-8")
app = FastAPI()
store = rag.load_store("zh")
retriever = rag.make_retriever(store, lang="zh")
chain = rag.make_chain(retriever)
grader = ChatDeepSeek(model="deepseek-chat", temperature=0, timeout=90, max_retries=1).bind(response_format={"type": "json_object"})


class Request(BaseModel):
    case_id: str


@app.get("/health")
def health():
    return {"scope": "book1", "chunks": store._collection.count(), "cases": len(CASES)}


@app.post("/calibrate")
def calibrate(request: Request):
    if request.case_id not in CALIBRATION:
        raise HTTPException(404, "Unknown calibration case")
    case = CALIBRATION[request.case_id]
    # Expected scores are reserved for the deterministic assertion, never the grader.
    payload = {key: case[key] for key in ("question", "context", "reference_answer", "reference_kind", "expected_behavior", "answer")}
    payload["expected_language"] = "zh"
    if SOURCE_LABELS:
        payload["source_metadata"] = case.get("source_metadata", [])
    result = {"id": case["id"], "kind": case["kind"], "expected_scores": case["expected_scores"],
              "require_unsupported_claims": case.get("require_unsupported_claims", False),
              "require_source_errors": case.get("require_source_errors", False),
              "require_no_source_errors": case.get("require_no_source_errors", False),
              **grade_answer(grader, RUBRIC, payload)}
    (RUN / f"{case['id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


@app.post("/regrade")
def regrade(request: Request):
    if request.case_id not in CASES or not SOURCE_LABELS:
        raise HTTPException(404, "Source-aware frozen answer not available")
    case = CASES[request.case_id]
    baseline = json.loads((RUN / "frozen-baseline" / f"{case['id']}.json").read_text(encoding="utf-8"))
    payload = {"question": case["question"], "expected_language": "zh",
               "reference_answer": case["reference"],
               "reference_kind": {"correct_premise": "correct_premise", "abstain": "abstention"}.get(case["behavior"], "factual"),
               "expected_behavior": case["behavior"], "context": render_sources(baseline["sources"]),
               "source_metadata": source_metadata(baseline["sources"]), "answer": baseline["response"]["answer"]}
    result = {**baseline, **grade_answer(grader, RUBRIC, payload), "regraded_saved_answer": True,
              "generation_usage": {}, "source_labels": True}
    (RUN / f"regrade-{case['id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


@app.post("/evaluate")
def evaluate(request: Request):
    if request.case_id not in CASES:
        raise HTTPException(404, "Unknown pilot case")
    case = CASES[request.case_id]
    started = time.perf_counter()
    if MANIFEST.get("frozen_source_run"):
        saved = json.loads((RUN / "frozen-baseline" / f"{case['id']}.json").read_text(encoding="utf-8"))
        docs = [Document(page_content=s["text"], metadata=s["metadata"]) for s in saved["sources"]]
    else:
        docs = retriever.invoke(case["question"])
    retrieval_ms = (time.perf_counter() - started) * 1000
    # Freeze this retrieval for query(), avoiding a second retrieval with changed context.
    generation_usage = UsageMetadataCallbackHandler()
    details = [{"text": d.page_content, "metadata": d.metadata} for d in docs]
    context = render_sources(details) if SOURCE_LABELS else rag.format_docs(docs)
    answer_chain = (RunnableLambda(lambda payload: {**payload, "context": context}) | chain) if SOURCE_LABELS else chain
    response = rag.query(case["question"], RunnableLambda(lambda _: docs),
                         answer_chain.with_config(callbacks=[generation_usage]), use_cache=False, lang="zh")
    response["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    details = [{"text": d.page_content, "metadata": d.metadata} for d in docs]
    indexes = {d.metadata["index"] for d in docs}
    evidence = evidence_metrics(case, indexes)
    grading_input = {"question": case["question"], "expected_language": "zh",
                     "reference_answer": case["reference"],
                     "reference_kind": {"correct_premise": "correct_premise", "abstain": "abstention"}.get(case["behavior"], "factual"),
                     "expected_behavior": case["behavior"], "context": context,
                     "answer": response["answer"]}
    if SOURCE_LABELS:
        grading_input["source_metadata"] = source_metadata(details)
    result = {"id": case["id"], "type": case["type"], "response": response,
              "expected_behavior": case["behavior"],
              "source_labels": SOURCE_LABELS, "frozen_context": bool(MANIFEST.get("frozen_source_run")),
              "rendered_context_tokens": len(rag._get_tokenizer("zh").encode(context, add_special_tokens=False)),
              "sources": details, "retrieval_ms": round(retrieval_ms, 1),
              **evidence, "generation_usage": generation_usage.usage_metadata, "grading_status": "pending"}
    output_path = RUN / f"{case['id']}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        result.update(grade_answer(grader, RUBRIC, grading_input))
        result["grading_status"] = "complete"
    except Exception as exc:
        result.update(grading_status="error", grading_error=type(exc).__name__)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise HTTPException(502, "Grading failed; generated answer saved") from exc
    result["total_with_grading_ms"] = round((time.perf_counter()-started)*1000,1)
    (RUN / f"{case['id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
