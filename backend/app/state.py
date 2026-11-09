"""LangGraph 共享状态定义。"""
import operator
from typing import Annotated, TypedDict


class Paper(TypedDict, total=False):
    title: str
    authors: list[str]
    year: int
    venue: str
    abstract: str
    url: str
    source: str            # arxiv / s2 / crossref
    doi: str
    arxiv_id: str
    citationCount: int
    score: float           # screening 打分（1~5）
    score_reason: str
    locked: bool           # 人工锁定（不会被剔除）
    aliases: list[str]     # 去重合并时其余别名标题
    all_urls: list[str]


class ResearchState(TypedDict, total=False):
    # —— 输入 ——
    topic: str
    year_from: int
    year_to: int
    top_n: int
    include_pdf: bool

    # —— planner 产出 ——
    sub_queries: list[str]

    # —— 中间态 ——
    papers: Annotated[list[Paper], operator.add]   # 多源累加合并
    screened: list[Paper]
    survey_draft: str
    verify_report: list[dict]
    bib_entries: list[str]

    # —— PDF 向量库 ——
    pdf_ingested: int      # 成功入库篇数

    # —— 控制流 ——
    retry_count: int
    human_feedback: str | None
