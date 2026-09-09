"""Shared styling and PDF rendering for the generated documents.

Three documents are built from the repo — the methodology, the Q&A defence
pack and the code walkthrough. They share one look, one escaping helper and
one renderer, which live here so that changing the house style is one edit
rather than three.

    from docgen import esc, table, page, render, qa

Rendering uses the Playwright chromium already installed for the scrapers.
No extra dependency.
"""

from __future__ import annotations

import os

BG = "#0f1115"
PANEL = "#171a21"
INK = "#e6e8eb"
MUTED = "#9aa4b2"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREEN = "#3f9c6d"
LINE = "#252a33"

CSS = """
/* Zero visible border at the page edge is achieved by letting the ROOT
   element's background propagate to the page canvas — it paints the whole
   sheet, margins included — while @page margins still inset text on EVERY
   page. A literal margin:0 with padding on a wrapper pads only page one;
   page two then runs into the paper edge. */
@page { size: A4; margin: 7mm 0; }
* { box-sizing: border-box; }
html { background: %(BG)s; }
html, body { margin: 0; padding: 0; }
/* Horizontal inset comes from padding on the content, NOT from a page
   margin, so the page box itself is edge-to-edge left and right. The small
   vertical @page margin stays because it is the only inset that repeats on
   every printed page — padding on a block is applied once and is not
   reinstated where the block breaks, so with margin:0 top and bottom the
   text would sit against the paper edge on every continuation page.
   Set both to 0 for literal zero. */
.page { padding: 0 7mm; }
body {
  background: %(BG)s; color: %(INK)s;
  font-family: "Segoe UI", -apple-system, system-ui, Arial, sans-serif;
  font-size: 10pt; line-height: 1.55;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
.page { break-after: page; }
.page:last-child { break-after: auto; }
.page > h2:first-child { margin-top: 4pt; }
h1 { font-size: 25pt; margin: 0 0 4pt; letter-spacing: -0.6pt; font-weight: 650; }
h2 { font-size: 13pt; margin: 20pt 0 7pt; color: %(BLUE)s; font-weight: 620;
     border-bottom: 1px solid %(LINE)s; padding-bottom: 4pt; }
h3 { font-size: 10.6pt; margin: 13pt 0 4pt; font-weight: 620; }
h2, h3 { break-after: avoid; }
table, .panel, .formula, .qa { break-inside: avoid; }
p  { margin: 0 0 8pt; }
.sub { color: %(MUTED)s; font-size: 10.5pt; margin: 0 0 2pt; }
ul, ol { margin: 0 0 9pt; padding-left: 16pt; }
li { margin-bottom: 3.5pt; }
code, .mono { font-family: Consolas, "DejaVu Sans Mono", monospace;
              font-size: 8.8pt; color: %(ORANGE)s; }
table { width: 100%%; border-collapse: collapse; margin: 8pt 0 12pt;
        font-size: 9pt; }
th { text-align: left; color: %(MUTED)s; font-weight: 600;
     border-bottom: 1px solid %(LINE)s; padding: 5pt 7pt; font-size: 8.2pt;
     text-transform: uppercase; letter-spacing: 0.4pt; }
td { padding: 5pt 7pt; border-bottom: 1px solid %(LINE)s; vertical-align: top; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }
.panel { background: %(PANEL)s; border-left: 3px solid %(BLUE)s;
         padding: 9pt 12pt; margin: 9pt 0 12pt; border-radius: 0 3px 3px 0; }
.panel.warn { border-left-color: %(ORANGE)s; }
.panel.good { border-left-color: %(GREEN)s; }
.panel p:last-child { margin-bottom: 0; }
.formula, pre { background: %(PANEL)s; padding: 10pt 12pt; margin: 8pt 0;
           font-family: Consolas, "DejaVu Sans Mono", monospace;
           font-size: 8.6pt; line-height: 1.45; color: %(INK)s;
           border-radius: 3px; white-space: pre-wrap; overflow-wrap: anywhere; }
pre .c { color: %(MUTED)s; }
.tag { display: inline-block; font-size: 7.4pt; letter-spacing: 0.6pt;
       text-transform: uppercase; padding: 2pt 6pt; border-radius: 2px;
       background: %(BLUE)s; color: #fff; font-weight: 650; }
.tag.warn { background: %(ORANGE)s; }
.tag.good { background: %(GREEN)s; }
.tag.mute { background: %(LINE)s; color: %(MUTED)s; }
a { color: %(BLUE)s; text-decoration: none; word-break: break-all; }
.rule { height: 3px; background: %(BLUE)s; width: 54pt; margin: 12pt 0 16pt; }
.foot { color: %(MUTED)s; font-size: 8.2pt; border-top: 1px solid %(LINE)s;
        padding-top: 7pt; margin-top: 18pt; }
.two { display: flex; gap: 14pt; }
.two > div { flex: 1; }

/* question-and-answer block */
.qa { margin: 0 0 13pt; }
.qa .q { font-weight: 640; color: %(INK)s; margin: 0 0 4pt;
         padding-left: 15pt; text-indent: -15pt; }
.qa .q::before { content: "Q "; color: %(BLUE)s; font-weight: 700; }
.qa .a { margin: 0 0 4pt; padding-left: 15pt; }
.qa .push { margin: 0; padding-left: 15pt; color: %(MUTED)s;
            font-size: 9.2pt; }
.qa .push b { color: %(ORANGE)s; }
.owner { float: right; }
""" % dict(BG=BG, PANEL=PANEL, INK=INK, MUTED=MUTED, BLUE=BLUE,
           ORANGE=ORANGE, GREEN=GREEN, LINE=LINE)


def esc(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def table(headers, rows, numeric=()) -> str:
    th = "".join(f'<th class="{"n" if i in numeric else ""}">{esc(h)}</th>'
                 for i, h in enumerate(headers))
    body = []
    for row in rows:
        tds = "".join(f'<td class="{"n" if i in numeric else ""}">{c}</td>'
                      for i, c in enumerate(row))
        body.append(f"<tr>{tds}</tr>")
    return (f"<table><thead><tr>{th}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table>")


def qa(question: str, answer: str, owner: str = "", push: str = "") -> str:
    """One question-and-answer block.

    owner  — who on the team fields this one.
    push   — what to say if the judge presses further. Having a second
             sentence ready is the difference between an answer and a
             defence.
    """
    tag = f'<span class="tag mute owner">{esc(owner)}</span>' if owner else ""
    extra = f'<p class="push"><b>If pressed:</b> {push}</p>' if push else ""
    return (f'<div class="qa">{tag}<p class="q">{question}</p>'
            f'<p class="a">{answer}</p>{extra}</div>')


def document(title: str, pages: list) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body>"
            + "".join(f'<div class="page">{p}</div>' for p in pages)
            + "</body></html>")


def render(html: str, html_path: str, pdf_path: str) -> bool:
    os.makedirs(os.path.dirname(html_path) or ".", exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"[docgen] wrote {html_path}")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[docgen] playwright missing — print the HTML from a browser "
              "(Ctrl+P, enable background graphics).")
        return False
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, wait_until="load")
            page.pdf(path=pdf_path, format="A4", print_background=True,
                     margin={"top": "0", "right": "0",
                             "bottom": "0", "left": "0"})
        finally:
            browser.close()
    print(f"[docgen] wrote {pdf_path}")
    return True
