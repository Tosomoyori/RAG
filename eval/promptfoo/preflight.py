"""Validate baseline evidence against the active Chroma collections."""
import hashlib
import argparse
import json
import os
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "eval/reports/react/raw")
    parser.add_argument("--cases", nargs="+", default=["cases.json"])
    args = parser.parse_args()
    cases = []
    for name in args.cases:
        cases.extend(json.loads((DIRECTORY / name).read_text(encoding="utf-8")))
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    collections = {}
    for lang in ("zh", "en"):
        collection = client.get_collection(f"rag_{lang}")
        data = collection.get(include=["documents", "metadatas"])
        documents = {}
        for metadata, text in zip(data["metadatas"], data["documents"]):
            index = metadata["index"]
            if index in documents:
                raise ValueError(f"Duplicate chunk index in {lang}: {index}")
            documents[index] = text
        for case in cases:
            if case["vars"]["expected_lang"] != lang:
                continue
            for evidence in case["metadata"]["evidence"]:
                if documents.get(evidence["index"], "").strip() != evidence["text"]:
                    raise ValueError(f"Evidence mismatch: {case['description']} chunk {evidence['index']}")
        serialized = json.dumps(sorted(documents.items()), ensure_ascii=False).encode("utf-8")
        collections[lang] = {
            "chunks": len(documents),
            "content_sha256": hashlib.sha256(serialized).hexdigest(),
        }
    files = ["doc.pdf", "ReAct.pdf", "rag_langchain.py", "app.py",
             "eval/promptfoo/cases.json", "eval/promptfoo/promptfooconfig.yaml",
             "eval/promptfoo/response-checks.cjs", "retrieval.py",
             "eval/promptfoo/acceptance.json", "eval/promptfoo/promptfooconfig.compare.yaml",
             "prompts.json"]
    manifest = {
        "collections": collections,
        "files_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
        "promptfoo": "0.125.1",
        "answer_cache": False,
        "prompt_version": os.getenv("RAG_PROMPT_VERSION", "legacy"),
        "retrieval": {
            "mode": os.getenv("RETRIEVAL_MODE", "language"),
            "neighbors": int(os.getenv("CONTEXT_NEIGHBORS", "1")),
            "max_chunks": int(os.getenv("CONTEXT_MAX_CHUNKS", "10")),
            "max_tokens": int(os.getenv("CONTEXT_MAX_TOKENS", "2560")),
        },
        "semantic_review": "pending",
    }
    destination = args.output_dir
    destination.mkdir(exist_ok=True, parents=True)
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(collections, indent=2))
    print("Evidence preflight passed")


if __name__ == "__main__":
    main()
