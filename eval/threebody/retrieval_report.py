"""Summarize four retrieval configurations from saved Promptfoo observations."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    manifest = read(run / "manifest.json")
    for name, expected in manifest["files_sha256"].items():
        with (ROOT / name).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected, name
    bank_manifest = ROOT / "eval/corpora/threebody/question-bank-v1/manifest.json"
    assert hashlib.sha256(bank_manifest.read_bytes()).hexdigest() == manifest["question_bank_sha256"]
    bank = read(bank_manifest)
    for name, expected in bank["files_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    cases = read(run / "cases.frozen.json")
    assert len(cases) == 24 and all(c["split"] == "development" for c in cases)
    variants = ("vector-n0", "vector-n1", "hybrid-n0", "hybrid-n1")
    pf = read(run / "promptfoo.json")["results"]
    assert len(pf["results"]) == 96
    schedule = read(run / "tests.frozen.json")
    assert [(r["vars"]["case_id"], r["vars"]["variant"]) for r in pf["results"]] == [
        (t["vars"]["case_id"], t["vars"]["variant"]) for t in schedule]
    observations = {}
    for row in pf["results"]:
        x = row["response"]["output"]
        assert isinstance(x, dict), "Missing retrieval output"
        key = (x["id"], x["variant"])
        assert key not in observations
        observations[key] = x
        assert x["generation_api_calls"] == x["grading_api_calls"] == 0
        assert x["cache_stats"]["embed_hit"] == x["cache_stats"]["rerank_hit"] == 0
        assert x["context_chunks"] <= 10 and x["context_body_tokens"] <= 2560
    summaries = []
    for variant in variants:
        all_rows = [observations[c["id"], variant] for c in cases]
        answerable = [x for x in all_rows if x["context_metrics"]["evidence_applicable"]]
        assert len(answerable) == 22
        summaries.append({
            "variant": variant, "answerable": len(answerable),
            "candidate_group_coverage": statistics.mean(x["candidate_metrics"]["evidence_coverage"] for x in answerable),
            "candidate_all": sum(x["candidate_metrics"]["all_evidence_found"] for x in answerable),
            "seed_all": sum(x["seed_metrics"]["all_evidence_found"] for x in answerable),
            "seed_mrr": statistics.mean(x["seed_mrr"] for x in answerable),
            "context_group_coverage": statistics.mean(x["context_metrics"]["evidence_coverage"] for x in answerable),
            "context_all": sum(x["context_metrics"]["all_evidence_found"] for x in answerable),
            "mean_chunks": statistics.mean(x["context_chunks"] for x in all_rows),
            "mean_body_tokens": statistics.mean(x["context_body_tokens"] for x in all_rows),
            "mean_labeled_tokens": statistics.mean(x["context_labeled_tokens"] for x in all_rows),
            "median_ms": statistics.median(x["retrieval_ms"] for x in all_rows),
            "median_candidate_ms": statistics.median(x["candidate_ms"] for x in all_rows),
            "median_rerank_ms": statistics.median(x["rerank_ms"] for x in all_rows),
            "median_expansion_ms": statistics.median(x["expansion_ms"] for x in all_rows),
        })
    paired = {}
    for mode in ("vector", "hybrid"):
        gained, lost = [], []
        for case in cases:
            a, b = (observations[case["id"], f"{mode}-n{i}"] for i in (0, 1))
            assert a["candidate_ids"] == b["candidate_ids"] and a["seed_ids"] == b["seed_ids"], "Unpaired retrieval rankings"
            if not a["context_metrics"]["evidence_applicable"]:
                continue
            first, second = a["context_metrics"]["all_evidence_found"], b["context_metrics"]["all_evidence_found"]
            if second and not first:
                gained.append(case["id"])
            if first and not second:
                lost.append(case["id"])
        paired[mode] = {"neighbor_gains": gained, "neighbor_losses": lost}
    original = read(ROOT / "eval/corpora/threebody/local/original-index-before.json")
    current = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (ROOT / "chroma_db").rglob("*") if p.is_file()}
    assert current == original
    baseline_path = ROOT / "eval/reports/threebody/raw/development-baseline-20261105-01"
    baseline_reproduced = all(
        observations[c["id"], "hybrid-n1"]["context_ids"] == [s["metadata"]["index"] for s in read(baseline_path / f"{c['id']}.json")["sources"]]
        for c in cases)
    summary = {"observations": 96, "answerable_questions": 22, "abstention_questions": 2,
               "promptfoo_stats": {k: pf["stats"][k] for k in ("successes", "failures", "errors")},
               "default_context_ids_reproduced": baseline_reproduced,
               "summaries": summaries, "paired": paired, "model_api_calls": 0,
               "holdout_not_run": True, "original_index_unchanged": True}
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 三体第一册四组检索对照", "", "## 设计与指标", "",
             "24 道开发题 × 4 组配置，共96次观测。22道可回答题参与证据指标统计；2道无答案题仅核验链路结构，"
             "证据覆盖记为不适用，不用于推断拒答质量。16道保留题未执行。参考标注为AI核对，独立人工复核待完成。", "",
             "四组使用同一索引、embedding、cross-encoder、256-token切块及40-token重叠；候选20、精排5。"
             "开启扩充时按同节相邻半径1补充，最多10块、正文片段token之和2560。关闭扩充保留5个精排种子。"
             "来源标签和前导说明额外计量，不混入正文预算。未调用生成或裁判API，未修改生产默认配置。", "",
             "完整证据=每项必要事实至少命中一个已标注支持位置；事实组覆盖=命中必要事实的比例（逐题平均）。"
             "MRR为精排种子中第一个已标注支持块的倒数名次，不代表所有必要事实均找到。"
             "标注可能遗漏其他同义位置，指标只代表已标注证据覆盖。", "",
             f"Promptfoo原始统计：{pf['stats']['successes']}通过、{pf['stats']['failures']}未通过、{pf['stats']['errors']}运行错误。"
             "其中8次无答案题观测只作结构检查，不能将96次混合条件总通过率解释为问答准确率。", "",
             "## 检索质量", "", "| 配置 | 候选事实组覆盖 | 候选完整证据/22 | 精排完整证据/22 | 精排MRR | 最终事实组覆盖 | 最终完整证据/22 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for s in summaries:
        lines.append(f"| {s['variant']} | {s['candidate_group_coverage']:.1%} | {s['candidate_all']} | {s['seed_all']} | {s['seed_mrr']:.3f} | {s['context_group_coverage']:.1%} | {s['context_all']} |")
    lines += ["", "## 上下文成本与耗时", "", "| 配置 | 平均块数 | 平均正文token | 平均带标签token | 检索总耗时中位ms | 召回/精排/扩充中位ms |",
              "|---|---:|---:|---:|---:|---|"]
    for s in summaries:
        lines.append(f"| {s['variant']} | {s['mean_chunks']:.2f} | {s['mean_body_tokens']:.0f} | {s['mean_labeled_tokens']:.0f} | {s['median_ms']:.1f} | {s['median_candidate_ms']:.1f}/{s['median_rerank_ms']:.1f}/{s['median_expansion_ms']:.1f} |")
    lines += ["", "模型和Chroma查询预热后，每次观测清空本实验进程内的embedding及精排分数缓存。"
              "单并发，四种配置顺序逐题轮换，每组在每个顺序位置出现6次。系统及Chroma底层缓存未清空，"
              "单题单配置仅观测一次，耗时没有置信区间；各阶段中位数之和不必等于总耗时中位数。"
              "当前BM25逐次读取全库并重算词频，这部分计入混合召回耗时。"
              "上表块数和token平均值统计全部24题；token使用中文embedding模型的同一tokenizer计数，"
              "不是生成模型的实际计费token。", "",
              "## 相邻块扩充的逐题变化", ""]
    for mode, change in paired.items():
        lines += [f"- {mode}：新增完整命中 {len(change['neighbor_gains'])} 题（{', '.join(change['neighbor_gains']) or '无'}）；"
                  f"丢失完整命中 {len(change['neighbor_losses'])} 题。"]
    lines += ["", "## 逐题最终证据覆盖", "", "| 开发题 | vector-n0 | vector-n1 | hybrid-n0 | hybrid-n1 |", "|---|---:|---:|---:|---:|"]
    for case in cases:
        values = [observations[case["id"], variant]["context_metrics"]["evidence_coverage"] for variant in variants]
        lines.append("| " + case["id"] + " | " + " | ".join("N/A" if v is None else f"{v:.0%}" for v in values) + " |")
    best = max(s["context_all"] for s in summaries)
    leaders = [s["variant"] for s in summaries if s["context_all"] == best]
    lines += ["", "## 可支持的结论", "",
              f"本轮最高已标注完整证据覆盖为 {best}/22，对应 {', '.join(leaders)}。"
              "不能由此直接推断答案正确率；扩充带来的收益必须同时考虑实际输入token增长。"
              "下一阶段应基于质量与成本选取少量候选进行带来源标签的生成对照，而非自动修改默认配置。", "",
              "建议优先比较hybrid-n0与hybrid-n1：仅改变相邻块扩充，前者输入较少，后者已标注证据覆盖最高。"
              "本轮混合检索从候选21题完整证据到精排18题，再通过扩充恢复到21题；"
              "向量扩充的邻居也可来自候选20块之外，因此最终完整证据数可能超过原候选集合的完整证据数。", "",
              f"当前默认hybrid-n1的24题最终片段ID序列与此前开发基线逐题一致：{baseline_reproduced}。", "",
              "原论文索引31个文件哈希不变；题库身份、四组输入及同模式下的候选和精排排序一致性已核验。"
              "所有失败均保留原标注，不据此追加支持位置。", "",
              f"本地完整轨迹：`{run.relative_to(ROOT).as_posix()}`。", ""]
    (ROOT / "eval/reports/threebody/RETRIEVAL_COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
