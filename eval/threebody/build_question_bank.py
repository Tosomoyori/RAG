"""Compile source-checked development/holdout annotations without querying models."""
import collections
import copy
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent
DESTINATION = ROOT / "eval/corpora/threebody/question-bank-v1"
PILOT_GROUPS = ["visitors", "physics_uniformity", "farmer_hypothesis", "solar_amplification",
                "ye_criminal_record", "eto_motives", "visitors", "sophon_particle"]


def annotate(case, chunks, sections):
    case = copy.deepcopy(case)
    case["annotation_review"] = "AI source checked; independent human review pending"
    case["evidence"] = []
    for number, quote in enumerate(case["facts"]):
        quotes = [quote] + case.get("alternative_quotes", {}).get(str(number), [])
        for candidate in quotes:
            if not any(candidate in chunk["text"] for chunk in chunks):
                raise ValueError(f"Missing evidence for {case['id']}: {candidate}")
        matches = [c for c in chunks if any(q in c["text"] for q in quotes)]
        case["evidence"].append({"quote": quote, "alternative_quotes": quotes[1:],
                                 "acceptable_indexes": [c["metadata"]["index"] for c in matches],
                                 "locations": sorted({c["metadata"]["section"] for c in matches}),
                                 "chapters": sorted({c["metadata"]["parent_chapter"] for c in matches})})
    if case["behavior"] == "abstain":
        if case["facts"] or not case.get("support_anchors") or not case.get("absence_check"):
            raise ValueError("Abstention requires an explicit bounded absence review")
        check = case["absence_check"]
        targets = [sections[i - 1] for i in check["chapters"]]
        corpus = "\n".join(row["text"] for row in targets)
        for anchor in case["support_anchors"]:
            if anchor not in corpus:
                raise ValueError(f"Missing scoped anchor: {case['id']}")
        check["scope_locations"] = [row["location"] for row in targets]
        check["keyword_occurrences"] = {term: corpus.count(term) for term in check["search_terms"]}
        check["review_status"] = "AI scoped-text review; human confirmation pending"
        case["evidence_applicable"] = False
    elif not case["evidence"]:
        raise ValueError("Answerable questions require evidence groups")
    else:
        case["evidence_applicable"] = True
    return case


def validate_split(cases):
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate case ID")
    if len({c["question"] for c in cases}) != len(cases):
        raise ValueError("Duplicate question")
    groups = {}
    for case in cases:
        previous = groups.setdefault(case["group"], case["split"])
        if previous != case["split"]:
            raise ValueError(f"Knowledge group crosses split: {case['group']}")
    if collections.Counter(c["split"] for c in cases) != {"development": 24, "holdout": 16}:
        raise ValueError("Expected 24 development and 16 holdout cases")


def main():
    module = runpy.run_path(str(DIRECTORY / "prepare_corpus.py"))
    config = module["read_json"](module["CONFIG_PATH"])
    manifest, chunks = module["frozen"](config, "book1")
    sections = module["read_json"](module["LOCAL"] / "book1/sections.json")
    pilot = module["read_json"](DIRECTORY / "pilot_cases.json")
    for case, group in zip(pilot, PILOT_GROUPS):
        case.update(split="development", group=group, previously_evaluated=True)
    extra = module["read_json"](DIRECTORY / "question_bank_extra.json")
    cases = [annotate(c, chunks, sections) for c in pilot + extra]
    validate_split(cases)
    module["write_json"](DESTINATION / "development.json", [c for c in cases if c["split"] == "development"])
    module["write_json"](DESTINATION / "holdout.json", [c for c in cases if c["split"] == "holdout"])
    # Only development IDs are made executable through the Promptfoo development config.
    module["write_json"](DIRECTORY / "development-tests.json", [
        {"description": c["id"], "vars": {"case_id": c["id"]}}
        for c in cases if c["split"] == "development"])
    summary = {
        "version": "question-bank-v1", "scope": "book1", "total": len(cases),
        "split_counts": dict(collections.Counter(c["split"] for c in cases)),
        "type_counts": dict(collections.Counter(c["type"] for c in cases)),
        "behavior_counts": dict(collections.Counter(c["behavior"] for c in cases)),
        "knowledge_groups": {split: sorted({c["group"] for c in cases if c["split"] == split})
                             for split in ("development", "holdout")},
        "previously_evaluated_ids": [c["id"] for c in cases if c.get("previously_evaluated")],
        "holdout_execution": "not run; static source annotation and validation only",
        "review": "AI annotations; independent human review pending",
        "corpus_manifest_sha256": module["file_hash"](ROOT / "eval/corpora/threebody/book1.manifest.json"),
        "files_sha256": {p.relative_to(ROOT).as_posix(): module["file_hash"](p) for p in (
            Path(__file__), DIRECTORY / "pilot_cases.json", DIRECTORY / "question_bank_extra.json",
            DESTINATION / "development.json", DESTINATION / "holdout.json")},
    }
    module["write_json"](DESTINATION / "manifest.json", summary)
    lines = ["# 三体第一册题库 v1", "", "## 状态与边界", "",
             "共 40 题：24 道开发题、16 道保留题。8 道既有试运行题全部保留在开发组。"
             "按知识点组隔离；相关问法不跨组。保留题仅完成静态原文标注与校验，未运行检索模型、生成或裁判。"
             "独立人工复核待完成，当前分数不得作为已人工审核基准。", "",
             "无答案题限定具体章节与缺失字段，记录全文范围、背景锚点及关键词计数。"
             "计数仅辅助核对，不将零命中作为信息不存在的证明。无答案题的证据覆盖指标为不适用，"
             "不能因没有标注答案块而自动记为 100%。", "",
             "多处证据题分别标注每项必要事实；同义位置可以替代，必要事实组之间仍要求全部覆盖。"
             "候选位置尚未穷尽全部可能的同义支持，因此属于开发标注。", "",
             "## 开发题复核表", "",
             "| 题号 | 题型 | 问题 | 参考答案 |", "|---|---|---|---|"]
    for case in cases:
        if case["split"] == "development":
            lines.append(f"| {case['id']} | {case['type']} | {case['question']} | {case['reference']} |")
    lines += ["", "## 保留题", "", "保留题 ID 为 tb-test-01 至 tb-test-16，完整问题、参考答案和证据见 "
              "`eval/corpora/threebody/question-bank-v1/holdout.json`。本报告不展示逐题内容，"
              "避免在开发结果复核中反复接触。人工审阅可单独打开该文件。", ""]
    report = ROOT / "eval/reports/threebody/QUESTION_BANK.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("total", "split_counts", "type_counts", "behavior_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
