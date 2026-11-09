"""Freeze two hybrid-retrieval contexts per development case for generation comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    previous = sys.argv
    try:
        sys.argv = ["question_bank_preflight.py", "--source-labels", "--output-dir", str(args.output_dir)]
        runpy.run_path(str(DIRECTORY / "question_bank_preflight.py"), run_name="__main__")
    finally:
        sys.argv = previous
    module = runpy.run_path(str(DIRECTORY / "prepare_corpus.py"))
    read, write, digest = module["read_json"], module["write_json"], module["file_hash"]
    retrieval_manifest = read(args.retrieval_run / "manifest.json")
    for name, expected in retrieval_manifest["files_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Retrieval input changed: {name}")
    cases = read(args.output_dir / "cases.frozen.json")
    chunks = read(ROOT / "eval/corpora/threebody/local/book1/chunks.json")
    frozen_hashes = {}
    tests = []
    for number, case in enumerate(cases):
        for variant in (("hybrid-n0", "hybrid-n1") if number % 2 == 0 else ("hybrid-n1", "hybrid-n0")):
            name = f"{case['id']}-{variant}.json"
            source = args.retrieval_run / name
            result = read(source)
            if result["id"] != case["id"] or result["variant"] != variant:
                raise ValueError("Frozen context identity mismatch")
            for item in result["sources"]:
                chunk = chunks[item["metadata"]["index"]]
                if item["text"] != chunk["text"] or item["metadata"] != chunk["metadata"]:
                    raise ValueError("Frozen context differs from fixed corpus")
            destination = args.output_dir / "contexts" / name
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)
            frozen_hashes[name] = digest(destination)
            tests.append({"description": f"{case['id']} {variant}", "vars": {"case_id": case["id"], "variant": variant}})
    write(DIRECTORY / "generation-comparison-tests.json", tests)
    write(args.output_dir / "tests.frozen.json", tests)
    calibration_run = ROOT / "eval/reports/threebody/raw/source-labels-20261105-01"
    calibration_manifest = read(calibration_run / "manifest.json")
    for name in ("eval/threebody/semantic_grading.py", "eval/threebody/source_context.py",
                 "eval/threebody/source-grading-rules.txt", "eval/promptfoo/semantic-rubric.txt"):
        if digest(ROOT / name) != calibration_manifest["files_sha256"][name]:
            raise ValueError(f"Source-aware grader protocol changed since calibration: {name}")
    calibration = read(calibration_run / "calibration.json")
    if calibration["results"]["stats"]["successes"] != 12 or calibration["results"]["stats"]["errors"]:
        raise ValueError("Source-aware calibration did not pass")
    shutil.copyfile(calibration_run / "calibration.json", args.output_dir / "calibration.reused.json")
    manifest = read(args.output_dir / "manifest.json")
    manifest.update(experiment="paired-hybrid-generation", observations=48,
                    retrieval_run=str(args.retrieval_run), frozen_contexts_sha256=frozen_hashes,
                    calibration_reused_sha256=digest(args.output_dir / "calibration.reused.json"),
                    calibration_source=str(calibration_run.relative_to(ROOT)),
                    order_policy="alternate variant-first order across development cases; concurrency 1",
                    timing_policy="generation only measured anew; no live retrieval; grading timed separately")
    files = [DIRECTORY / name for name in ("prepare_generation_comparison.py", "generation_comparison_server.py",
             "promptfooconfig.generation-comparison.yaml", "generation-comparison-tests.json")]
    manifest["files_sha256"].update({p.relative_to(ROOT).as_posix(): digest(p) for p in files})
    write(args.output_dir / "manifest.json", manifest)
    print("Frozen 48 generation observations; source-aware calibration reused with identical protocol; holdout excluded")


if __name__ == "__main__":
    main()
