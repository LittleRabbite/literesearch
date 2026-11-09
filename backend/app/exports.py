"""三种导出：Markdown 综述 / BibTeX / Excel 文献矩阵。"""
from __future__ import annotations

import io
from datetime import date


def _meta_lines(state: dict) -> list[str]:
    return [
        f"- 主题：{state.get('topic', '')}",
        f"- 年份范围：{state.get('year_from', '')}–{state.get('year_to', '')}",
        f"- 入选文献：{len(state.get('screened', []))} 篇",
        f"- 生成日期：{date.today().isoformat()}",
    ]


def to_markdown(state: dict) -> str:
    parts = [f"# 文献综述：{state.get('topic', '')}", "", *_meta_lines(state), "", "---", ""]
    parts.append(state.get("survey_draft", "") or "（综述为空）")
    screened = state.get("screened", [])
    if screened:
        parts += ["", "---", "", "## References", ""]
        for i, p in enumerate(screened):
            authors = ", ".join(p.get("authors", [])[:6])
            doi = f"  \nDOI: {p['doi']}" if p.get("doi") else ""
            parts.append(f"[{i}] {p['title']}. {authors}. {p.get('venue', '')}, "
                         f"{p.get('year', '')}.{doi}  \n{p.get('url', '')}\n")
    return "\n".join(parts)


def to_bibtex(state: dict) -> str:
    return "\n\n".join(b for b in state.get("bib_entries", []) if b)


def to_xlsx(state: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "文献矩阵"

    headers = ["#", "标题", "作者", "年份", "期刊/会议", "来源", "引用数",
               "得分", "打分理由", "DOI", "URL", "核验状态", "锁定"]
    header_fill = PatternFill("solid", fgColor="1F3A5F")
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    verify_map = {r.get("ref"): r for r in state.get("verify_report", [])}
    for i, p in enumerate(state.get("screened", [])):
        v = verify_map.get(i, {})
        row = [
            i + 1, p.get("title", ""), ", ".join(p.get("authors", [])[:6]),
            p.get("year", ""), p.get("venue", ""), p.get("source", ""),
            p.get("citationCount", 0), p.get("score", ""), p.get("score_reason", ""),
            p.get("doi", ""), p.get("url", ""),
            "通过" if v.get("ok") else ("未通过" if v else "未核验"),
            "是" if p.get("locked") else "",
        ]
        for c, val in enumerate(row, 1):
            ws.cell(row=i + 2, column=c, value=val)

    widths = [5, 50, 30, 7, 18, 12, 9, 7, 30, 22, 30, 10, 6]
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"

    # 元信息 sheet
    ws2 = wb.create_sheet("任务信息")
    for r, line in enumerate(_meta_lines(state), 1):
        ws2.cell(row=r, column=1, value=line.strip("- "))
    ws2.column_dimensions["A"].width = 80

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
