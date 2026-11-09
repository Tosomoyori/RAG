"""Compare retrieval candidates on the frozen bilingual development questions."""
import hashlib
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rag_langchain as rag
from retrieval import expand_context, retrieve_candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "eval/reports/react/raw/retrieval-study")
    args = parser.parse_args()
    directory = args.output_dir
    directory.mkdir(exist_ok=False, parents=True)
    results = []
    for lang in ("zh", "en"):
        questions = json.loads((ROOT / f"eval/eval_set_{lang}.json").read_text(encoding="utf-8"))["questions"]
        store = rag.load_store(lang)
        tokenizer = rag._get_tokenizer(lang)
        for question in questions:
            want = set(question["answers"])
            for mode in ("vector", "hybrid"):
                started = time.perf_counter()
                candidates = retrieve_candidates(store, question["q"], rag.RETRIEVE_K, mode)
                scores = rag.rerank_cached(question["q"], [doc.page_content for doc in candidates])
                seeds = [doc for doc, _ in sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)][:rag.RERANK_TOP_N]
                retrieval_ms = (time.perf_counter() - started) * 1000
                candidate_ids = [doc.metadata["index"] for doc in candidates]
                seed_ids = [doc.metadata["index"] for doc in seeds]
                rank = next((rank for rank, index in enumerate(seed_ids, 1) if index in want), 0)
                for neighbors in (0, 1):
                    context = expand_context(store, seeds, tokenizer) if neighbors else seeds
                    context_ids = [doc.metadata["index"] for doc in context]
                    results.append({
                        "id": question["id"], "lang": lang, "type": question["type"],
                        "mode": mode, "neighbors": neighbors, "want": sorted(want),
                        "candidates": candidate_ids, "seeds": seed_ids, "context": context_ids,
                        "candidate_hit": bool(want & set(candidate_ids)),
                        "seed_hit": bool(rank), "seed_mrr": 1 / rank if rank else 0,
                        "context_hit": bool(want & set(context_ids)),
                        "annotated_block_coverage": len(want & set(context_ids)) / len(want),
                        "context_tokens": sum(len(tokenizer.encode(doc.page_content, add_special_tokens=False)) for doc in context),
                        "retrieval_ms": retrieval_ms,
                    })
            print(f"Completed {question['id']}", flush=True)
    summary = []
    for lang in ("zh", "en"):
        for mode in ("vector", "hybrid"):
            for neighbors in (0, 1):
                rows = [row for row in results if (row["lang"], row["mode"], row["neighbors"]) == (lang, mode, neighbors)]
                keys = ("candidate_hit", "seed_hit", "seed_mrr", "context_hit", "annotated_block_coverage", "context_tokens")
                summary.append({"lang": lang, "mode": mode, "neighbors": neighbors,
                                **{key: sum(row[key] for row in rows) / len(rows) for key in keys}})
    files = ["doc.pdf", "ReAct.pdf", "rag_langchain.py", "retrieval.py", "eval/compare_retrieval.py",
             "eval/eval_set_zh.json", "eval/eval_set_en.json"]
    output = {"created_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "rows": results,
              "files_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files}}
    (directory / "retrieval.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
