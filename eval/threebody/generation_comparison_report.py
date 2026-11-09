"""Summarize paired generation outcomes, annotated evidence and actual token usage."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ("hybrid-n0", "hybrid-n1")
DIMENSIONS = ("correctness", "grounding", "behavior", "language")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def usage_total(usage, field):
    if field in usage:
        return usage[field]
    return sum(usage_total(v, field) for v in usage.values() if isinstance(v, dict))


def semantic_pass(output):
    return all(output["grade"][key] == 2 for key in DIMENSIONS) and not output["grade"]["source_errors"]


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
    assert hashlib.sha256((run / "calibration.reused.json").read_bytes()).hexdigest() == manifest["calibration_reused_sha256"]
    cases = read(run / "cases.frozen.json")
    assert len(cases) == 24 and all(c["split"] == "development" for c in cases)
    for name, expected in manifest["frozen_contexts_sha256"].items():
        assert hashlib.sha256((run / "contexts" / name).read_bytes()).hexdigest() == expected
        assert hashlib.sha256((ROOT / manifest["retrieval_run"] / name).read_bytes()).hexdigest() == expected
    first_pf = read(run / "promptfoo.json")["results"]
    pf = read(run / ("promptfoo-reviewed.json" if (run / "promptfoo-reviewed.json").exists() else "promptfoo.json"))["results"]
    schedule = read(run / "tests.frozen.json")
    assert [(r["vars"]["case_id"], r["vars"]["variant"]) for r in pf["results"]] == [
        (t["vars"]["case_id"], t["vars"]["variant"]) for t in schedule]
    rows = {(r["vars"]["case_id"], r["vars"]["variant"]): r for r in pf["results"]}
    assert len(rows) == 48
    outputs = {}
    repaired = []
    for case in cases:
        for variant in VARIANTS:
            x = rows[case["id"], variant]["response"]["output"]
            assert x["sources"] == read(run / "contexts" / f"{case['id']}-{variant}.json")["sources"]
            assert x["live_retrieval"] is False and x["response"]["cache_hit"] is False
            if x.get("grading_repaired"):
                before = read(run / "repairs" / f"{case['id']}-{variant}.before.json")
                assert x["response"] == before["response"] and x["sources"] == before["sources"]
                assert x["generation_usage"] == before["generation_usage"]
                repaired.append(f"{case['id']}/{variant}")
            outputs[case["id"], variant] = x
    assert len({x["prompt_fingerprint"] for x in outputs.values()}) == 1
    summaries = []
    for variant in VARIANTS:
        group = [outputs[c["id"], variant] for c in cases]
        answerable = [x for x in group if x["evidence_applicable"]]
        abstention = [x for x in group if x["expected_behavior"] == "abstain"]
        summaries.append({"variant": variant, "strict_passes": sum(rows[c["id"], variant]["success"] for c in cases),
                          "semantic_passes": sum(semantic_pass(x) for x in group),
                          "full_scores": {key: sum(x["grade"][key] == 2 for x in group) for key in DIMENSIONS},
                          "all_annotated_evidence": sum(x["all_evidence_found"] for x in answerable),
                          "abstention_semantic_passes": sum(semantic_pass(x) for x in abstention),
                          "source_error_cases": sum(bool(x["grade"]["source_errors"]) for x in group),
                          "penalty_rule_inconsistencies": sum(bool(x["grade"]["source_errors"]) and any(x["grade"][k] == 2 for k in DIMENSIONS[:3]) for x in group),
                          "generation_input_tokens": sum(usage_total(x["generation_usage"], "input_tokens") for x in group),
                          "generation_output_tokens": sum(usage_total(x["generation_usage"], "output_tokens") for x in group),
                          "generation_total_tokens": sum(usage_total(x["generation_usage"], "total_tokens") for x in group),
                          "grading_tokens": sum(usage_total(x["grading_usage"], "total_tokens") for x in group),
                          "median_generation_ms": statistics.median(x["generation_ms"] for x in group)})
    gains, losses = [], []
    for case in cases:
        a, b = (semantic_pass(outputs[case["id"], variant]) for variant in VARIANTS)
        if b and not a:
            gains.append(case["id"])
        if a and not b:
            losses.append(case["id"])
    old = read(ROOT / "eval/corpora/threebody/local/original-index-before.json")
    current = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (ROOT / "chroma_db").rglob("*") if p.is_file()}
    assert current == old
    summary = {"observations": 48, "summaries": summaries, "semantic_neighbor_gains": gains,
               "semantic_neighbor_losses": losses, "holdout_not_run": True,
               "original_index_unchanged": True, "inputs_match_frozen_retrieval": True,
               "promptfoo_stats": {k: pf["stats"][k] for k in ("successes", "failures", "errors")},
               "initial_promptfoo_stats": {k: first_pf["stats"][k] for k in ("successes", "failures", "errors")},
               "repaired_grades": repaired, "invalid_grade_usage_unavailable": len(repaired)}
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 三体混合检索扩充开关的生成对照", "", "## 实验设计", "",
             "24道开发题×2组，共48次生成和评分。输入取自已保存的检索实验，不重新检索；逐项核对片段正文、顺序及元数据。"
             "同一来源标签格式、legacy模板、deepseek-chat生成温度0.7、来源裁判温度0；逐题交错先执行的配置，单并发。"
             "答案缓存及Promptfoo缓存关闭。16道保留题未运行；8道既有试运行题仍在开发组内。", "",
             "来源评分代码、规则及上下文格式与之前12个受控样例检查的哈希一致，复用其校准档案，没有重复调用校准模型。"
             "评分仅接收问题、参考答案、当前片段和当前回答，不接收组别名称或另一组答案。独立人工校准仍待完成。", "",
             "严格通过=四项语义评分满分且找到全部已标注证据；无答案题不要求证据块。"
             "语义通过=正确性、依据、行为、语言均为2且没有来源错误，不要求命中特定标注位置。"
             "两项分开报告，避免标注漏掉同义支持时将证据位置指标误作答案质量。", "",
             f"首次48项Promptfoo运行统计为{first_pf['stats']['successes']}通过、{first_pf['stats']['failures']}未通过。"
             f"其中{len(repaired)}项裁判输出校验失败（{', '.join(repaired) or '无'}），HTTP错误正文被Promptfoo记为断言未通过，"
             "不能把顶层errors=0解释为没有评分异常。仅对已保存答案重试评分，"
             "校验答案、来源和生成用量未变后，再以本地重放检查全部结果；首次档案及异常前记录保留。", "",
             "## 结果", "", "| 条件 | 严格通过/24 | 语义通过/24 | 正确/依据/行为/语言满分题数 | 找齐标注证据/22 | 无答案语义通过/2 | 来源错误题数 |",
             "|---|---:|---:|---|---:|---:|---:|"]
    for s in summaries:
        lines.append(f"| {s['variant']} | {s['strict_passes']} | {s['semantic_passes']} | {'/'.join(str(s['full_scores'][k]) for k in DIMENSIONS)} | {s['all_annotated_evidence']} | {s['abstention_semantic_passes']} | {s['source_error_cases']} |")
    lines += ["", "## 实际生成用量与耗时", "", "| 条件 | 生成输入token总数 | 生成输出token总数 | 生成总token | 裁判token | 生成耗时中位ms |",
              "|---|---:|---:|---:|---:|---:|"]
    for s in summaries:
        lines.append(f"| {s['variant']} | {s['generation_input_tokens']} | {s['generation_output_tokens']} | {s['generation_total_tokens']} | {s['grading_tokens']} | {s['median_generation_ms']:.1f} |")
    lines += ["", "用量取模型响应元数据，区别于检索阶段embedding tokenizer估算；未核对实时价格，不换算货币。"
              "耗时只统计新生成，不含实时检索或裁判；冻结片段的历史检索耗时未伪装为本轮完整问答耗时。", "",
              f"用量表包含成功评分及恢复评分的已记录用量；{len(repaired)}次首次无效评分的响应元数据未保存，"
              "总评分用量因此存在缺口，不将表中合计声称为实际全部费用。", "",
              "## 逐题对照", "", "| 题号 | 关闭扩充语义分数 | 开启扩充语义分数 | 关闭/开启语义通过 |", "|---|---|---|---|"]
    for case in cases:
        a, b = (outputs[case["id"], variant] for variant in VARIANTS)
        score = lambda x: "/".join(str(x["grade"][k]) for k in DIMENSIONS)
        lines.append(f"| {case['id']} | {score(a)} | {score(b)} | {semantic_pass(a)}/{semantic_pass(b)} |")
    lines += ["", f"开启扩充后新增语义通过：{', '.join(gains) or '无'}；原通过变未通过：{', '.join(losses) or '无'}。", "",
              "## 新增证据题及边界回答", ""]
    review_ids = {"tb-dev-06", "tb-dev-16", "tb-dev-22", "tb-dev-21"} | set(gains) | set(losses)
    for case in cases:
        if case["id"] not in review_ids:
            continue
        lines += [f"### {case['id']}", "", case["question"], ""]
        for variant in VARIANTS:
            x = outputs[case["id"], variant]
            lines += [f"**{variant}**", "", x["response"]["answer"], "",
                      f"裁判理由：{x['grade']['reason']}", "",
                      f"已标注证据覆盖：{x['evidence_coverage']}；来源错误：{x['grade']['source_errors']}。", ""]
    review = read(ROOT / "eval/threebody/generation_comparison_review.json")
    if review["run"] == run.name:
        lines += ["## 原文复核与可支持的判断", "",
                  "以下为AI对照实际片段的复核，不是独立人工评分，原始自动分数保持不变。", ""]
        for finding in review["findings"]:
            if "source_index" in finding:
                for variant in VARIANTS:
                    output = outputs[finding["id"], variant]
                    source = next(s for s in output["sources"] if s["metadata"]["index"] == finding["source_index"])
                    assert source["metadata"]["parent_chapter"] == finding["source_chapter"]
                    assert finding["quote"] in source["text"] and finding["quote"] in output["response"]["answer"]
            lines += [f"### {finding['id']}：{finding['topic']}", "", finding["observation"], "", finding["conclusion"], ""]
        lines += [review["decision"], ""]
    lines += ["## 限制", "",
              "每题每配置仅生成一次，没有固定可复现的API采样种子或置信区间，生成差异不能全部归因于扩充。"
              "裁判和生成来自同模型系列，标注与受控期待值由AI编制。未做无检索对照；不能将答对自动解释为检索贡献。"
              "语义通过是自动裁判结果，独立人工复核待完成。来源扣分规则执行不一致的题数按组为："
              + ", ".join(f"{s['variant']}={s['penalty_rule_inconsistencies']}" for s in summaries) + "。", "",
              "题库、原证据位置、检索索引和默认服务配置均未因输出而修改。原论文索引31个文件哈希保持不变，保留题未执行。"
              "开发比较用于质量与用量取舍，不作为独立测试成绩。", "",
              f"本地完整档案：`{run.relative_to(ROOT).as_posix()}`。", ""]
    (ROOT / "eval/reports/threebody/GENERATION_COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
