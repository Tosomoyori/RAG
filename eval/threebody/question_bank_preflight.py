"""Freeze development annotations after verifying corpus and question-bank identities."""
import argparse
import json
from pathlib import Path
import runpy
import shutil

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-labels", action="store_true")
    parser.add_argument("--frozen-source-run", type=Path)
    args = parser.parse_args()
    module = runpy.run_path(str(DIRECTORY / "prepare_corpus.py"))
    manifest_path = ROOT / "eval/corpora/threebody/question-bank-v1/manifest.json"
    bank = module["read_json"](manifest_path)
    for name, expected in bank["files_sha256"].items():
        if module["file_hash"](ROOT / name) != expected:
            raise ValueError(f"Question-bank identity changed: {name}")
    manifest, chunks = module["frozen"](module["read_json"](module["CONFIG_PATH"]), "book1")
    if bank["corpus_manifest_sha256"] != module["file_hash"](ROOT / "eval/corpora/threebody/book1.manifest.json"):
        raise ValueError("Question-bank corpus identity mismatch")
    import chromadb
    collection = chromadb.PersistentClient(path=str(ROOT / manifest["index_directory"])).get_collection("rag_zh")
    module["verify_store"](collection, chunks)
    cases = module["read_json"](manifest_path.parent / "development.json")
    if any(c["split"] != "development" for c in cases):
        raise ValueError("Development run contains holdout cases")
    tests = module["read_json"](DIRECTORY / "development-tests.json")
    if [t["vars"]["case_id"] for t in tests] != [c["id"] for c in cases]:
        raise ValueError("Promptfoo case IDs differ from frozen development annotations")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    module["write_json"](args.output_dir / "cases.frozen.json", cases)
    calibration_name = "calibration_sources.json" if args.source_labels else "calibration_cases.json"
    module["write_json"](args.output_dir / "calibration.frozen.json", module["read_json"](DIRECTORY / calibration_name))
    baseline_hashes = {}
    if args.frozen_source_run:
        for case in cases:
            source = args.frozen_source_run / f"{case['id']}.json"
            saved = module["read_json"](source)
            if saved["id"] != case["id"] or not saved.get("sources"):
                raise ValueError("Frozen source result mismatch")
            for item in saved["sources"]:
                chunk = chunks[item["metadata"]["index"]]
                if item["text"] != chunk["text"] or item["metadata"] != chunk["metadata"]:
                    raise ValueError("Frozen source does not match corpus")
            target = args.output_dir / "frozen-baseline" / source.name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
            baseline_hashes[source.name] = module["file_hash"](target)
    files = [DIRECTORY / name for name in ("pilot_server.py", "pilot_checks.cjs", "evidence_metrics.py",
             "promptfooconfig.development.yaml", "development-tests.json", "semantic_grading.py",
             "calibration_cases.json", "calibration_checks.cjs", "promptfooconfig.calibration.yaml")]
    if args.source_labels:
        files += [DIRECTORY / name for name in ("source_context.py", "source-grading-rules.txt", "calibration_sources.json",
                  "promptfooconfig.calibration-sources.yaml", "promptfooconfig.regrade-sources.yaml")]
    files += [ROOT / name for name in ("rag_langchain.py", "retrieval.py", "prompts.json", "eval/promptfoo/semantic-rubric.txt")]
    module["write_json"](args.output_dir / "manifest.json", {
        "split": "development", "cases": len(cases), "question_bank_sha256": module["file_hash"](manifest_path),
        "files_sha256": {p.relative_to(ROOT).as_posix(): module["file_hash"](p) for p in files},
        "scope": "book1", "prompt": "legacy", "answer_cache": False,
        "source_labels": args.source_labels, "frozen_source_run": str(args.frozen_source_run) if args.frozen_source_run else None,
        "frozen_baseline_sha256": baseline_hashes,
        "retrieval_mode": "language", "neighbors": 1, "max_chunks": 10, "context_tokens": 2560,
        "generator": "deepseek-chat", "generator_temperature": 0.7,
        "grader": "deepseek-chat", "grader_temperature": 0,
        "promptfoo": "0.125.1", "calibration_reference": "AI-authored controlled cases; human review pending",
        "holdout_cases_included": False, "model_calls_during_preflight": 0})
    print(f"Verified and froze {len(cases)} development cases; holdout excluded")


if __name__ == "__main__":
    main()
