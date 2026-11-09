"""Freeze retrieval inputs and schedule four counterbalanced conditions per case."""
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
    runpy.run_path(str(DIRECTORY / "question_bank_preflight.py"), run_name="__main__")
    helpers = runpy.run_path(str(DIRECTORY / "prepare_corpus.py"))
    read, write, file_hash = helpers["read_json"], helpers["write_json"], helpers["file_hash"]
    cases = read(args.output_dir / "cases.frozen.json")
    conditions = [("vector", 0), ("vector", 1), ("hybrid", 0), ("hybrid", 1)]
    tests = []
    for number, case in enumerate(cases):
        order = conditions[number % 4:] + conditions[:number % 4]
        for mode, neighbors in order:
            tests.append({"description": f"{case['id']}/{mode}-n{neighbors}", "vars": {
                "case_id": case["id"], "variant": f"{mode}-n{neighbors}", "mode": mode, "neighbors": neighbors}})
    write(DIRECTORY / "retrieval-tests.json", tests)
    write(args.output_dir / "tests.frozen.json", tests)
    manifest = read(args.output_dir / "manifest.json")
    manifest.update(experiment="retrieval-only-four-conditions", observations=len(tests),
                    cache_policy="models warmed; clear in-process embed/rerank caches before each observation",
                    order_policy="four-condition rotation across 24 development cases; concurrency 1",
                    retrieve_k=20, rerank_top_n=5, max_chunks=10, max_body_tokens=2560,
                    model_api_calls=0, timing_scope="single observation per case/configuration; OS/Chroma caches remain warm")
    files = [DIRECTORY / name for name in ("retrieval_server.py", "retrieval_checks.cjs", "retrieval-tests.json",
             "promptfooconfig.retrieval.yaml", "prepare_retrieval_study.py", "source_context.py")]
    model = ROOT / "mmarco-mMiniLMv2-L12-H384-v1"
    files += sorted(p for p in model.rglob("*") if p.is_file() and p.suffix in (".json", ".txt", ".bin", ".safetensors"))
    manifest["files_sha256"].update({p.relative_to(ROOT).as_posix(): file_hash(p) for p in files})
    write(args.output_dir / "manifest.json", manifest)
    print(f"Frozen {len(tests)} retrieval observations; holdout excluded")


if __name__ == "__main__":
    main()
