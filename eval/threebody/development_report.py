"""Summarize saved calibration and development runs without invoking models."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def token_total(usage):
    if "total_tokens" in usage:
        return usage["total_tokens"]
    return sum(token_total(value) for value in usage.values() if isinstance(value, dict))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    manifest = read(run / "manifest.json")
    for name, expected in manifest["files_sha256"].items():
        with (ROOT / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Run input changed: {name}")
    bank_manifest = ROOT / "eval/corpora/threebody/question-bank-v1/manifest.json"
    with bank_manifest.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == manifest["question_bank_sha256"]
    bank = read(bank_manifest)
    for name, expected in bank["files_sha256"].items():
        with (ROOT / name).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected
    frozen = read(run / "cases.frozen.json")
    assert len(frozen) == 24 and all(c["split"] == "development" for c in frozen)
    result = read(run / "promptfoo.json")["results"]
    calibration = read(run / "calibration.json")["results"]
    rows = {r["vars"]["case_id"]: r for r in result["results"]}
    assert set(rows) == {c["id"] for c in frozen}
    outputs = {identifier: row["response"]["output"] for identifier, row in rows.items()
               if isinstance(row.get("response", {}).get("output"), dict)}
    old = read(ROOT / "eval/corpora/threebody/local/original-index-before.json")
    current = {}
    for path in (ROOT / "chroma_db").rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                current[path.relative_to(ROOT).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    assert old == current, "Original index changed"
    directory = ROOT / "eval/reports/threebody"
    cal_lines = ["# 三体语义裁判受控检查", "", "## 范围", "",
                 "8 个 AI 编制的受控样例，使用开发事实和人为控制的短上下文。"
                 "期待分数不发送给裁判，实际评分与预设集合由 Promptfoo JavaScript 断言比较。"
                 "未使用保留题，尚无独立人工评分或跨模型复核。", "",
                 f"结果：{calibration['stats']['successes']}/8 符合预期，"
                 f"{calibration['stats']['failures']} 不符合，{calibration['stats']['errors']} 运行错误。", "",
                 "| 样例 | 情况 | 正确/依据/行为/语言 | 符合预期 |", "|---|---|---|---|"]
    for row in calibration["results"]:
        out = row.get("response", {}).get("output", {})
        grade = out.get("grade", {})
        scores = "/".join(str(grade.get(key, "error")) for key in ("correctness", "grounding", "behavior", "language"))
        cal_lines.append(f"| {out.get('id', row['vars']['case_id'])} | {out.get('kind', '')} | {scores} | {'是' if row['success'] else '否'} |")
    cal_lines += ["", "这些检查证明裁判在所选的简单控制样例上符合预设，不证明复杂小说问题评分无偏。"
                  "开发基线中的失败和边界回答仍需逐题复核；同模型系列生成与评分的共同偏差仍然存在。", ""]
    (directory / "CALIBRATION.md").write_text("\n".join(cal_lines), encoding="utf-8")
    valid = [o for o in outputs.values() if o.get("grade")]
    applicable = [o for o in valid if o.get("evidence_applicable")]
    abstentions = [o for o in valid if o.get("expected_behavior") == "abstain"]
    generation_tokens = sum(token_total(o.get("generation_usage", {})) for o in valid)
    grading_tokens = sum(token_total(o.get("grading_usage", {})) for o in valid)
    calibration_tokens = sum(token_total(r.get("response", {}).get("output", {}).get("grading_usage", {})) for r in calibration["results"])
    scores = {key: sum(o["grade"][key] == 2 for o in valid) for key in ("correctness", "grounding", "behavior", "language")}
    stats = result["stats"]
    metrics = {"cases": 24, "stats": {k: stats[k] for k in ("successes", "failures", "errors")},
               "full_score_counts": scores, "answerable_cases_with_grade": len(applicable),
               "all_annotated_evidence_found": sum(o["all_evidence_found"] for o in applicable),
               "abstention_cases_with_grade": len(abstentions),
               "abstention_full_semantic_passes": sum(all(o["grade"][key] == 2 for key in scores) for o in abstentions),
               "generation_tokens": generation_tokens, "grading_tokens": grading_tokens,
               "calibration_grading_tokens": calibration_tokens,
               "original_index_unchanged": True, "holdout_not_run": True}
    (run / "summary.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 三体第一册 24 题开发基线", "", "## 实验范围", "",
             "固定题库 v1 的 24 道开发题，含既有 8 道试运行题及 16 道新增题。"
             "相同知识点的相关问法存在相关性，结果不是 24 个独立知识点的泛化估计。16 道保留题未执行。"
             "题目与参考答案由 AI 对照原文编制，独立人工复核待完成。", "",
             "第一册索引 865 块；当前默认中文混合检索、召回 20、精排 5、同节相邻块半径 1；"
             "上下文最多 10 块、2560 token。legacy 提示词，deepseek-chat 生成温度 0.7，"
             "deepseek-chat 裁判温度 0。答案缓存与 Promptfoo 缓存关闭，嵌入和精排使用进程内缓存。"
             "使用实际检索和生成函数的本地评测适配接口，未验证生产 /ask HTTP 路由。", "",
             "裁判在本轮开始前通过 8 个受控样例检查，详见 [裁判检查](CALIBRATION.md)。", "",
             "## 未修订标注的首轮结果", "",
             f"Promptfoo：{stats['successes']}/24 通过，{stats['failures']} 未通过，{stats['errors']} 运行错误。"
             "本轮不依据输出更改题库、证据标注、提示词或检索参数，以下均为原始基线。", "",
             f"自动裁判给出的正确性满分 {scores['correctness']}/{len(valid)}；依据一致性满分 {scores['grounding']}/{len(valid)}；"
             f"行为满分 {scores['behavior']}/{len(valid)}；语言满分 {scores['language']}/{len(valid)}。",
             f"可回答题中，找齐已标注证据 {metrics['all_annotated_evidence_found']}/{len(applicable)}。"
             f"无答案题四项语义评分全部满分 {metrics['abstention_full_semantic_passes']}/{len(abstentions)}；其证据覆盖不适用。", "",
             "| 题号 | 题型 | 证据覆盖 | 正确/依据/行为/语言 | Promptfoo | 问答耗时 ms |", "|---|---|---:|---|---|---:|"]
    for case in frozen:
        row = rows[case["id"]]
        out = outputs.get(case["id"], {})
        grade = out.get("grade", {})
        score_text = "/".join(str(grade.get(key, "error")) for key in scores)
        coverage = out.get("evidence_coverage")
        lines.append(f"| {case['id']} | {case['type']} | {'N/A' if coverage is None else format(coverage, '.0%')} | {score_text} | {'通过' if row['success'] else '未通过'} | {out.get('response', {}).get('elapsed_ms', 'error')} |")
    lines += ["", "## 未通过样例与自动评分理由", ""]
    for case in frozen:
        row = rows[case["id"]]
        if row["success"]:
            continue
        out = outputs.get(case["id"], {})
        lines += [f"### {case['id']}", "", case["question"], "",
                  f"参考答案：{case['reference']}", "",
                  f"实际回答：{out.get('response', {}).get('answer', 'No saved response')}", "",
                  f"裁判理由：{out.get('grade', {}).get('reason', str(row.get('error', 'Run error')))}", "",
                  "归因需同时核对检索上下文及证据标注，不能单凭关键词命中或裁判总分判定。", ""]
    review_path = ROOT / "eval/threebody/development_review.json"
    if review_path.exists():
        review = read(review_path)
        if review["run"] == run.name:
            lines += ["## 原文与来源元数据复核", "",
                      "以下为 AI 对照原文和章节元数据的复核，尚无独立人工审核。复核未覆盖所有回答的全部附加断言；"
                      "自动满分不能解释为实际事实全部正确。原始评分保留，不作事后调分。", ""]
            for item in review["cases"]:
                saved = outputs[item["id"]]
                source = next(s for s in saved["sources"] if s["metadata"]["index"] == item["source_index"])
                assert source["metadata"]["parent_chapter"] == item["actual_source_chapter"]
                assert item["source_quote"] in source["text"]
                assert item["incorrect_claim"] in saved["response"]["answer"]
                lines += [f"### {item['id']}：同义证据漏标与章节错引同时存在", ""]
                lines += [f"- {finding}" for finding in item["findings"]]
                lines += ["", item["action"], ""]
    if valid:
        lines += ["## 耗时与用量", "",
                  f"问答耗时中位数 {statistics.median(o['response']['elapsed_ms'] for o in valid):.1f} ms；"
                  f"检索耗时中位数 {statistics.median(o['retrieval_ms'] for o in valid):.1f} ms。问答耗时不含裁判。"
                  "进程存在缓存和首次加载差异，此处为本轮观测值，不作为统一冷启动性能结论。", "",
                  f"开发生成 token {generation_tokens}，开发裁判 token {grading_tokens}，校准裁判 token {calibration_tokens}。"
                  "用量取模型响应元数据；HTTP provider 顶层 token=0 不表示免费。未核对实时计价，不报告货币金额。", ""]
    lines += ["## 信息边界与下一阶段", "",
              "本轮没有不检索对照、检索消融、全集对照或重复运行。没有将开发题结果当作独立测试成绩。"
              "证据覆盖基于已标注位置，不保证穷尽其他同义支持；无答案题只对规定范围内的缺失字段成立。", "",
              "原论文索引 31 个文件哈希不变；题库文件身份与运行输入哈希已核验；16 道保留题未运行。"
              "下一阶段先修补章节来源核验并增加错引控制样例，再在开发题上比较检索配置；配置冻结后才运行保留题。", "",
              f"本地原始记录：`{run.relative_to(ROOT).as_posix()}`。包括校准输入、冻结题目、实际上下文、答案、裁判原始输出和用量。", ""]
    (directory / "DEVELOPMENT_BASELINE.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False))


if __name__ == "__main__":
    main()
