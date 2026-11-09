"""Report a single frozen holdout run without changing its configuration or scores."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def token_total(usage):
    if "total_tokens" in usage:
        return usage["total_tokens"]
    return sum(token_total(v) for v in usage.values() if isinstance(v, dict))


def semantic_pass(output):
    grade = output.get("grade")
    return bool(grade) and all(grade[k] == 2 for k in ("correctness", "grounding", "behavior", "language")) and not grade["source_errors"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    manifest = read(run / "manifest.json")
    profile = read(run / "profile.frozen.json")
    assert hashlib.sha256((run / "profile.frozen.json").read_bytes()).hexdigest() == manifest["profile_sha256"]
    assert hashlib.sha256((run / "cases.frozen.json").read_bytes()).hexdigest() == manifest["case_snapshot_sha256"]
    for mapping in (manifest["files_sha256"], profile["files_sha256"], profile["dataset_sha256"], profile["reranker_files_sha256"]):
        for name, expected in mapping.items():
            with (ROOT / name).open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == expected, name
    cases = read(run / "cases.frozen.json")
    assert len(cases) == 16 and all(c["split"] == "holdout" for c in cases)
    pf = read(run / "promptfoo.json")["results"]
    rows = {r["vars"]["case_id"]: r for r in pf["results"]}
    assert set(rows) == {c["id"] for c in cases}
    outputs = {c["id"]: read(run / f"{c['id']}.json") for c in cases}
    assert all((run / f"{c['id']}.started.json").exists() for c in cases)
    generated = [x for x in outputs.values() if x.get("response")]
    complete = [x for x in outputs.values() if x.get("stage") == "complete"]
    answerable = [x for x in outputs.values() if x["evidence_applicable"]]
    abstain = [x for x in complete if x["expected_behavior"] == "abstain"]
    literal_errors = {}
    for x in generated:
        refs = {int(i) for i in re.findall(r"chunk-(\d+)", x["response"]["answer"])}
        actual = {s["metadata"]["index"] for s in x["sources"]}
        if refs-actual:
            literal_errors[x["id"]] = sorted(refs-actual)
        assert x["generation_observations"] == 1 and not x["response"]["cache_hit"]
    prior = read(ROOT / "eval/corpora/threebody/local/original-index-before.json")
    current = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (ROOT / "chroma_db").rglob("*") if p.is_file()}
    assert prior == current
    summary = {
        "cases":16, "generated":len(generated), "complete_grades":len(complete),
        "strict_passes":sum(row["success"] for row in rows.values()),
        "automatic_semantic_passes":sum(semantic_pass(x) for x in complete),
        "answerable":len(answerable), "all_annotated_evidence":sum(x["all_evidence_found"] for x in answerable),
        "abstention":len(abstain), "abstention_semantic_passes":sum(semantic_pass(x) for x in abstain),
        "source_error_cases":[x["id"] for x in complete if x["grade"]["source_errors"]],
        "full_score_counts":{key:sum(x["grade"][key]==2 for x in complete) for key in ("correctness","grounding","behavior","language")},
        "literal_unknown_ids":literal_errors,
        "grading_attempts":sum(len(x.get("grading_attempts",[])) for x in generated),
        "invalid_grading_attempts":sum(bool(a.get("validation_error")) for x in generated for a in x.get("grading_attempts",[])),
        "generation_tokens":sum(token_total(x["generation_usage"]) for x in generated),
        "all_grading_attempt_tokens":sum(token_total(a["usage"]) for x in generated for a in x.get("grading_attempts",[])),
        "original_index_unchanged":True, "profile_unchanged":True, "post_output_tuning":False,
        "review_identity":"auxiliary automatic grades; separate AI source review; no independent human accuracy"}
    (run / "summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    ledger_path = ROOT / "eval/reports/threebody/raw/holdout-v1-ledger.json"
    ledger = read(ledger_path)
    assert Path(ledger["run_directory"]) == run
    ledger.update(state="evaluated", generated_cases=len(generated), complete_grades=len(complete),
                  result_sha256=hashlib.sha256((run / "promptfoo.json").read_bytes()).hexdigest(), post_output_tuning=False)
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding="utf-8")
    lines = ["# 三体第一册冻结配置保留题评测", "", "## 范围与执行边界", "",
             "16道保留题在开发后冻结的profile-v1上各执行一次。题目此前仅静态标注，未用于模型或参数选择。"
             "知识点组与开发组隔离，但同一小说背景及相关题仍存在相关性，不是领域外泛化测试。"
             "参考标注由AI对照原文编制，独立人工复核未完成。", "",
             "固定混合召回20、精排5、同节邻居半径1、最多10块及2560正文token；使用来源标签及legacy模板；"
             "deepseek-chat生成温度0.7、来源辅助裁判温度0。未在查看输出后调参、修订题目或追加标注位置。"
             "单次执行台账及逐题started标记防止重复生成，SDK网络重试不作为第二份答案选择。", "",
             "## 原始结果", "",
             f"已生成 {len(generated)}/16，完成评分 {len(complete)}/16。"
             f"严格规则通过 {summary['strict_passes']}/16，自动语义通过 {summary['automatic_semantic_passes']}/16。"
             f"可回答题找齐已标注证据 {summary['all_annotated_evidence']}/{len(answerable)}，"
             f"无答案题自动语义通过 {summary['abstention_semantic_passes']}/{len(abstain)}。", "",
             "严格规则同时要求语义评分满分和完整已标注证据；语义通过仅要求四维评分满分且无来源错误。"
             "标注位置遗漏不能直接证明回答无支持，自动满分也不等于事实审核完成。", "",
             "| 题号 | 题型 | 证据覆盖 | 正确/依据/行为/语言 | 严格通过 |", "|---|---|---:|---|---|"]
    for c in cases:
        x=outputs[c["id"]];g=x.get("grade",{})
        scores="/".join(str(g.get(k,"error")) for k in ("correctness","grounding","behavior","language"))
        coverage=x["evidence_coverage"]
        lines.append(f"| {c['id']} | {c['type']} | {'N/A' if coverage is None else format(coverage,'.0%')} | {scores} | {rows[c['id']]['success']} |")
    review_path = ROOT / "eval/threebody/holdout_source_review_v1.json"
    if review_path.exists():
        review=read(review_path)
        assert review["run"] == run.name
        lines += ["", "## AI原文来源复核", "", "复核标签与自动数值分开记录，不是独立人工准确率；原分数保持不变。", ""]
        for item in review["cases"]:
            x=outputs[item["id"]]
            for e in item.get("evidence",[]):
                source=next(s for s in x["sources"] if s["metadata"]["index"]==e["index"])
                assert e["quote"] in source["text"]
                if e.get("chapter"):
                    assert source["metadata"]["parent_chapter"]==e["chapter"]
            if item.get("answer_anchor"):
                assert item["answer_anchor"] in x["response"]["answer"]
            corpus = read(ROOT / "eval/corpora/threebody/local/book1/chunks.json")
            for e in item.get("corpus_only_evidence",[]):
                assert e["quote"] in corpus[e["index"]]["text"]
                assert e["index"] not in {s["metadata"]["index"] for s in x["sources"]}
            lines += [f"- **{item['id']} — {item['verdict']}**：{item['finding']}"]
        lines += ["", "复核中查阅的全书证据与实际检索输入分开：tb-test-01的恢复条件在块120，"
                  "但当前输入未包含该块。复核不能把它补算成模型已经看到的依据。"
                  "第15题的参考答案遗漏店名，第9题的附加范围表述不够精确，均仅记录，不据此改题或事后调分。"]
    lines += ["", "## 用量及异常", "",
              f"生成token {summary['generation_tokens']}；全部评分尝试token {summary['all_grading_attempt_tokens']}；"
              f"评分尝试 {summary['grading_attempts']} 次，其中校验失败 {summary['invalid_grading_attempts']} 次。"
              "每次评分的原始响应和用量在校验前保存，无效评分也纳入用量，不重复生成答案。", ""]
    if generated:
        lines += [f"检索耗时中位 {statistics.median(x['retrieval_ms'] for x in generated):.1f} ms；"
                  f"生成耗时中位 {statistics.median(x['generation_ms'] for x in generated):.1f} ms。"
                  "模型已预热，单次观测无置信区间，未核对实时价格。", ""]
    lines += ["## 可支持的结论与限制", "",
              "本结果是固定第一册语料、16道AI标注保留题及一次采样下的表现，不代表全书任意问题准确率。"
              "同模型系列生成与评分的偏差仍存在；不能把开发集与保留集分数直接合并成独立总体成绩。"
              "尚未进行无检索对照、全集规模对照或跨版本重复验证。", "",
              "冻结配置、题库、模型文件和原论文索引身份均校验通过。保留结果查看后没有调参；"
              "后续若调整配置或评分口径，此批题转为开发材料。下一阶段可固定本配置，单独评估第一册到全集的规模变化；"
              "复用这些问题的规模对照属于配对压力测试，不能再当作一批全新的独立测试。", "",
              f"本地完整记录：`{run.relative_to(ROOT).as_posix()}`。", ""]
    (ROOT / "eval/reports/threebody/HOLDOUT.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
