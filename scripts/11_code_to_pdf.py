"""
11_code_to_pdf.py
==================
Renders every Python source file into a readable, syntax-highlighted PDF.

Exists for one reason: the hackathon portal only accepts PDF or zip, and its own
instructions say "in case of errors uploading zip files, convert/print all files
to pdf and upload." This script is that fallback, generated automatically so the
PDFs can never drift from the actual code.

Produces:
    submission/code_pdfs/<flat-name>.py.pdf   one PDF per source file
    submission/ALL_SOURCE_CODE.pdf            every file concatenated, in one PDF,
                                               with a table of contents - upload
                                               this single file if a zip won't go through
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak,
    Table, TableStyle,
)
from reportlab.lib.enums import TA_LEFT
import re
from html.parser import HTMLParser

OUT_DIR = ROOT / "submission" / "code_pdfs"
COMBINED_PDF = ROOT / "submission" / "ALL_SOURCE_CODE.pdf"

# Files in a deliberate reading order: interface/config first, then the physics,
# then model + controller, then the scripts pipeline in run order, then tests.
FILE_ORDER = [
    "src/simulator_interface.py",
    "src/config.py",
    "src/well_simulator.py",
    "src/model.py",
    "src/controller.py",
    "src/plotting.py",
    "scripts/01_reference_dataset_eda.py",
    "scripts/02_step_tests.py",
    "scripts/03_identify_model.py",
    "scripts/04_run_scenarios.py",
    "scripts/05_export_dashboard_data.py",
    "scripts/06_robustness_study.py",
    "scripts/07_capture_dashboard.py",
    "scripts/08_export_report_pdf.py",
    "scripts/09_build_presentation.py",
    "scripts/10_build_ppt_assets.py",
    "scripts/11_code_to_pdf.py",
    "tests/test_all.py",
]

INK = colors.HexColor("#0f172a")
DIM = colors.HexColor("#64748b")
BLUE = colors.HexColor("#1d4fd8")
LINE_BG = colors.HexColor("#f6f8fa")

# Pygments token -> reportlab colour, tuned for a light background (print-friendly)
TOKEN_COLORS = {
    "Token.Keyword": colors.HexColor("#cf222e"),
    "Token.Keyword.Namespace": colors.HexColor("#cf222e"),
    "Token.Keyword.Constant": colors.HexColor("#0550ae"),
    "Token.Name.Builtin": colors.HexColor("#8250df"),
    "Token.Name.Builtin.Pseudo": colors.HexColor("#8250df"),
    "Token.Name.Function": colors.HexColor("#8250df"),
    "Token.Name.Class": colors.HexColor("#8250df"),
    "Token.Name.Decorator": colors.HexColor("#8250df"),
    "Token.String": colors.HexColor("#0a3069"),
    "Token.String.Doc": colors.HexColor("#6e7781"),
    "Token.Number": colors.HexColor("#0550ae"),
    "Token.Comment": colors.HexColor("#6e7781"),
    "Token.Operator": colors.HexColor("#cf222e"),
    "Token.Punctuation": INK,
    "Token.Name": INK,
}


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tokenize_to_markup(code: str) -> list[str]:
    """Convert Python source into reportlab mini-XML markup, one string per line,
    preserving Pygments' syntax colouring."""
    from pygments.lexers import PythonLexer as Lexer
    from pygments import lex

    lines_markup = [""]
    for ttype, value in lex(code, Lexer()):
        colour = None
        t = str(ttype)
        while t and colour is None:
            colour = TOKEN_COLORS.get(t)
            t = t.rsplit(".", 1)[0] if "." in t else ""
        colour = colour or INK
        hexcol = colour.hexval()[2:] if hasattr(colour, "hexval") else "0f172a"

        parts = value.split("\n")
        for i, part in enumerate(parts):
            if part:
                lines_markup[-1] += f'<font color="#{hexcol}">{escape(part)}</font>'
            if i < len(parts) - 1:
                lines_markup.append("")
    return lines_markup


def build_file_flowables(rel_path: str, code_style, header_style) -> list:
    path = ROOT / rel_path
    text = path.read_text()
    n_lines = text.count("\n") + 1

    flow = []
    flow.append(Paragraph(escape(rel_path), header_style))
    flow.append(Paragraph(f"{n_lines} lines", ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=8.5, textColor=DIM, spaceAfter=8)))
    flow.append(HRFlowable(width="100%", thickness=0.7, color=colors.HexColor("#d0d7de"), spaceAfter=8))

    lines = tokenize_to_markup(text)
    # Group ~55 lines per Paragraph so long files don't choke reportlab's layout engine
    chunk = []
    for i, line in enumerate(lines, start=1):
        num = f'<font color="#8c959f">{i:>4} </font>'
        chunk.append(num + (line or "&nbsp;"))
        if len(chunk) >= 55:
            flow.append(Paragraph("<br/>".join(chunk), code_style))
            chunk = []
    if chunk:
        flow.append(Paragraph("<br/>".join(chunk), code_style))
    return flow


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    header_style = ParagraphStyle(
        "fheader", fontName="Helvetica-Bold", fontSize=12.5, textColor=BLUE,
        spaceAfter=2, alignment=TA_LEFT,
    )
    code_style = ParagraphStyle(
        "code", fontName="Courier", fontSize=7.6, leading=9.6,
        textColor=INK, backColor=LINE_BG, borderPadding=6, spaceAfter=6,
    )
    toc_title_style = ParagraphStyle("toctitle", fontName="Helvetica-Bold", fontSize=18,
                                     textColor=INK, spaceAfter=4)
    toc_sub_style = ParagraphStyle("tocsub", fontName="Helvetica", fontSize=10,
                                   textColor=DIM, spaceAfter=18)
    toc_row_style = ParagraphStyle("tocrow", fontName="Helvetica", fontSize=10.5,
                                   textColor=INK)

    files = [f for f in FILE_ORDER if (ROOT / f).exists()]
    missing = [f for f in FILE_ORDER if not (ROOT / f).exists()]
    if missing:
        print(f"  NOTE: not found, skipped: {missing}")

    # ---- individual per-file PDFs -------------------------------------
    print(f"Rendering {len(files)} individual PDFs to {OUT_DIR.relative_to(ROOT)}/ ...")
    for rel_path in files:
        flat_name = rel_path.replace("/", "_") + ".pdf"
        doc = SimpleDocTemplate(
            str(OUT_DIR / flat_name), pagesize=LETTER,
            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
            leftMargin=0.55 * inch, rightMargin=0.55 * inch,
            title=rel_path,
        )
        doc.build(build_file_flowables(rel_path, code_style, header_style))
        print(f"  {flat_name}")

    # ---- one combined PDF with a table of contents ---------------------
    print(f"\nRendering combined PDF: {COMBINED_PDF.relative_to(ROOT)}")
    story = []
    story.append(Paragraph("Autonomous Production Choke Controller", toc_title_style))
    story.append(Paragraph(
        "Full source code &mdash; every Python file in the project, in one PDF. "
        f"{len(files)} files, {sum((ROOT / f).read_text().count(chr(10)) + 1 for f in files)} lines total.",
        toc_sub_style))

    toc_rows = [[Paragraph(f"{i+1}.", toc_row_style), Paragraph(escape(f), toc_row_style)]
                for i, f in enumerate(files)]
    toc_table = Table(toc_rows, colWidths=[0.45 * inch, 6.0 * inch])
    toc_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(toc_table)
    story.append(PageBreak())

    for rel_path in files:
        story.extend(build_file_flowables(rel_path, code_style, header_style))
        story.append(PageBreak())
    if story and isinstance(story[-1], PageBreak):
        story.pop()

    doc = SimpleDocTemplate(
        str(COMBINED_PDF), pagesize=LETTER,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.55 * inch, rightMargin=0.55 * inch,
        title="Autonomous Production Choke Controller - Source Code",
    )
    doc.build(story)
    print(f"  wrote {COMBINED_PDF} ({COMBINED_PDF.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
