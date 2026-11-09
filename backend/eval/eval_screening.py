"""screening 离线评估主脚本（设计文档第二节、第三节）。

用法（项目根目录）：
    python -m backend.eval.eval_screening                     # 本地模式：跑黄金集，打印指标
    python -m backend.eval.eval_screening --stability         # 附带打分稳定性检查（两次打分一致率）
    python -m backend.eval.eval_screening --sweep             # 去重阈值扫描（需黄金集含 duplicate_pairs 标注）
    python -m backend.eval.eval_screening --langfuse          # 结果上报 Langfuse（需配置 LANGFUSE_*）

黄金集格式见 golden_v1.json；正式使用请替换为专家标注版本。
评估复用生产 screening 的 PaperDeduplicator 与 RUBRIC_TEMPLATE，保证实验与线上同构。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app import config
from backend.app.dedup import PaperDeduplicator
from backend.app.llm import get_llm
from backend.app.nodes import RUBRIC_TEMPLATE, ScoreList
from backend.eval import metrics

GOLDEN_PATH = Path(__file__).parent / "golden_v1.json"

_system_prompt_note = ""


def run_screening(item_input: dict) -> dict:
    """与生产 screening 同构：去重 → rubric 打分 → 排序。

    返回 {"ranked_ids": [...], "llm_scores": {paper_id: 1~5 分}, "merged": 合并后条目数}
    """
    papers = [
        {**p, "id": p.get("id", f"p{i:02d}")}
        for i, p in enumerate(item_input["candidate_pool"])
    ]
    candidates = PaperDeduplicator().run(papers)

    scorer = get_llm().with_structured_output(ScoreList)
    for start in range(0, len(candidates), 20):
        batch = candidates[start:start + 20]
        rubric = RUBRIC_TEMPLATE.format(
            topic=item_input["topic"],
            papers=str([{"id": start + i, "title": p.get("title", ""),
                         "abstract": p.get("abstract", "")[:300]}
                        for i, p in enumerate(batch)]),
        )
        try:
            scores = scorer.invoke(rubric).get("scores", [])
        except Exception:
            scores = []
        for s in scores:
            idx = s["id"]
            if 0 <= idx < len(candidates):
                candidates[idx]["score"] = s["score"]

    ranked = sorted(candidates, key=lambda p: p.get("score", 0), reverse=True)
    return {
        "ranked_ids": [p["id"] for p in ranked],
        "llm_scores": {p["id"]: p.get("score", 0) for p in ranked},
        "merged": len(candidates),
    }


def evaluate_item(item: dict) -> dict:
    """对单个黄金集条目跑 screening 并计算全部指标。"""
    inp = item["input"]
    expected = item["expected_output"]
    result = run_screening(inp)

    graded = metrics.grade_sequence(result["ranked_ids"], expected)
    n = len(result["ranked_ids"])

    # kappa：LLM 1~5 分映射到专家 0~3 量表，仅对已标注论文比较
    exp_map = {e["paper_id"]: int(e["grade"]) for e in expected}
    common = [pid for pid in result["ranked_ids"] if pid in exp_map]
    llm_g = [metrics.llm_score_to_grade(result["llm_scores"][pid]) for pid in common]
    exp_g = [exp_map[pid] for pid in common]

    return {
        "topic": inp["topic"],
        "ndcg@10": round(metrics.ndcg_at_k(graded, 10), 4),
        "precision@15": round(metrics.precision_at_k(graded, min(15, n)), 4),
        "recall@15": round(metrics.recall_at_k(result["ranked_ids"], expected,
                                               min(15, n)), 4),
        "kappa": round(metrics.weighted_kappa(llm_g, exp_g, 0, 3), 4),
        "merged": result["merged"],
        "raw": len(inp["candidate_pool"]),
    }


def stability_check(item: dict, repeats: int = 2) -> float:
    """打分稳定性：同一批论文重复打分，一致论文占比（低 → rubric 需要 anchor 示例）。"""
    from backend.app.nodes import ScoreList
    inp = item["input"]
    papers = [{**p, "id": p.get("id", f"p{i:02d}")}
              for i, p in enumerate(inp["candidate_pool"])]
    scorer = get_llm().with_structured_output(ScoreList)
    rounds = []
    for _ in range(repeats):
        scores = {}
        for start in range(0, len(papers), 20):
            batch = papers[start:start + 20]
            rubric = RUBRIC_TEMPLATE.format(
                topic=inp["topic"],
                papers=str([{"id": start + i, "title": p.get("title", ""),
                             "abstract": p.get("abstract", "")[:300]}
                            for i, p in enumerate(batch)]),
            )
            try:
                for s in scorer.invoke(rubric).get("scores", []):
                    idx = s["id"]
                    if 0 <= idx < len(papers):
                        scores[papers[idx]["id"]] = s["score"]
            except Exception:
                pass
        rounds.append(scores)
    ids = set(rounds[0]) & set(rounds[1])
    if not ids:
        return 0.0
    return sum(1 for i in ids if rounds[0][i] == rounds[1][i]) / len(ids)


def threshold_sweep(golden: dict) -> list[tuple]:
    """对 duplicate_pairs 标注对计算嵌入相似度并扫描 precision/recall。"""
    pairs = golden.get("duplicate_pairs", [])
    if not pairs:
        print("黄金集未包含 duplicate_pairs 标注，跳过阈值扫描")
        return []
    pool: dict[str, dict] = {}
    for item in golden["items"]:
        for p in item["input"]["candidate_pool"]:
            pool[p["id"]] = p
    texts = []
    valid_pairs = []
    for pr in pairs:
        a, b = pool.get(pr["a"]), pool.get(pr["b"])
        if not a or not b:
            continue
        texts.append(f"{a['title']}. {a.get('abstract', '')[:512]}")
        texts.append(f"{b['title']}. {b.get('abstract', '')[:512]}")
        valid_pairs.append(pr)
    dedup = PaperDeduplicator()
    if dedup.model is None:
        print("嵌入模型不可用，跳过阈值扫描")
        return []
    embs = dedup.model.encode(texts, normalize_embeddings=True)
    sims = []
    for k in range(len(valid_pairs)):
        sims.append(float(embs[2 * k] @ embs[2 * k + 1]))
    return metrics.threshold_sweep(valid_pairs, sims)


def push_to_langfuse(golden: dict, run_name: str, reports: list[dict]) -> bool:
    """有凭据时把黄金集与实验结果上报 Langfuse（v4 run_experiment API）。"""
    if not (config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY):
        return False
    try:
        from langfuse import Langfuse
        lf = Langfuse(public_key=config.LANGFUSE_PUBLIC_KEY,
                      secret_key=config.LANGFUSE_SECRET_KEY,
                      host=config.LANGFUSE_HOST)

        lf.create_dataset(name="screening-golden-v1",
                          description="screening 离线评估黄金集")
        for item in golden["items"]:
            lf.create_dataset_item(dataset_name="screening-golden-v1",
                                   input=item["input"],
                                   expected_output=item["expected_output"])

        def task(*, item, **kwargs):
            return run_screening(item["input"])

        def evaluator(*, output, expected_output, **kwargs):
            graded = metrics.grade_sequence(output["ranked_ids"], expected_output)
            n = len(output["ranked_ids"])
            exp_map = {e["paper_id"]: int(e["grade"]) for e in expected_output}
            common = [pid for pid in output["ranked_ids"] if pid in exp_map]
            llm_g = [metrics.llm_score_to_grade(output["llm_scores"][pid]) for pid in common]
            exp_g = [exp_map[pid] for pid in common]
            return [
                {"name": "ndcg@10", "value": metrics.ndcg_at_k(graded, 10)},
                {"name": "precision@15", "value": metrics.precision_at_k(graded, min(15, n))},
                {"name": "recall@15", "value": metrics.recall_at_k(output["ranked_ids"], expected_output, min(15, n))},
                {"name": "kappa", "value": metrics.weighted_kappa(llm_g, exp_g, 0, 3)},
            ]

        lf.run_experiment(name="screening 离线评估", run_name=run_name,
                          data=golden["items"], task=task, evaluators=[evaluator])
        lf.flush()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[langfuse] 上报失败，降级为本地模式: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="screening 离线评估")
    ap.add_argument("--golden", default=str(GOLDEN_PATH), help="黄金集 JSON 路径")
    ap.add_argument("--run-name", default="screening-baseline",
                    help="Langfuse 实验 run_name（换 rubric/模型后改名即可并排对比）")
    ap.add_argument("--stability", action="store_true", help="打分稳定性检查")
    ap.add_argument("--sweep", action="store_true", help="去重阈值扫描")
    ap.add_argument("--langfuse", action="store_true", help="上报 Langfuse")
    args = ap.parse_args()

    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))

    print(f"黄金集: {len(golden['items'])} 个主题 · 模型: {config.LLM_MODEL} · "
          f"嵌入: {config.EMBED_MODEL}\n")
    reports = []
    for item in golden["items"]:
        r = evaluate_item(item)
        reports.append(r)
        print(f"「{r['topic']}」 原始 {r['raw']} → 去重后 {r['merged']}")
        print(f"  nDCG@10={r['ndcg@10']}  Precision@15={r['precision@15']}  "
              f"Recall@15={r['recall@15']}  weighted_kappa={r['kappa']}")

    if args.stability:
        print("\n打分稳定性检查（两次打分一致率）:")
        for item in golden["items"]:
            rate = stability_check(item)
            print(f"  「{item['input']['topic']}」 {rate:.0%}"
                  + ("  ← 一致性偏低，建议给 rubric 加分数档 anchor 示例" if rate < 0.8 else ""))

    if args.sweep:
        print("\n去重阈值扫描（precision 优先，误合危害大于漏合）:")
        rows = threshold_sweep(golden)
        for t, p, r in rows:
            print(f"  threshold={t}  precision={p}  recall={r}")

    if args.langfuse:
        print("\n上报 Langfuse…")
        ok = push_to_langfuse(golden, args.run_name, reports)
        print("  已上报" if ok else "  未配置 LANGFUSE_* 或上报失败，见上方提示")


if __name__ == "__main__":
    main()
