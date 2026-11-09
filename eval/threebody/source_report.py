"""Report the source-aware frozen-context experiment and preserve baseline identity."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def token_total(usage):
    if "total_tokens" in usage:
        return usage["total_tokens"]
    return sum(token_total(v) for v in usage.values() if isinstance(v, dict))


def results(path):
    data = read(path)["results"]
    return data, {r["vars"]["case_id"]: r for r in data["results"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    manifest = read(run / "manifest.json")
    for name, expected in manifest["files_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    bank_manifest = ROOT / "eval/corpora/threebody/question-bank-v1/manifest.json"
    assert hashlib.sha256(bank_manifest.read_bytes()).hexdigest() == manifest["question_bank_sha256"]
    for name, expected in read(bank_manifest)["files_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    baseline_dir = ROOT / manifest["frozen_source_run"]
    for name, expected in manifest["frozen_baseline_sha256"].items():
        assert hashlib.sha256((run / "frozen-baseline" / name).read_bytes()).hexdigest() == expected
        assert hashlib.sha256((baseline_dir / name).read_bytes()).hexdigest() == expected
    before, old_rows = results(baseline_dir / "promptfoo.json")
    calibration, _ = results(run / "calibration.json")
    regraded, regrade_rows = results(run / "regrade.json")
    generated, generated_rows = results(run / "promptfoo.json")
    cases = read(run / "cases.frozen.json")
    assert len(cases) == 24 and all(c["split"] == "development" for c in cases)
    assert set(regrade_rows) == set(generated_rows) == {c["id"] for c in cases}
    rows = []
    counts = {"regraded_source_error_cases": 0, "generated_source_error_cases": 0,
              "regraded_penalty_rule_inconsistencies": 0, "generated_penalty_rule_inconsistencies": 0,
              "generated_unknown_chunk_id_cases": 0}
    tokens = {"generation": 0, "regrading": 0, "grading_new_answers": 0,
              "calibration": sum(token_total(r["response"]["output"].get("grading_usage", {})) for r in calibration["results"])}
    for case in cases:
        identifier = case["id"]
        old = old_rows[identifier]["response"]["output"]
        regrade = regrade_rows[identifier]["response"]["output"]
        new = generated_rows[identifier]["response"]["output"]
        assert old["response"] == regrade["response"]
        assert old["sources"] == regrade["sources"] == new["sources"]
        assert new["frozen_context"] and new["source_labels"]
        assert old["evidence_coverage"] == new["evidence_coverage"]
        cited = {int(i) for i in re.findall(r"chunk-(\d+)", new["response"]["answer"])}
        actual = {source["metadata"]["index"] for source in new["sources"]}
        counts["generated_unknown_chunk_id_cases"] += bool(cited - actual)
        counts["regraded_source_error_cases"] += bool(regrade["grade"]["source_errors"])
        counts["generated_source_error_cases"] += bool(new["grade"]["source_errors"])
        for output, key in ((regrade, "regraded_penalty_rule_inconsistencies"), (new, "generated_penalty_rule_inconsistencies")):
            if output["grade"]["source_errors"] and any(output["grade"][name] == 2 for name in ("correctness", "grounding", "behavior")):
                counts[key] += 1
        tokens["generation"] += token_total(new.get("generation_usage", {}))
        tokens["regrading"] += token_total(regrade.get("grading_usage", {}))
        tokens["grading_new_answers"] += token_total(new.get("grading_usage", {}))
        score = lambda output: "/".join(str(output["grade"][key]) for key in ("correctness", "grounding", "behavior", "language"))
        rows.append({"id": identifier, "old": score(old), "regraded": score(regrade), "new": score(new),
                     "old_source_errors": regrade["grade"]["source_errors"],
                     "new_source_errors": new["grade"]["source_errors"],
                     "new_pass": generated_rows[identifier]["success"]})
    original_index = read(ROOT / "eval/corpora/threebody/local/original-index-before.json")
    current_index = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in (ROOT / "chroma_db").rglob("*") if p.is_file()}
    assert original_index == current_index
    summary = {"calibration": {k: calibration["stats"][k] for k in ("successes", "failures", "errors")},
               "baseline": {k: before["stats"][k] for k in ("successes", "failures", "errors")},
               "regraded_baseline": {k: regraded["stats"][k] for k in ("successes", "failures", "errors")},
               "generated_with_labels": {k: generated["stats"][k] for k in ("successes", "failures", "errors")},
               **counts, "tokens": tokens, "frozen_sources_identical": True,
               "baseline_unchanged": True, "original_index_unchanged": True, "holdout_not_run": True}
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 三体来源标签与来源核验实验", "", "## 实验设计", "",
             "本轮只使用 24 道开发题，16 道保留题未执行。原始基线答案和检索上下文均保持不变，"
             "题库及原标注未修订。所有生成条件复用原基线每题的相同片段、顺序和元数据，不重新检索。", "",
             "新增上下文格式为正文配真实册名、父章节、section 和 chunk-ID，并提示来源归属以标签为准。"
             "生成仍使用 legacy 模板；上下文前导来源说明与标签属于实验处理。裁判新增来源规则与 source_errors 字段。"
             "显式来源声明必须正确，未强制每个答案都添加引用。", "",
             "分三步：12 个受控样例检查来源规则；用新裁判重评原始答案；在同一冻结上下文上加入标签后重新生成并用新裁判评分。"
             "原裁判与新裁判分数不视为同口径直接提升；重评原答案与新答案采用同一新裁判，但仍只有单次生成。", "",
             "## 原始结果", "", "| 条件 | 通过 | 未通过 | 错误 |", "|---|---:|---:|---:|"]
    for title, result in (("来源规则受控检查（12例）", calibration), ("旧答案＋原裁判（24题）", before),
                          ("旧答案＋来源裁判（24题）", regraded), ("来源标签新答案＋来源裁判（24题）", generated)):
        stats = result["stats"]
        lines.append(f"| {title} | {stats['successes']} | {stats['failures']} | {stats['errors']} |")
    lines += ["", f"新裁判在旧答案中标记来源错误 {counts['regraded_source_error_cases']} 题，"
              f"在标签条件新答案中标记来源错误 {counts['generated_source_error_cases']} 题。"
              "这是自动核验结果，不是独立人工审核后的错误总数。", "",
              f"另以确定性规则检查新答案中显式出现的 chunk-ID，引用未提供编号的样例为 "
              f"{counts['generated_unknown_chunk_id_cases']}/24。该检查不强制引用，也不证明被引用片段支持对应断言。", "",
              f"来源扣分规则不一致：旧答案重评 {counts['regraded_penalty_rule_inconsistencies']} 题，"
              f"新答案 {counts['generated_penalty_rule_inconsistencies']} 题。指裁判已列出 source_errors，"
              "却仍将正确性、依据或行为中的某项给2分，与来源规则规定的最多1分不一致。"
              "本报告保留模型原始分数，不事后改写；识别出错误不代表分值执行完全可靠。", "",
              "| 题号 | 原裁判：正确/依据/行为/语言 | 新裁判重评旧答案 | 新裁判评新答案 | 新答案规则通过 |",
              "|---|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['id']} | {row['old']} | {row['regraded']} | {row['new']} | {'是' if row['new_pass'] else '否'} |")
    lines += ["", "## 来源问题与边界回答复核", ""]
    for row in rows:
        if row["old_source_errors"] or row["new_source_errors"] or not row["new_pass"]:
            identifier = row["id"]
            old = old_rows[identifier]["response"]["output"]
            regrade = regrade_rows[identifier]["response"]["output"]
            new = generated_rows[identifier]["response"]["output"]
            lines += [f"### {identifier}", "", f"原答案：{old['response']['answer']}", "",
                      f"来源裁判重评理由：{regrade['grade']['reason']}", "",
                      f"标签条件新答案：{new['response']['answer']}", "",
                      f"新答案裁判理由：{new['grade']['reason']}", "",
                      f"原标注证据覆盖：{new['evidence_coverage']}。该项未因本轮输出而修订。", ""]
    lines += ["## 控制条件与限制", "",
              "逐题验证了原始片段内容、顺序、元数据相同；新旧答案的已标注证据覆盖完全相同，"
              "因此不能将评分变化归因于检索改善。正文片段预算仍为原配置，标签与来源前导说明增加了输入 token；"
              "不是相同总 token 预算的检索对照。来源说明和格式是一起改变的，未单独识别两者效果。", "",
              "当前改变仅位于实验适配服务，没有修改生产 rag_langchain.py 的默认格式或提示词，未替换原论文索引。"
              "同模型系列生成与评分、AI 编制标注、单次采样及开发集相关性仍限制结论；独立人工复核待完成。", "",
              f"本轮用量：生成 {tokens['generation']} token；旧答案重评 {tokens['regrading']}；"
              f"新答案评分 {tokens['grading_new_answers']}；受控检查 {tokens['calibration']}。未核对实时计价。", "",
              "原论文索引 31 个文件哈希、原基线档案及题库文件身份均通过核验。"
              "下一阶段应先确定并冻结评测上下文与来源评分协议，再开展开发集检索配置对照，最后使用保留题。", "",
              f"本地完整记录：`{run.relative_to(ROOT).as_posix()}`。", ""]
    (ROOT / "eval/reports/threebody/SOURCE_ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
