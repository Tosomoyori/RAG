"""Verify claim-level development reviews and freeze the selected evaluation profile."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = Path(__file__).resolve().parent
PROFILE = DIRECTORY / "frozen_profile_v1.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_evidence(claim, answer, sources, corpus):
    if claim["answer_anchor"] not in answer:
        raise ValueError("Reviewed claim is not in the saved answer")
    retrieved = {s["metadata"]["index"]: s for s in sources}
    for evidence in claim["evidence"]:
        index = evidence["index"]
        item = corpus[index]
        if evidence["quote"] not in item["text"]:
            raise ValueError(f"Evidence text mismatch: {index}")
        if evidence["scope"] == "retrieved":
            if index not in retrieved or item["text"] != retrieved[index]["text"] or item["metadata"] != retrieved[index]["metadata"]:
                raise ValueError("Corpus-only evidence was used as retrieved evidence")
        elif evidence["scope"] == "corpus_only":
            if index in retrieved:
                raise ValueError("Corpus-only label conflicts with actual context")
        else:
            raise ValueError("Unknown evidence scope")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    args = parser.parse_args()
    helpers = runpy.run_path(str(DIRECTORY / "prepare_corpus.py"))
    corpus_manifest, chunks = helpers["frozen"](read(helpers["CONFIG_PATH"]), "book1")
    corpus = {c["metadata"]["index"]: c for c in chunks}
    bank_dir = ROOT / "eval/corpora/threebody/question-bank-v1"
    bank = read(bank_dir / "manifest.json")
    for name, expected in bank["files_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Question bank changed: {name}")
    review = read(DIRECTORY / "source_review_v1.json")
    protocol = read(DIRECTORY / "review_protocol_v1.json")
    run = ROOT / "eval/reports/threebody/raw" / review["run"]
    run_manifest = read(run / "manifest.json")
    for name, expected in run_manifest["files_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Reviewed experiment code changed: {name}")
    evidence_count = 0
    checked = []
    snapshots = {}
    for case in review["cases"]:
        for variant, annotation in case["variants"].items():
            if annotation["verdict"] not in protocol["verdicts"]:
                raise ValueError("Unregistered review verdict")
            path = run / f"{case['id']}-{variant}.json"
            saved = read(path)
            frozen = read(run / "contexts" / path.name)
            if saved["sources"] != frozen["sources"]:
                raise ValueError("Reviewed context changed")
            for claim in annotation["claims"]:
                validate_evidence(claim, saved["response"]["answer"], saved["sources"], corpus)
                evidence_count += len(claim["evidence"])
            checked.append({"id": case["id"], "variant": variant, "verdict": annotation["verdict"]})
            snapshots[path.relative_to(ROOT).as_posix()] = digest(path)
    previous = read(ROOT / "eval/corpora/threebody/local/original-index-before.json")
    current = {p.relative_to(ROOT).as_posix(): digest(p) for p in (ROOT / "chroma_db").rglob("*") if p.is_file()}
    if previous != current:
        raise ValueError("Original paper index changed")
    retrieval_manifest_path = ROOT / "eval/reports/threebody/raw/retrieval-study-20261105-02/manifest.json"
    reranker_hashes = {name: expected for name, expected in read(retrieval_manifest_path)["files_sha256"].items()
                       if name.startswith("mmarco-mMiniLMv2-L12-H384-v1/")}
    if not reranker_hashes:
        raise ValueError("Reranker model identity is missing")
    for name, expected in reranker_hashes.items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Reranker changed: {name}")
    selection = {
        "version": "threebody-evaluation-profile-v1", "status": "frozen_after_development_before_holdout",
        "scope": "book1", "deployment": "evaluation only; production defaults were not changed",
        "retrieval": {"mode": "hybrid", "candidate_k": 20, "rerank_top_n": 5,
                      "neighbors": 1, "same_section_only": True, "max_chunks": 10, "max_body_tokens": 2560},
        "index": {"directory": corpus_manifest["index_directory"], "collection": "rag_zh",
                  "chunk_tokens": 256, "chunk_overlap_tokens": 40,
                  "embedding_model": "text2vec-base-chinese", "reranker": "mmarco-mMiniLMv2-L12-H384-v1"},
        "generation": {"model": "deepseek-chat", "temperature": 0.7, "prompt": "legacy",
                       "context_format": "source_context.render_sources", "answer_cache": False},
        "auxiliary_grader": {"model": "deepseek-chat", "temperature": 0,
                             "base_rubric": "eval/promptfoo/semantic-rubric.txt",
                             "source_rules": "eval/threebody/source-grading-rules.txt",
                             "status": "auxiliary; known source-attribution and penalty inconsistencies"},
        "review_protocol": "eval/threebody/review_protocol_v1.json",
        "decision_basis": "Evidence completeness and direct support prioritized; no demonstrated overall accuracy gain. Lower-input hybrid-n0 remains an archived candidate.",
        "reporting": "Separate annotated retrieval coverage, auxiliary automatic grades, source-review labels and actual token usage; no independently human-verified accuracy claim.",
        "next_stage": "One frozen holdout evaluation without tuning; then assess corpus scaling separately.",
        "holdout_policy": protocol["post_holdout_rule"],
        "limitations": ["AI-authored annotations and review", "single generation per condition",
                        "same model family generator and grader", "temperature sampling not reproducibly seeded"],
        "dataset_sha256": {str(p.relative_to(ROOT).as_posix()): digest(p) for p in
                           (bank_dir / "manifest.json", bank_dir / "development.json", bank_dir / "holdout.json")},
        "corpus_manifest_sha256": digest(ROOT / "eval/corpora/threebody/book1.manifest.json"),
        "reranker_files_sha256": reranker_hashes,
        "retrieval_study_manifest_sha256": digest(retrieval_manifest_path),
        "files_sha256": {str(p.relative_to(ROOT).as_posix()): digest(p) for p in
                         [DIRECTORY / name for name in ("source_review_v1.json", "review_protocol_v1.json", "review_and_freeze.py",
                          "source_context.py", "semantic_grading.py", "source-grading-rules.txt")] +
                         [ROOT / name for name in ("rag_langchain.py", "retrieval.py", "prompts.json", "eval/promptfoo/semantic-rubric.txt")]},
        "reviewed_output_sha256": snapshots,
    }
    if args.action == "build":
        if PROFILE.exists() and read(PROFILE) != selection:
            raise ValueError("Existing frozen profile differs; create a new version rather than overwrite")
        write(PROFILE, selection)
    elif read(PROFILE) != selection:
        raise ValueError("Frozen profile or dependencies changed")
    result = {"reviewed_cases": 4, "reviewed_answers": len(checked), "verified_evidence_references": evidence_count,
              "verdict_counts": dict(Counter(row["verdict"] for row in checked)),
              "profile_sha256": digest(PROFILE), "review_identity": review["reviewer"],
              "model_api_calls": 0, "holdout_not_run": True, "original_index_unchanged": True,
              "historical_scores_unchanged": True, "checked": checked}
    destination = ROOT / "eval/reports/threebody"
    write(destination / "source-review-verification.json", result)
    lines = ["# 开发争议题原文复核与评测配置冻结", "", "## 复核范围", "",
             "对第6、16、21、22题的两组已保存答案逐项复核，共8份答案。以冻结EPUB正文、原始片段及元数据为依据，"
             "不新增生成或裁判API调用。全文其他位置只用于事实核验和解释检索缺口，不冒充模型实际收到的证据。"
             "本记录是AI原文复核，不是独立人工审核，也不重新给历史答案打数值分数。", "",
             f"逐项验证了{evidence_count}处引文证据引用、答案锚点及上下文可见性。复核标签如下：", "",
             "| 题号 | 关闭扩充 | 开启扩充 | 结论 |", "|---|---|---|---|"]
    for case in review["cases"]:
        a, b = (case["variants"][variant]["verdict"] for variant in ("hybrid-n0", "hybrid-n1"))
        lines.append(f"| {case['id']} | {a} | {b} | {case['conclusion']} |")
    lines += ["", "## 逐项证据", ""]
    for case in review["cases"]:
        lines += [f"### {case['id']}", "", case["question_scope"], ""]
        for variant, annotation in case["variants"].items():
            lines += [f"**{variant}**：{annotation['core_facts']}", ""]
            for claim in annotation["claims"]:
                refs = "; ".join(f"chunk-{e['index']}（{'实际输入' if e['scope']=='retrieved' else '仅全书复核'}）：“{e['quote']}”" for e in claim["evidence"])
                lines += [f"- 答案锚点：{claim['answer_anchor']}。判定：{claim['status']}。{claim['note']} 证据：{refs}"]
            lines.append("")
        if case.get("annotation_issue"):
            lines += [f"标注设计限制：{case['annotation_issue']}", ""]
    lines += ["## 冻结决策", "",
              "选择混合召回20、精排5、同节邻居半径1，上限10块及2560正文token，使用带真实来源标签的上下文。"
              "生成保留legacy模板、deepseek-chat和温度0.7；既有来源裁判保留为辅助分数，另按review-protocol-v1记录事实、"
              "当前支持、归属、引文和范围处理。未修改生产默认行为。", "",
              "选择依据是证据完整性及减少自行推断，不是24/24自动满分；本轮并未证明总体准确率提升。"
              "关闭扩充仍是低输入候选，不再围绕同一开发样例反复优化。原题库及证据位置保持冻结，设计限制单列。", "",
              "配置及依赖哈希已保存于 `eval/threebody/frozen_profile_v1.json`。保留题尚未执行。"
              "下一阶段按此配置一次运行16道保留题，分开报告自动分数和来源复核；查看结果后若调整配置或口径，"
              "该批题转作开发材料，不再作为未见测试。", "",
              "复核标签及证据：`eval/threebody/source_review_v1.json`；统一口径：`eval/threebody/review_protocol_v1.json`。", ""]
    (destination / "SOURCE_REVIEW_AND_FREEZE.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
