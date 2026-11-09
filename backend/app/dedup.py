"""候选论文语义去重：bge-m3 嵌入 + 并查集聚类。

模型加载失败时自动降级为标题归一化精确去重，保证流程不中断。
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np

from . import config


def _norm_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s).strip()


# 模型进程级缓存：避免每次 screening 都从磁盘重新加载大模型
_model_cache: dict = {}


def _load_model(name: str):
    if name in _model_cache:
        return _model_cache[name]
    config.ensure_hf_mirror()
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(name)
    _model_cache[name] = model
    return model


class PaperDeduplicator:
    """嵌入余弦相似度 ≥ threshold 的论文并入同一簇，簇内合并为 canonical 记录。"""

    def __init__(self, model_name: str | None = None, threshold: float | None = None):
        self.threshold = threshold or config.DEDUP_THRESHOLD
        self.model = None
        try:
            self.model = _load_model(model_name or config.EMBED_MODEL)
        except Exception as e:  # noqa: BLE001 —— 模型缺失/网络不通时降级
            print(f"[dedup] 嵌入模型加载失败，降级为标题去重: {e}")

    # ---- 嵌入聚类 ----
    def cluster_indices(self, papers: list[dict]) -> list[list[int]]:
        n = len(papers)
        texts = [f"{p.get('title', '')}. {p.get('abstract', '')[:512]}" for p in papers]
        embs = self.model.encode(texts, batch_size=32, normalize_embeddings=True)
        sim = np.asarray(embs) @ np.asarray(embs).T

        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        i_idx, j_idx = np.triu_indices(n, k=1)
        for a, b in zip(i_idx, j_idx):
            if sim[a, b] >= self.threshold:
                ra, rb = find(int(a)), find(int(b))
                if ra != rb:
                    parent[ra] = rb

        groups: dict[int, list[int]] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)
        return list(groups.values())

    # ---- 簇内合并 ----
    @staticmethod
    def merge_group(group: list[dict]) -> dict:
        def quality(p: dict) -> tuple:
            return (bool(p.get("venue") and p["venue"] != "arXiv"),
                    bool(p.get("doi")),
                    p.get("citationCount", 0) or 0)

        canonical = dict(max(group, key=quality))
        canonical["aliases"] = sorted({p["title"] for p in group
                                       if p.get("title") and p["title"] != canonical["title"]})
        canonical["all_urls"] = sorted({p["url"] for p in group if p.get("url")})
        if not canonical.get("abstract"):
            canonical["abstract"] = max((p.get("abstract", "") for p in group), key=len)
        # 合并来源标记
        sources = {p.get("source") for p in group if p.get("source")}
        canonical["source"] = "+".join(sorted(sources)) if sources else canonical.get("source", "")
        return canonical

    # ---- 降级路径：标题精确去重 ----
    @staticmethod
    def _fallback(papers: list[dict]) -> list[list[int]]:
        groups: dict[str, list[int]] = {}
        for i, p in enumerate(papers):
            groups.setdefault(_norm_title(p.get("title", "")), []).append(i)
        return list(groups.values())

    def run(self, papers: list[dict]) -> list[dict]:
        if not papers:
            return []
        if self.model is None or len(papers) == 1:
            groups = self._fallback(papers) if self.model is None else [[0]]
        else:
            groups = self.cluster_indices(papers)
        return [self.merge_group([papers[i] for i in g]) for g in groups]
