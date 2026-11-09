"""screening 离线评估指标（设计文档第二节）：排序质量 + 打分一致性。

全部纯 numpy 实现，不依赖 sklearn/langfuse，本地即可运行。
等级约定：3=必读 2=相关 1=沾边 0=无关。
"""
from __future__ import annotations

import numpy as np


def grade_sequence(ranked_ids: list[str],
                   expected: list[dict]) -> list[int]:
    """把模型排序映射为专家等级序列（未标注的论文记 0）。

    expected: [{"paper_id": "p03", "grade": 3}, ...]
    """
    grade_map = {e["paper_id"]: int(e["grade"]) for e in expected}
    return [grade_map.get(pid, 0) for pid in ranked_ids]


def ndcg_at_k(grades: list[int], k: int) -> float:
    """grades: 按当前排名顺序的 relevance 等级列表。"""
    gains = [(2 ** g - 1) for g in grades[:k]]
    discounts = [1 / np.log2(i + 2) for i in range(len(gains))]
    dcg = sum(g * d for g, d in zip(gains, discounts))
    ideal = sorted(grades, reverse=True)[:k]
    idcg = sum((2 ** g - 1) * d for g, d in zip(ideal, discounts))
    return dcg / idcg if idcg else 0.0


def precision_at_k(grades: list[int], k: int, threshold: int = 2) -> float:
    """Top-k 里 grade >= threshold 的比例（直接决定下游 token 浪费率）。"""
    top = grades[:k]
    if not top:
        return 0.0
    return sum(1 for g in top if g >= threshold) / len(top)


def recall_at_k(ranked_ids: list[str], expected: list[dict], k: int,
                threshold: int = 3) -> float:
    """专家标的必读文献（grade >= threshold）有多少被保留进 Top-k（最重要）。"""
    must_read = {e["paper_id"] for e in expected if int(e["grade"]) >= threshold}
    if not must_read:
        return 0.0
    kept = set(ranked_ids[:k])
    return len(must_read & kept) / len(must_read)


def weighted_kappa(llm_grades: list[int], expert_grades: list[int],
                   min_rating: int = 0, max_rating: int = 5) -> float:
    """二次加权 kappa：LLM 1~5 分与专家 0~3 等级的 agreement。

    两侧量表须对齐后再传入（llm_score_to_grade 已做 1~5 → 0~3 映射）；
    仅有共同评分的样本参与计算。
    """
    pairs = [(l, e) for l, e in zip(llm_grades, expert_grades)
             if l is not None and e is not None]
    n = len(pairs)
    if n == 0:
        return 0.0
    n_cat = max_rating - min_rating + 1
    w = np.zeros((n_cat, n_cat))
    for i in range(n_cat):
        for j in range(n_cat):
            w[i, j] = ((i - j) / (n_cat - 1)) ** 2
    o = np.zeros((n_cat, n_cat))
    for l, e in pairs:
        o[l - min_rating, e - min_rating] += 1
    o /= n
    hist_l = o.sum(axis=1)
    hist_e = o.sum(axis=0)
    e_mat = np.outer(hist_l, hist_e)
    denom = (w * e_mat).sum()
    return 1.0 - (w * o).sum() / denom if denom else 0.0


def llm_score_to_grade(score: int) -> int:
    """LLM 1~5 分 → 专家 0~3 等级（线性缩放）。"""
    return int(round((score - 1) * 3 / 4))


def threshold_sweep(pairs: list[dict], sims: list[float]) -> list[tuple]:
    """去重阈值扫描：对人工标注的 same/different 论文对画 precision/recall。

    pairs:   [{"a": "p01", "b": "p02", "label": "same"|"different"}]
    sims:    与 pairs 等长的嵌入余弦相似度
    返回 [(threshold, precision, recall)]
    """
    labels = [1 if p["label"] == "same" else 0 for p in pairs]
    out = []
    for t in np.arange(0.85, 0.99, 0.01):
        pred = [1 if s >= t else 0 for s in sims]
        tp = sum(1 for p, l in zip(pred, labels) if p and l)
        fp = sum(1 for p, l in zip(pred, labels) if p and not l)
        fn = sum(1 for p, l in zip(pred, labels) if not p and l)
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        out.append((round(float(t), 2), round(precision, 3), round(recall, 3)))
    return out
