"""
08_export_report_pdf.py
=========================
Renders `report/ENGINEERING_REPORT.md` to a polished PDF at
`submission/ENGINEERING_REPORT.pdf`, for the hackathon's "pdf or zip only"
upload requirement.

This is a small purpose-built Markdown -> ReportLab converter (headings,
tables, bullet/numbered lists, bold/inline-code spans, images, horizontal
rules, fenced code blocks) rather than a generic HTML renderer - it only
needs to handle the constructs actually used in our one report file, and
keeping it dependency-light (reportlab + markdown's tiny inline regexes only)
avoids pulling in a headless-browser PDF toolchain that may not be available
in the judging environment.

Requires: pip install reportlab markdown   (NOT needed for the core pipeline;
only for this optional PDF export.)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    HRFlowable, ListFlowable, ListItem, PageBreak, KeepTogether,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT_MD = ROOT / "report" / "ENGINEERING_REPORT.md"
OUT_DIR = ROOT / "submission"
OUT_PDF = OUT_DIR / "ENGINEERING_REPORT.pdf"

INK = colors.HexColor("#111827")
DIM = colors.HexColor("#6b7280")
BLUE = colors.HexColor("#2563eb")
LINE = colors.HexColor("#e5e7eb")
HEADFILL = colors.HexColor("#f3f4f6")

styles = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=styles["Title"], fontSize=20, textColor=INK, spaceAfter=4),
    "subtitle": ParagraphStyle("subtitle", parent=styles["Normal"], fontSize=11, textColor=DIM, spaceAfter=18),
    "h2": ParagraphStyle("h2", parent=styles["Heading1"], fontSize=15, textColor=INK,
                          spaceBefore=18, spaceAfter=8, borderColor=LINE),
    "h3": ParagraphStyle("h3", parent=styles["Heading2"], fontSize=12.5, textColor=BLUE,
                          spaceBefore=12, spaceAfter=6),
    "body": ParagraphStyle("body", parent=styles["Normal"], fontSize=9.7, leading=14,
                            textColor=INK, spaceAfter=6),
    "bullet": ParagraphStyle("bullet", parent=styles["Normal"], fontSize=9.7, leading=14, textColor=INK),
    "cell": ParagraphStyle("cell", parent=styles["Normal"], fontSize=8.3, leading=11, textColor=INK),
    "cellhead": ParagraphStyle("cellhead", parent=styles["Normal"], fontSize=8.3, leading=11,
                                textColor=colors.white, fontName="Helvetica-Bold"),
    "code": ParagraphStyle("code", parent=styles["Normal"], fontName="Courier", fontSize=8.2,
                            leading=11, textColor=INK, backColor=HEADFILL,
                            borderPadding=8, spaceAfter=8),
    "quote": ParagraphStyle("quote", parent=styles["Normal"], fontSize=9.4, leading=14,
                            textColor=DIM, leftIndent=18, rightIndent=10,
                            spaceBefore=4, spaceAfter=8, borderPadding=6,
                            fontName="Helvetica-Oblique"),
    "caption": ParagraphStyle("caption", parent=styles["Normal"], fontSize=8.3, textColor=DIM,
                               alignment=1, spaceAfter=12),
}


def inline(text: str) -> str:
    """Convert a subset of inline Markdown to ReportLab's mini-XML markup."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # restore markup we want to allow through after escaping
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8.3" color="#b91c1c">\1</font>', text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links -> plain text (local anchors)
    return text


def parse_table(lines: list[str]) -> Table:
    rows = [l.strip().strip("|").split("|") for l in lines if not re.match(r"^\s*\|?\s*-+\s*\|", l)]
    rows = [[c.strip() for c in row] for row in rows]
    data = []
    for ri, row in enumerate(rows):
        style = STYLES["cellhead"] if ri == 0 else STYLES["cell"]
        data.append([Paragraph(inline(c), style) for c in row])
    ncols = len(data[0])
    avail_width = 6.6 * inch
    col_w = avail_width / ncols
    t = Table(data, colWidths=[col_w] * ncols, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build_story(md_text: str) -> list:
    story = []
    lines = md_text.split("\n")
    i = 0
    first_h1 = True
    while i < len(lines):
        line = lines[i]

        if line.startswith("# "):
            if first_h1:
                story.append(Paragraph(inline(line[2:]), STYLES["title"]))
                first_h1 = False
            else:
                story.append(Paragraph(inline(line[2:]), STYLES["h2"]))
            i += 1
        elif line.startswith("## "):
            story.append(Paragraph(inline(line[3:]), STYLES["h2"]))
            i += 1
        elif line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), STYLES["h3"]))
            i += 1
        elif line.startswith("**Challenge:**") or line.startswith("**Team submission"):
            story.append(Paragraph(inline(line), STYLES["subtitle"]))
            i += 1
        elif line.strip() == "---":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.6, color=LINE, spaceAfter=10))
            i += 1
        elif line.strip().startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            code_txt = "<br/>".join(l.replace(" ", "&nbsp;") or "&nbsp;" for l in code_lines)
            story.append(Paragraph(code_txt, STYLES["code"]))
        elif line.strip().startswith("!["):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
            if m:
                alt, relpath = m.groups()
                img_path = (REPORT_MD.parent / relpath).resolve()
                if img_path.exists():
                    img = Image(str(img_path), width=6.3 * inch, height=6.3 * inch * 0.62)
                    img.hAlign = "CENTER"
                    story.append(img)
                    story.append(Paragraph(alt, STYLES["caption"]))
            i += 1
        elif line.strip().startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            text = " ".join(l.strip() for l in quote_lines if l.strip())
            if text:
                story.append(Paragraph(inline(text), STYLES["quote"]))
        elif line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            story.append(Spacer(1, 4))
            story.append(parse_table(table_lines))
            story.append(Spacer(1, 10))
        elif re.match(r"^\s*-\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*-\s+", lines[i]):
                item_lines = [re.sub(r"^\s*-\s+", "", lines[i])]
                i += 1
                while i < len(lines) and lines[i].strip() != "" and not re.match(
                    r"^\s*(-\s+|\d+\.\s+|#|\||```|!\[|---)", lines[i]
                ):
                    item_lines.append(lines[i].strip())
                    i += 1
                items.append(ListItem(Paragraph(inline(" ".join(item_lines)), STYLES["bullet"]),
                                       bulletColor=BLUE))
            story.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=16))
            story.append(Spacer(1, 6))
        elif re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                item_lines = [re.sub(r"^\s*\d+\.\s+", "", lines[i])]
                i += 1
                while i < len(lines) and lines[i].strip() != "" and not re.match(
                    r"^\s*(-\s+|\d+\.\s+|#|\||```|!\[|---)", lines[i]
                ):
                    item_lines.append(lines[i].strip())
                    i += 1
                items.append(ListItem(Paragraph(inline(" ".join(item_lines)), STYLES["bullet"])))
            story.append(ListFlowable(items, bulletType="1", leftIndent=16))
            story.append(Spacer(1, 6))
        elif line.strip() == "":
            i += 1
        else:
            para_lines = [line]
            i += 1
            while i < len(lines) and lines[i].strip() != "" and not re.match(
                r"^(#|>|-|\d+\.|\||```|!\[|---)", lines[i].strip()
            ):
                para_lines.append(lines[i])
                i += 1
            story.append(Paragraph(inline(" ".join(para_lines)), STYLES["body"]))

    return story


def main():
    OUT_DIR.mkdir(exist_ok=True)
    md_text = REPORT_MD.read_text()
    story = build_story(md_text)

    doc = SimpleDocTemplate(
        str(OUT_PDF), pagesize=LETTER,
        topMargin=0.65 * inch, bottomMargin=0.65 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        title="Autonomous Production Choke Controller — Engineering Report",
    )
    doc.build(story)
    print(f"wrote {OUT_PDF}  ({OUT_PDF.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
