"""图组装：StateGraph + SqliteSaver 断点续跑 + human_review interrupt。"""
from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from . import config
from .nodes import (bib_generator, human_review, pdf_ingest, planner,
                    retriever, route_coverage, route_feedback,
                    route_verify, screening, verifier, writer)
from .state import ResearchState

_conn = None
_saver = None


def get_checkpointer() -> SqliteSaver:
    global _conn, _saver
    if _saver is None:
        _conn = sqlite3.connect(str(config.CHECKPOINT_DB), check_same_thread=False)
        _saver = SqliteSaver(_conn)
    return _saver


def build_graph():
    g = StateGraph(ResearchState)
    g.add_node("planner", planner)
    g.add_node("retriever", retriever)
    g.add_node("screening", screening)
    g.add_node("writer", writer)
    g.add_node("verifier", verifier)
    g.add_node("bib_generator", bib_generator)
    g.add_node("pdf_ingest", pdf_ingest)
    g.add_node("human_review", human_review)

    g.add_edge(START, "planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "screening")
    g.add_conditional_edges("screening", route_coverage,
                            {"writer": "writer", "retriever": "retriever"})
    g.add_edge("writer", "verifier")
    g.add_conditional_edges("verifier", route_verify,
                            {"bib_generator": "bib_generator", "writer": "writer",
                             "retriever": "retriever"})
    g.add_edge("bib_generator", "pdf_ingest")
    g.add_edge("pdf_ingest", "human_review")
    g.add_conditional_edges("human_review", route_feedback,
                            {"writer": "writer", "retriever": "retriever",
                             END: END})
    return g.compile(checkpointer=get_checkpointer())
