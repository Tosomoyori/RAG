"""Verify the frozen profile and authorize a single holdout execution archive."""
import argparse
import json
from pathlib import Path
import runpy
import shutil

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent
LEDGER = ROOT / "eval/reports/threebody/raw/holdout-v1-ledger.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if LEDGER.exists():
        raise ValueError("Holdout v1 already has an execution archive; inspect the ledger instead of rerunning")
    module = runpy.run_path(str(DIRECTORY / "prepare_corpus.py"))
    read, write, digest = module["read_json"], module["write_json"], module["file_hash"]
    profile_path = DIRECTORY / "frozen_profile_v1.json"
    profile = read(profile_path)
    for mapping in (profile["files_sha256"], profile["dataset_sha256"], profile["reranker_files_sha256"]):
        for name, expected in mapping.items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"Frozen identity changed: {name}")
    corpus_manifest, chunks = module["frozen"](read(module["CONFIG_PATH"]), "book1")
    if digest(ROOT / "eval/corpora/threebody/book1.manifest.json") != profile["corpus_manifest_sha256"]:
        raise ValueError("Frozen corpus identity changed")
    import chromadb
    store = chromadb.PersistentClient(path=str(ROOT / profile["index"]["directory"])).get_collection("rag_zh")
    module["verify_store"](store, chunks)
    cases = read(ROOT / "eval/corpora/threebody/question-bank-v1/holdout.json")
    if len(cases) != 16 or any(c["split"] != "holdout" for c in cases):
        raise ValueError("Unexpected holdout partition")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write(args.output_dir / "cases.frozen.json", cases)
    shutil.copyfile(profile_path, args.output_dir / "profile.frozen.json")
    tests = [{"description": c["id"], "vars": {"case_id": c["id"]}} for c in cases]
    write(DIRECTORY / "holdout-tests.json", tests)
    write(args.output_dir / "tests.frozen.json", tests)
    files = [DIRECTORY / name for name in ("prepare_holdout.py", "holdout_server.py", "holdout-tests.json",
             "promptfooconfig.holdout.yaml", "pilot_checks.cjs")]
    write(args.output_dir / "manifest.json", {
        "experiment": "holdout-v1-single-run", "cases": 16, "scope": "book1",
        "profile_sha256": digest(profile_path), "case_snapshot_sha256": digest(args.output_dir / "cases.frozen.json"),
        "files_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in files},
        "grading_validation_retries": 1, "generation_observations_per_case": 1,
        "network_retry_caveat": "SDK retries may occur; no second generated answer is selected",
        "calibration": "source-aware protocol unchanged from frozen development profile",
        "holdout_policy": profile["holdout_policy"], "tuning_after_outputs": False})
    write(LEDGER, {"state": "prepared", "run_directory": str(args.output_dir.resolve()),
                   "profile_sha256": digest(profile_path), "case_ids": [c["id"] for c in cases],
                   "policy": "one generation observation per case; preserve failures; no retuning"})
    print("Frozen profile, corpus, model files and 16 holdout cases verified; single-run ledger created")


if __name__ == "__main__":
    main()
