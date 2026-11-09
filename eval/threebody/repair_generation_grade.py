"""Retry grading a saved answer after a validation failure; never regenerate."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from eval.threebody.semantic_grading import validate_grade
from eval.threebody.source_context import render_sources, source_metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--variant", choices=("hybrid-n0", "hybrid-n1"), required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    cases = {c["id"]: c for c in json.loads((args.run_dir / "cases.frozen.json").read_text(encoding="utf-8"))}
    case = cases[args.case_id]
    path = args.run_dir / f"{args.case_id}-{args.variant}.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["grading_status"] != "error":
        raise ValueError("Only an errored saved grade can be repaired")
    repair_dir = args.run_dir / "repairs"
    repair_dir.mkdir(exist_ok=True)
    backup = repair_dir / f"{path.stem}.before.json"
    if backup.exists():
        raise ValueError("A repair already exists; inspect it before retrying")
    backup.write_bytes(path.read_bytes())
    payload = {"question": case["question"], "expected_language": "zh", "reference_answer": case["reference"],
               "reference_kind": {"correct_premise": "correct_premise", "abstain": "abstention"}.get(case["behavior"], "factual"),
               "expected_behavior": case["behavior"], "context": render_sources(result["sources"]),
               "source_metadata": source_metadata(result["sources"]), "answer": result["response"]["answer"]}
    rubric = (ROOT / "eval/promptfoo/semantic-rubric.txt").read_text(encoding="utf-8") + (ROOT / "eval/threebody/source-grading-rules.txt").read_text(encoding="utf-8")
    grader = ChatDeepSeek(model="deepseek-chat", temperature=0, timeout=90, max_retries=1).bind(response_format={"type": "json_object"})
    started = time.perf_counter()
    message = grader.invoke([("system", rubric), ("human", json.dumps(payload, ensure_ascii=False))])
    raw = {"raw": message.content, "usage": message.usage_metadata or {}}
    (repair_dir / f"{path.stem}.retry.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    grade = validate_grade(json.loads(message.content))
    if "source_errors" not in grade:
        raise ValueError("Source-aware grade has no source_errors")
    result.update(grade=grade, grading_usage=message.usage_metadata or {}, grading_raw=message.content,
                  grading_status="complete", grading_repaired=True,
                  grading_ms=(time.perf_counter()-started)*1000,
                  first_grading_usage_unavailable=True)
    result.pop("grading_error", None)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Regraded saved answer {args.case_id}/{args.variant}; generation unchanged")


if __name__ == "__main__":
    main()
