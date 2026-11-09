"""Freeze pilot annotations and verify every evidence quotation against the index."""
import argparse
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    module = runpy.run_path(str(DIRECTORY / "prepare_corpus.py"))
    config = module["read_json"](module["CONFIG_PATH"])
    manifest, chunks = module["frozen"](config, "book1")
    import chromadb
    collection = chromadb.PersistentClient(path=str(ROOT / manifest["index_directory"])).get_collection("rag_zh")
    module["verify_store"](collection, chunks)
    cases = json.loads((DIRECTORY / "pilot_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        case["evidence"] = []
        for number, quote in enumerate(case["facts"]):
            quotes = [quote] + case.get("alternative_quotes", {}).get(str(number), [])
            matches = [c for c in chunks if any(q in c["text"] for q in quotes)]
            for alternative in quotes:
                if not any(alternative in c["text"] for c in chunks):
                    raise ValueError(f"Alternative evidence missing: {case['id']}: {alternative}")
            if not matches:
                raise ValueError(f"Evidence missing: {case['id']}: {quote}")
            case["evidence"].append({"quote": quote, "alternative_quotes": quotes[1:], "acceptable_indexes": [c["metadata"]["index"] for c in matches],
                                     "chapter": matches[0]["metadata"]["parent_chapter"]})
        case["split"] = "development_pilot"
        case["annotation_review"] = "AI checked against source; independent human review pending"
    args.output_dir.mkdir(parents=True, exist_ok=False)
    module["write_json"](args.output_dir / "cases.frozen.json", cases)
    tracked = [DIRECTORY / name for name in ("pilot_cases.json", "pilot_server.py", "pilot_checks.cjs", "promptfooconfig.pilot.yaml")]
    tracked += [ROOT / name for name in ("rag_langchain.py", "retrieval.py", "prompts.json", "package-lock.json", "eval/promptfoo/semantic-rubric.txt")]
    module["write_json"](args.output_dir / "manifest.json", {
        "scope": "book1", "cases": len(cases), "split": "development_pilot",
        "corpus_manifest_sha256": module["file_hash"](ROOT / "eval/corpora/threebody/book1.manifest.json"),
        "files_sha256": {p.relative_to(ROOT).as_posix(): module["file_hash"](p) for p in tracked},
        "prompt_version": "legacy", "retrieval_mode": "language", "neighbors": 1,
        "max_chunks": 10, "max_context_tokens": 2560, "answer_cache": False,
        "promptfoo": "0.125.1", "generator": "deepseek-chat", "generator_temperature": 0.7,
        "grader": "deepseek-chat", "grader_temperature": 0,
        "review": "AI annotations; independent human review pending"})
    print(f"Verified {len(cases)} development cases and all evidence groups")


if __name__ == "__main__":
    main()
