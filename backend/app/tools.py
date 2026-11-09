"""检索与核验工具：arXiv / Semantic Scholar / OpenAlex / ChinaXiv / CrossRef / BibTeX。

全部为纯函数（不依赖 LangChain @tool 装饰器），节点直接调用，
便于单测与复用；失败时静默降级返回 []，由上层聚合判断覆盖度。
"""
from __future__ import annotations

import re
import time
import unicodedata
from difflib import SequenceMatcher

import feedparser
import requests

from . import config

HEADERS = {"User-Agent": "LiteratureAgent/0.1 (research tool)"}


def _norm_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return s.strip()


# ---------------------------------------------------------------- arXiv
def search_arxiv(query: str, year_from: int = 2020, max_results: int = 15) -> list[dict]:
    """arXiv Atom API 检索，返回 Paper dict 列表。"""
    try:
        resp = requests.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
            },
            timeout=config.HTTP_TIMEOUT,
            headers=HEADERS,
        )
        resp.raise_for_status()
    except Exception:
        return []
    feed = feedparser.parse(resp.text)
    papers: list[dict] = []
    for e in feed.entries:
        year = getattr(e, "published_parsed", None)
        year = year[0] if year else 0
        if year and year < year_from:
            continue
        arxiv_id = getattr(e, "id", "").rsplit("/", 1)[-1]  # http://arxiv.org/abs/2310.12345v1
        doi = ""
        for link in getattr(e, "links", []):
            if link.get("title") == "doi":
                doi = link.get("href", "").replace("http://dx.doi.org/", "")
        papers.append({
            "title": (e.get("title") or "").strip().replace("\n", " "),
            "authors": [a.get("name", "") for a in getattr(e, "authors", [])],
            "year": year,
            "venue": "arXiv",
            "abstract": (e.get("summary") or "").strip().replace("\n", " "),
            "url": getattr(e, "id", ""),
            "source": "arxiv",
            "arxiv_id": arxiv_id.split("v")[0] if arxiv_id else "",
            "doi": doi,
            "citationCount": 0,
        })
    return papers


# ---------------------------------------------------- Semantic Scholar
def search_semantic_scholar(query: str, year_from: int = 2020, limit: int = 15) -> list[dict]:
    """S2 API 检索，带引用数；429 限流时退避重试，最终失败返回 []。"""
    params = {
        "query": query,
        "limit": limit,
        "year": f"{year_from}-",
        "fields": "title,authors,year,abstract,venue,url,citationCount,externalIds",
    }
    headers = dict(HEADERS)
    if config.S2_API_KEY:
        headers["x-api-key"] = config.S2_API_KEY
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params, headers=headers, timeout=config.HTTP_TIMEOUT,
            )
            if resp.status_code == 429:
                time.sleep(2 ** attempt + 1)
                continue
            resp.raise_for_status()
            break
        except Exception:
            return []
    else:
        return []
    papers: list[dict] = []
    for item in resp.json().get("data", []):
        ext = item.get("externalIds") or {}
        authors = item.get("authors") or []
        papers.append({
            "title": (item.get("title") or "").strip(),
            "authors": [a.get("name", "") for a in authors],
            "year": item.get("year") or 0,
            "venue": item.get("venue") or "",
            "abstract": (item.get("abstract") or "").strip(),
            "url": item.get("url") or "",
            "source": "s2",
            "doi": ext.get("DOI", ""),
            "arxiv_id": ext.get("ArXiv", ""),
            "citationCount": item.get("citationCount") or 0,
        })
    return [p for p in papers if p["title"]]


# ---------------------------------------------------------- OpenAlex
def _openalex_abstract(inv: dict) -> str:
    """OpenAlex 的 abstract_inverted_index → 摘要文本。"""
    pos: dict[int, str] = {}
    for word, idxs in (inv or {}).items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def search_openalex(query: str, year_from: int = 2020, max_results: int = 15) -> list[dict]:
    """OpenAlex 检索（免费无 key，带 mailto 进 polite pool），覆盖广、含中文期刊。"""
    try:
        resp = requests.get(
            "https://api.openalex.org/works",
            params={
                "search": query,
                "per-page": max_results,
                "filter": f"from_publication_date:{year_from}-01-01",
                "mailto": "literesearch@example.com",
            },
            timeout=config.HTTP_TIMEOUT, headers=HEADERS,
        )
        resp.raise_for_status()
    except Exception:
        return []
    papers: list[dict] = []
    for it in resp.json().get("results", []):
        loc = it.get("primary_location") or {}
        src = (loc.get("source") or {}).get("display_name") or ""
        # 扫描镜像位置，识别 arXiv 预印本以便 BibTeX 拉取
        arxiv_id = ""
        for l in it.get("locations", []):
            m = re.search(r"arxiv\.org/abs/([\w.]+)", l.get("landing_page_url") or "")
            if m:
                arxiv_id = m.group(1).split("v")[0]
                break
        papers.append({
            "title": (it.get("title") or "").strip(),
            "authors": [a["author"]["display_name"]
                        for a in it.get("authorships", []) if a.get("author")],
            "year": it.get("publication_year") or 0,
            "venue": src,
            "abstract": _openalex_abstract(it.get("abstract_inverted_index"))[:2000],
            "url": loc.get("landing_page_url") or it.get("id") or "",
            "source": "openalex",
            "doi": (it.get("doi") or "").replace("https://doi.org/", ""),
            "arxiv_id": arxiv_id,
            "citationCount": it.get("cited_by_count") or 0,
        })
    return [p for p in papers if p["title"]]


# ---------------------------------------------------------- ChinaXiv
def search_chinaxiv(query: str, year_from: int = 2020, max_results: int = 15) -> list[dict]:
    """ChinaXiv（中科院预印本平台）站内检索。

    该平台搜索接口偶发维护/限流（403「系统正在维护中」页），此时静默返回 []。
    结果列表页不含摘要与作者，abstract 置空；年份从预印本 ID（YYYYMM.NNNNN）推导。
    """
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          "Referer": "https://www.chinaxiv.org/home.htm"}
    html = ""
    try:
        r = requests.post("https://www.chinaxiv.org/user/search.htm",
                          data={"keywordbanner": query}, headers=ua,
                          timeout=config.HTTP_TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and "系统正在维护" not in r.text:
            html = r.text
        if not html:
            r = requests.get("https://www.chinaxiv.org/user/search.htm",
                             params={"field": "all", "value": query}, headers=ua,
                             timeout=config.HTTP_TIMEOUT, allow_redirects=True)
            if r.status_code == 200 and "系统正在维护" not in r.text:
                html = r.text
    except Exception:
        return []
    if not html:
        return []

    papers: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(
            r'<a\s[^>]*href="(/abs/(\d{6})\.\d+)"([^>]*)>(.*?)</a>', html, re.S):
        path, ym, attrs, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        tm = re.search(r'title="([^"]*)"', attrs)
        title = (tm.group(1) if tm else re.sub(r"<[^>]+>", "", inner)).strip()
        year = int(ym[:4])
        if not title or year < year_from or path in seen:
            continue
        seen.add(path)
        papers.append({
            "title": title,
            "authors": [],
            "year": year,
            "venue": "ChinaXiv",
            "abstract": "",
            "url": f"https://www.chinaxiv.org{path}",
            "source": "chinaxiv",
            "chinaxiv_id": path[1:].replace("abs/", ""),
            "doi": "",
            "arxiv_id": "",
            "citationCount": 0,
        })
        if len(papers) >= max_results:
            break
    return papers


# ---------------------------------------------------------- CrossRef
def verify_reference(title: str, first_author: str = "", year: int = 0) -> dict:
    """CrossRef 核对一条引用是否真实存在。

    判定规则（多篇候选任一满足即可）：
    - 强匹配：标题相似度 ≥ 0.90（CS 会议常无官方 DOI，年份放宽）
    - 弱匹配：相似度 ≥ 0.82 且年份差 ≤ 1
    """
    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"query.bibliographic": title, "rows": 5},
            timeout=config.HTTP_TIMEOUT, headers=HEADERS,
        )
        resp.raise_for_status()
        items = resp.json()["message"]["items"]
    except Exception as e:
        return {"ok": False, "matched_title": "", "doi": "", "detail": f"crossref 不可达: {e}"}
    if not items:
        return {"ok": False, "matched_title": "", "doi": "", "detail": "CrossRef 无匹配记录"}

    def _year_of(it: dict) -> int | None:
        for k in ("published-print", "published-online", "issued"):
            parts = (it.get(k) or {}).get("date-parts", [[None]])
            if parts and parts[0] and parts[0][0]:
                return parts[0][0]
        return None

    best, best_ratio = None, 0.0
    for it in items:
        ct = (it.get("title") or [""])[0]
        ratio = SequenceMatcher(None, _norm_title(title), _norm_title(ct)).ratio()
        if ratio > best_ratio:
            best, best_ratio = it, ratio
        year_ok = year and _year_of(it) and abs(_year_of(it) - year) <= 1
        if ratio >= 0.90 or (ratio >= 0.82 and year_ok):
            matched_year = _year_of(it)
            detail = f"相似度 {ratio:.2f}" + (f"，年份 {matched_year}" if matched_year else "")
            return {"ok": True, "matched_title": ct, "doi": it.get("DOI", ""),
                    "matched_year": matched_year, "ratio": round(ratio, 2),
                    "detail": detail}

    matched_year = _year_of(best)
    detail = f"相似度 {best_ratio:.2f}，低于阈值"
    if year and matched_year and abs(matched_year - year) > 1:
        detail += f"，年份不符（核验 {matched_year} vs 引用 {year}）"
    return {"ok": False, "matched_title": (best.get("title") or [""])[0],
            "doi": best.get("DOI", ""), "matched_year": matched_year,
            "ratio": round(best_ratio, 2), "detail": detail}


# ------------------------------------------------------------ BibTeX
def fetch_bibtex(doi: str = "", arxiv_id: str = "", title: str = "") -> str | None:
    """优先拉现成 BibTeX：arXiv → DOI content negotiation → DBLP，避免 LLM 拼写幻觉。"""
    if arxiv_id:
        try:
            r = requests.get(f"https://arxiv.org/bibtex/{arxiv_id}",
                             timeout=config.HTTP_TIMEOUT, headers=HEADERS)
            if r.status_code == 200 and r.text.strip().startswith("@"):
                return r.text.strip()
        except Exception:
            pass
    if doi:
        try:
            r = requests.get(f"https://doi.org/{doi}",
                             headers={"Accept": "application/x-bibtex", **HEADERS},
                             timeout=config.HTTP_TIMEOUT, allow_redirects=True)
            if r.status_code == 200 and r.text.strip().startswith("@"):
                return r.text.strip()
        except Exception:
            pass
    if title:
        try:
            r = requests.get("https://dblp.org/search/publ/api",
                             params={"q": title, "format": "bibtex", "h": 1},
                             timeout=config.HTTP_TIMEOUT, headers=HEADERS)
            if r.status_code == 200 and "@inproceedings" in r.text or "@article" in r.text:
                return r.text.strip()
        except Exception:
            pass
    return None


# -------------------------------------------------------------- PDF
def download_pdf(url: str, save_path) -> bool:
    """下载论文 PDF（限 arXiv 直链），成功返回 True。"""
    if "arxiv.org" in url and "/pdf/" not in url and "/abs/" in url:
        url = url.replace("/abs/", "/pdf/")
    try:
        r = requests.get(url, timeout=60, headers=HEADERS, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        if r.status_code == 200 and ("pdf" in ct or r.content[:4] == b"%PDF"):
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False
