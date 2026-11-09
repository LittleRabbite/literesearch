"""PDF 下载解析 + 向量化入库（Chroma）。

流程：screened 论文 → 下载 PDF（arXiv 直链）→ PyMuPDF 抽文本 →
分块 → bge-m3 嵌入 → 按会话存入 Chroma 集合，供后续问答/深读。
"""
from __future__ import annotations

from pathlib import Path

import chromadb

from . import config, tools

_embed_model = None


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        config.ensure_hf_mirror()
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(config.EMBED_MODEL)
    return _embed_model


def _chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


def _pdf_url(p: dict) -> str:
    if p.get("arxiv_id"):
        return f"https://arxiv.org/pdf/{p['arxiv_id']}"
    url = p.get("url", "")
    if "arxiv.org" in url:
        return url.replace("/abs/", "/pdf/")
    return ""


def ingest_papers(papers: list[dict], thread_id: str, emit=None) -> int:
    """下载并入库，返回成功篇数。单篇失败不影响其余。"""
    emit = emit or (lambda _e: None)
    session_pdf_dir = config.PDF_DIR / thread_id
    client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    collection = client.get_or_create_collection(f"papers_{thread_id}")

    ok_count = 0
    for i, p in enumerate(papers):
        url = _pdf_url(p)
        if not url:
            emit({"type": "progress", "node": "pdf_ingest",
                  "message": f"[{i}] 非 arXiv 来源，跳过 PDF"})
            continue
        save_path = session_pdf_dir / f"{i}.pdf"
        if not save_path.exists() and not tools.download_pdf(url, save_path):
            emit({"type": "progress", "node": "pdf_ingest",
                  "message": f"[{i}] PDF 下载失败，跳过"})
            continue
        try:
            import fitz  # PyMuPDF
            with fitz.open(save_path) as doc:
                text = "\n".join(page.get_text() for page in doc)
            chunks = _chunk_text(text)
            if not chunks:
                continue
            model = _get_embed_model()
            embs = model.encode(chunks, batch_size=32, normalize_embeddings=True)
            collection.upsert(
                ids=[f"p{i}_c{j}" for j in range(len(chunks))],
                embeddings=[e.tolist() for e in embs],
                documents=chunks,
                metadatas=[{"paper_idx": i, "title": p["title"][:200],
                            "chunk": j} for j in range(len(chunks))],
            )
            ok_count += 1
            emit({"type": "progress", "node": "pdf_ingest",
                  "message": f"[{i}] 已入库 {len(chunks)} 个文本块"})
        except Exception as e:  # noqa: BLE001
            emit({"type": "progress", "node": "pdf_ingest",
                  "message": f"[{i}] 解析失败: {e}"})
    return ok_count
