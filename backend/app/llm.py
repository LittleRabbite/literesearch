"""LLM 封装：DeepSeek（OpenAI 兼容）+ MOCK 模式。

MOCK_LLM=1 时返回可确定运行的假实现，便于无 key 联调前后端。
"""
from __future__ import annotations

import re

from . import config

_subquery_cache: dict[str, list[str]] = {}


def get_llm():
    """返回 ChatOpenAI（DeepSeek）或 MockLLM。"""
    if config.MOCK_LLM:
        return MockLLM()
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=config.LLM_MODEL,
        temperature=0,
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
    )


# ------------------------------------------------------------------ mock
def _extract(prompt: str, key: str) -> str:
    m = re.search(rf"{key}[：:]\s*(.+)", prompt)
    return m.group(1).strip() if m else ""


def _extract_papers(prompt: str) -> list[dict]:
    """从 screening prompt 的 repr 列表中还原 (id, title, abstract)。"""
    out = []
    for m in re.finditer(
            r"'id': (\d+), 'title': '([^']*)', 'abstract': '([^']*)'", prompt):
        out.append({"id": int(m.group(1)), "title": m.group(2), "abstract": m.group(3)})
    return out


class _StructuredMock:
    def __init__(self, schema_name: str):
        self.schema_name = schema_name

    def invoke(self, prompt: str, *_a, **_kw):
        if self.schema_name == "SubQueries":
            topic = _extract(prompt, "主题") or "给定主题"
            return {"sub_queries": [
                f"{topic} 综述 survey",
                f"{topic} 核心方法 survey",
                f"{topic} 方法对比 comparison",
                f"{topic} 最新进展 2024 2025",
            ]}
        if self.schema_name == "ScoreList":
            papers = _extract_papers(prompt)
            return {"scores": [
                {"id": p["id"], "score": 5 - (p["id"] % 3), "reason": "mock：与主题相关性推断"}
                for p in papers
            ]}
        return {}

    def __call__(self, prompt: str, *_a, **_kw):
        return self.invoke(prompt)


class MockLLM:
    """最小接口兼容：invoke / stream / with_structured_output。"""

    def with_structured_output(self, schema, **_kw):
        return _StructuredMock(getattr(schema, "__name__", str(schema)))

    def invoke(self, prompt, *_a, **_kw):
        if isinstance(prompt, str) and "BibTeX" in prompt:
            return type("R", (), {"content": "@misc{mock2026, title={Mock Entry}, year={2026}}"})()
        if isinstance(prompt, str) and "文献综述" in prompt:
            refs = re.findall(r"\[(\d+)\] ([^\n]+)", prompt)
            lines = ["## 1. 发展脉络", ""]
            for i, _t in refs:
                lines.append(f"近年来相关研究持续推进 [{i}]。")
            lines += ["", "## 4. research gap", "", "现有工作在评测维度上仍有不足 [0]。" if refs else ""]
            return type("R", (), {"content": "\n".join(lines)})()
        return type("R", (), {"content": "mock"})()

    def stream(self, prompt, *_a, **_kw):
        result = self.invoke(prompt).content
        for i in range(0, len(result), 24):
            yield type("C", (), {"content": result[i:i + 24]})()
