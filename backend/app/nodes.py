"""LangGraph 节点实现：planner → retriever → screening → writer → verifier → bib → pdf → human_review。"""
from __future__ import annotations

import re

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from pydantic import BaseModel

from . import config, pdf_store, tools
from .dedup import PaperDeduplicator
from .llm import get_llm

llm = get_llm()


class SubQueries(BaseModel):
    sub_queries: list[str]


class PaperScore(BaseModel):
    id: int
    score: int
    reason: str


class ScoreList(BaseModel):
    scores: list[PaperScore]


# 打分 rubric：screening 与离线评估（backend/eval）共用，保证实验与生产一致
RUBRIC_TEMPLATE = (
    "按三个维度给每篇论文打 1~5 分（JSON）："
    "1) 与主题相关性 2) 方法代表性 3) 时效性。\n"
    "主题：{topic}\n论文列表：{papers}"
)


# DeepSeek 不支持 response_format=json_schema，改走 function calling 提取结构化输出
llm_structured = llm.with_structured_output(SubQueries, method="function_calling")


def _field(obj, name, default=None):
    """结构化输出结果取值兼容：真实 LLM 返回 pydantic 对象，MockLLM 返回 dict。"""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _emit(event: dict):
    """向 SSE 通道发送自定义事件（仅在 stream 上下文中有效）。"""
    try:
        get_stream_writer()(event)
    except Exception:
        pass


# ---------------------------------------------------------- 1. planner
def planner(state: dict) -> dict:
    _emit({"type": "node_start", "node": "planner"})
    prompt = (
        "你是科研检索规划师。将研究主题拆解为 3~6 个互补的子查询，"
        "覆盖：领域概述、核心方法、方法对比、最新进展"
        f"（{state.get('year_from')}-{state.get('year_to')}）。"
        f"\n主题：{state.get('topic')}"
    )
    result = llm_structured.invoke(prompt)
    sub_queries = (_field(result, "sub_queries") or [])[:6]
    _emit({"type": "progress", "node": "planner", "message": f"生成 {len(sub_queries)} 个子查询"})
    return {"sub_queries": sub_queries, "retry_count": 0}


# -------------------------------------------------------- 2. retriever
def retriever(state: dict) -> dict:
    _emit({"type": "node_start", "node": "retriever"})
    year_from = state.get("year_from", 2020)
    seen: set[str] = set()
    unique: list[dict] = []
    for q in state.get("sub_queries", []):
        for name, fn, kw in (("arXiv", tools.search_arxiv, {"max_results": 15}),
                         ("Semantic Scholar", tools.search_semantic_scholar,
                          {"limit": 15}),
                         ("OpenAlex", tools.search_openalex, {"max_results": 15}),
                         ("ChinaXiv", tools.search_chinaxiv, {"max_results": 15})):
            papers = fn(q, year_from=year_from, **kw)
            _emit({"type": "progress", "node": "retriever",
                   "message": f"{name}「{q}」命中 {len(papers)} 篇"})
            for p in papers:
                key = re.sub(r"\W+", "", p["title"].lower())
                if key and key not in seen:
                    seen.add(key)
                    unique.append(p)
    return {"papers": unique, "retry_count": state.get("retry_count", 0) + 1}


# -------------------------------------------------------- 3. screening
def screening(state: dict) -> dict:
    _emit({"type": "node_start", "node": "screening"})
    _emit({"type": "progress", "node": "screening",
           "message": f"候选 {len(state.get('papers', []))} 篇，语义去重中…"})
    candidates = PaperDeduplicator().run(state.get("papers", []))
    _emit({"type": "progress", "node": "screening",
           "message": f"去重后 {len(candidates)} 篇，LLM 打分中…"})

    topic = state.get("topic", "")
    # 分批打分，控制单次 prompt 长度
    scorer = llm.with_structured_output(ScoreList, method="function_calling")
    for start in range(0, len(candidates), 20):
        batch = candidates[start:start + 20]
        rubric = RUBRIC_TEMPLATE.format(
            topic=topic,
            papers=str([{"id": start + i, "title": p.get("title", ""),
                         "abstract": p.get("abstract", "")[:300]} for i, p in enumerate(batch)]),
        )
        try:
            scores = _field(scorer.invoke(rubric), "scores") or []
        except Exception:
            scores = []
        for s in scores:
            idx = _field(s, "id", -1)
            if isinstance(idx, int) and 0 <= idx < len(candidates):
                candidates[idx]["score"] = _field(s, "score", 0)
                candidates[idx]["score_reason"] = _field(s, "reason", "")

    # 锁定项强制保留，其余按分排序截断
    locked = [p for p in candidates if p.get("locked")]
    rest = sorted((p for p in candidates if not p.get("locked")),
                  key=lambda p: p.get("score", 0), reverse=True)
    top_n = max(state.get("top_n", 15) - len(locked), 1)
    top = locked + rest[:top_n]
    top.sort(key=lambda p: p.get("score", 0), reverse=True)
    _emit({"type": "progress", "node": "screening", "message": f"入选 {len(top)} 篇"})
    return {"screened": top}


# ------------------------------------------------------------ 4. writer
def writer(state: dict) -> dict:
    _emit({"type": "node_start", "node": "writer"})
    screened = state.get("screened", [])
    refs = "\n".join(
        f"[{i}] {p['title']} ({p.get('year', '')}), {', '.join(p.get('authors', [])[:3])}"
        for i, p in enumerate(screened))
    prompt = (
        "基于以下文献撰写结构化文献综述（中文）：\n"
        "1. 发展脉络  2. 主流方法对比（用 Markdown 表格）  3. 常用数据集/benchmark\n"
        "4. research gap 与研究机会\n"
        "硬性要求：每句事实性论断必须用 [n] 标注引用编号；不得引入列表之外的文献。\n\n"
        f"文献列表：\n{refs}"
    )
    chunks: list[str] = []
    for chunk in llm.stream(prompt):
        text = chunk.content
        if text:
            chunks.append(text)
            _emit({"type": "token", "node": "writer", "content": text})
    # 每次重写递增，供 route_verify 限定重写轮次，防止 writer↔verifier 死循环
    return {"survey_draft": "".join(chunks),
            "retry_count": state.get("retry_count", 0) + 1}


# --------------------------------------------------------- 5. verifier
def verifier(state: dict) -> dict:
    _emit({"type": "node_start", "node": "verifier"})
    draft = state.get("survey_draft", "")
    screened = state.get("screened", [])
    cited = {int(m) for m in re.findall(r"\[(\d+)\]", draft) if int(m) < len(screened)}
    report = []
    for idx in sorted(cited):
        p = screened[idx]
        result = tools.verify_reference(p["title"], p.get("authors", [""])[0] if p.get("authors") else "",
                                        p.get("year", 0))
        report.append({"ref": idx, **result})
        _emit({"type": "progress", "node": "verifier",
               "message": f"[{idx}] {'✓' if result['ok'] else '✗'} {result.get('detail', '')}"})
    return {"verify_report": report}


# ----------------------------------------------------- 6. bib_generator
def bib_generator(state: dict) -> dict:
    _emit({"type": "node_start", "node": "bib_generator"})
    entries: list[str] = []
    for i, p in enumerate(state.get("screened", [])):
        bib = tools.fetch_bibtex(doi=p.get("doi", ""), arxiv_id=p.get("arxiv_id", ""),
                                 title=p["title"])
        if bib is None:
            _emit({"type": "progress", "node": "bib_generator",
                   "message": f"[{i}] API 无现成条目，LLM 生成（需人工核对）"})
            bib = llm.invoke(f"根据以下信息生成 BibTeX 条目（key 用 {p.get('arxiv_id') or i}:"
                             f"{p['title'][:30]}）：{p}").content
        entries.append(bib or "")
        _emit({"type": "progress", "node": "bib_generator",
               "message": f"[{i}] {p['title'][:40]}… 完成"})
    return {"bib_entries": entries}


# ------------------------------------------------------- 7. pdf_ingest
def pdf_ingest(state: dict, config: RunnableConfig) -> dict:
    if not state.get("include_pdf"):
        return {"pdf_ingested": 0}
    _emit({"type": "node_start", "node": "pdf_ingest"})
    thread_id = config["configurable"]["thread_id"]
    n = pdf_store.ingest_papers(state.get("screened", []), thread_id, _emit)
    return {"pdf_ingested": n}


# ----------------------------------------------------- 8. human_review
def human_review(state: dict) -> dict:
    """interrupt 挂起点；反馈通过 Command(resume=...) 注入后本节点恢复执行。"""
    from langgraph.types import interrupt

    feedback = interrupt({"node": "human_review", "message": "等待人工审核"})
    action = feedback.get("action", "")
    comment = (feedback.get("comment") or "").strip()
    drop = feedback.get("drop") or []

    screened = list(state.get("screened", []))
    if action == "drop" and drop:
        drop_set = {int(i) for i in drop}
        for i in drop_set:
            if 0 <= i < len(screened):
                screened[i]["locked"] = False
        screened = [p for i, p in enumerate(screened) if i not in drop_set]
        return {"screened": screened, "human_feedback": f"drop: {sorted(drop_set)}"}

    if action == "approved":
        fb = "approved"
    elif action == "refetch":
        fb = f"refetch: {comment}"
    else:
        fb = f"rewrite: {comment}" if comment else "rewrite: 无具体意见，请整体润色"
    return {"human_feedback": fb}


# ------------------------------------------------------------ 条件路由
def route_coverage(state: dict) -> str:
    if len(state.get("screened", [])) >= config.MIN_PAPERS or \
            state.get("retry_count", 0) >= config.MAX_RETRY:
        return "writer"
    return "retriever"


def route_verify(state: dict) -> str:
    report = state.get("verify_report", [])
    if not report or all(r.get("ok") for r in report):
        return "bib_generator"
    if state.get("retry_count", 0) < config.MAX_RETRY:
        return "writer"
    # 重写轮次用尽：带未通过标注继续，由人工审核兜底
    _emit({"type": "progress", "node": "verifier",
           "message": f"{sum(1 for r in report if not r.get('ok'))} 条引用核验未通过，"
                      f"已达重写上限，交由人工审核"})
    return "bib_generator"


def route_feedback(state: dict) -> str:
    fb = state.get("human_feedback") or ""
    if fb == "approved":
        return "__end__"
    if fb.startswith("refetch"):
        return "retriever"
    if fb.startswith("drop"):
        return "writer"
    return "writer"
