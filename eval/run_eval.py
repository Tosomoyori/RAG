"""检索质量评测：Hit Rate / MRR / 逐题明细。

只评**检索**，不调 LLM。理由：生成质量是另一回事，而且一旦调 LLM，
评测就变慢、变贵、且不可复现——调参时你需要的是一条稳定的基线。

用法：
    python eval/run_eval.py            # 跑两个库
    python eval/run_eval.py zh         # 只跑中文库
    python eval/run_eval.py en -v      # 只跑英文库，并打印逐题明细

三个指标，分别回答不同的问题：
    Recall@K   召回阶段（k=RETRIEVE_K）有没有捞到标准答案？
               —— 没捞到 → 问题在向量检索或切块，跟精排无关
    Hit@N      精排后的 top_n（默认 5）里有没有？
               —— 召回到了但这里没有 → 问题在 cross-encoder 精排
    MRR        第一个命中的名次倒数（1.0 = 永远排第一）
               —— 衡量排序质量，比 Hit 更细腻

对账方式：直接读 Document.metadata["index"]，不做字符串比较。
旧版 evaluate_retrieval 用 `chunk == true_chunk` 全等比较，一旦有两块文本
相同就会认错，而且切块参数一变（块文本变了）就全废。用 index 不会。
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import rag_langchain as r  # noqa: E402


def load_set(lang: str) -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        f"eval_set_{lang}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def eval_lang(lang: str, verbose: bool = False) -> dict:
    data = load_set(lang)
    questions = data["questions"]

    store = r.load_store(lang)
    chunks = r.get_all_chunks_in_order(store)
    n_chunks = len(chunks)

    # 标注对不上当前语料时，先炸出来——这类错误静默时会给出假分数
    for item in questions:
        bad = [a for a in item["answers"] if a >= n_chunks]
        if bad:
            raise ValueError(
                f"{item['id']}: 标准答案块 {bad} 超出当前库的块数 {n_chunks}。"
                f"标注与语料不是同一份（切块参数改过？换过文档？），请重新标注。")

    # 召回阶段和精排阶段分别取一次，才能区分"召回没捞到"和"精排排掉了"
    base = store.as_retriever(search_kwargs={"k": r.RETRIEVE_K})
    retriever = r.make_retriever(store)

    rows = []
    for item in questions:
        q = item["q"]
        want = set(item["answers"])

        recalled = {d.metadata.get("index") for d in base.invoke(q)}
        final = [d.metadata.get("index") for d in retriever.invoke(q)]

        recall_hit = bool(want & recalled)
        rank = next((i for i, idx in enumerate(final, 1) if idx in want), 0)

        rows.append({
            "id": item["id"],
            "type": item.get("type", ""),
            "q": q,
            "want": sorted(want),
            "got": final,
            "recall_hit": recall_hit,
            "hit": rank > 0,
            "rank": rank,
            "mrr": (1.0 / rank) if rank else 0.0,
        })

    n = len(rows)
    summary = {
        "lang": lang,
        "n": n,
        "chunks": n_chunks,
        "retrieve_k": r.RETRIEVE_K,
        "top_n": r.RERANK_TOP_N,
        "recall_rate": sum(x["recall_hit"] for x in rows) / n if n else 0.0,
        "hit_rate": sum(x["hit"] for x in rows) / n if n else 0.0,
        "mrr": sum(x["mrr"] for x in rows) / n if n else 0.0,
        "rows": rows,
    }

    # 按题型分组，方便看出是哪一类问题在拖后腿
    by_type: dict = {}
    for x in rows:
        t = by_type.setdefault(x["type"] or "(未标)", {"n": 0, "hit": 0})
        t["n"] += 1
        t["hit"] += 1 if x["hit"] else 0
    summary["by_type"] = by_type

    if verbose:
        print(f"\n--- {lang} 逐题明细 ---")
        for x in rows:
            if x["hit"]:
                mark = f"命中@第{x['rank']}名"
            elif x["recall_hit"]:
                mark = "召回捞到了但被精排排掉"
            else:
                mark = "召回阶段就没捞到"
            print(f"  [{x['id']}] {mark}")
            print(f"        问：{x['q'][:70]}")
            print(f"        标注块 {x['want']}，实际返回 {x['got']}")
    return summary


def main():
    ap = argparse.ArgumentParser(description="检索质量评测")
    ap.add_argument("lang", nargs="?", default=None, choices=["zh", "en"],
                    help="只跑某个语种；不给则跑两个")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印逐题明细")
    args = ap.parse_args()

    langs = [args.lang] if args.lang else ["zh", "en"]
    results = [eval_lang(l, args.verbose) for l in langs]

    print()
    print("=" * 74)
    print(f"{'库':<6}{'块数':>6}{'题数':>6}{'Recall@K':>11}{'Hit@N':>9}{'MRR':>8}")
    print("-" * 74)
    for s in results:
        print(f"{s['lang']:<6}{s['chunks']:>6}{s['n']:>6}"
              f"{s['recall_rate']:>10.1%}{s['hit_rate']:>9.1%}{s['mrr']:>8.3f}")
    print("=" * 74)
    for s in results:
        print(f"\n[{s['lang']}] 按题型：")
        for t, v in sorted(s["by_type"].items()):
            print(f"   {t:<12} {v['hit']}/{v['n']}")

    # 失败清单单独列出来——这才是调参时要盯的东西
    for s in results:
        bad = [x for x in s["rows"] if not x["hit"]]
        if bad:
            print(f"\n[{s['lang']}] 未命中 {len(bad)} 题：")
            for x in bad:
                why = "精排排掉" if x["recall_hit"] else "召回未捞到"
                print(f"   {x['id']}（{why}）{x['q'][:56]}")


if __name__ == "__main__":
    main()
