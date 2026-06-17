#!/usr/bin/env python3
"""Generate tanitim.pdf + tanitim.docx from tanitim.md via WeasyPrint + pandoc."""

import os
import subprocess
import markdown
import weasyprint

MD_PATH = r"C:\project\smart\docs\tanitim.md"
PDF_PATH = r"C:\project\smart\docs\tanitim.pdf"
DOCX_PATH = r"C:\project\smart\docs\tanitim.docx"
REF_DOCX = r"C:\project\smart\docs\ref.docx"

with open(MD_PATH, encoding="utf-8") as f:
    md_text = f.read()

CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; line-height: 1.5; color: #1a1a1a; }
h1 { font-size: 22pt; color: #005a9e; border-bottom: 2px solid #005a9e; padding-bottom: 6px; margin-top: 30px; }
h2 { font-size: 16pt; color: #005a9e; margin-top: 28px; }
h3 { font-size: 13pt; color: #333; margin-top: 20px; }
h4 { font-size: 11pt; color: #444; margin-top: 14px; }
table { border-collapse: collapse; width: 100%; margin: 14px 0; page-break-inside: avoid; font-size: 9.5pt; }
th { background-color: #005a9e; color: white; padding: 7px 10px; text-align: left; font-weight: 700; border: 1px solid #005a9e; }
td { padding: 5px 10px; border: 1px solid #bbb; vertical-align: top; }
tr:nth-child(even) td { background-color: #f5f8fc; }
code { background: #eef; padding: 1px 5px; border-radius: 3px; font-family: 'Cascadia Code', Consolas, monospace; font-size: 9.5pt; }
pre { background: #f5f5f5; padding: 12px; border-left: 4px solid #005a9e; font-family: 'Cascadia Code', Consolas, monospace; font-size: 9pt; overflow-x: auto; }
hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }
strong { color: #005a9e; }
ul, ol { padding-left: 22px; }
li { margin: 3px 0; }
p { margin: 6px 0; }
img { max-width: 100%; height: auto; display: block; margin: 20px auto; }
"""

html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
html_full = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{html_body}</body></html>"""

weasyprint.HTML(string=html_full, base_url=os.path.dirname(MD_PATH)).write_pdf(PDF_PATH)
print(f"PDF created: {PDF_PATH}")

# DOCX via pandoc — proper markdown-to-DOCX conversion
TMP_DOCX = DOCX_PATH + ".tmp"
if os.path.exists(TMP_DOCX):
    os.remove(TMP_DOCX)
cmd = ["pandoc", MD_PATH, "-o", TMP_DOCX, "--from", "markdown", "--to", "docx"]
if os.path.exists(REF_DOCX):
    cmd += ["--reference-doc", REF_DOCX]
subprocess.run(cmd, check=True)
if os.path.exists(DOCX_PATH):
    os.remove(DOCX_PATH)
os.rename(TMP_DOCX, DOCX_PATH)
print(f"DOCX created: {DOCX_PATH}")
