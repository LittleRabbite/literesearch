"""Zotero 推送：核验通过的文献写入用户 Zotero 库。"""
from __future__ import annotations

from . import config


def is_configured() -> bool:
    return bool(config.ZOTERO_USER_ID and config.ZOTERO_API_KEY)


def _make_item(p: dict) -> dict:
    venue = p.get("venue", "") or ""
    if "arXiv" in venue and not p.get("doi"):
        item_type = "preprint"
    elif any(k in venue.lower() for k in ("proceedings", "conference", "symposium", "会议")):
        item_type = "conferencePaper"
    else:
        item_type = "journalArticle"

    creators = []
    for name in p.get("authors", [])[:20]:
        name = name.strip()
        if not name:
            continue
        if " " in name:
            last, first = name.rsplit(" ", 1)
            creators.append({"creatorType": "author", "firstName": first, "lastName": last})
        else:
            creators.append({"creatorType": "author", "lastName": name, "fieldMode": 1})

    item = {
        "itemType": item_type,
        "title": p.get("title", ""),
        "creators": creators,
        "date": str(p.get("year", "")),
        "abstractNote": p.get("abstract", "")[:2000],
        "url": p.get("url", ""),
        "tags": [{"tag": "literature-agent"}],
    }
    if p.get("doi"):
        item["DOI"] = p["doi"]
    if item_type == "preprint":
        item["repository"] = "arXiv"
        item["archiveID"] = f"arXiv:{p.get('arxiv_id', '')}"
    else:
        item["publicationTitle"] = venue
    return item


def push_papers(papers: list[dict]) -> dict:
    """批量创建条目，返回 {created, failed, keys}。"""
    if not is_configured():
        raise ValueError("Zotero 未配置：请在 .env 中填写 ZOTERO_USER_ID 和 ZOTERO_API_KEY")
    from pyzotero import zotero
    zot = zotero.Zotero(config.ZOTERO_USER_ID, "user", config.ZOTERO_API_KEY)

    items = [_make_item(p) for p in papers]
    resp = zot.create_items(items)
    created = [it for it in resp.get("success", {}).values()]
    failed = resp.get("failed", {})
    return {"created": len(created), "failed": len(failed),
            "keys": created, "detail": str(failed)[:500] if failed else ""}
