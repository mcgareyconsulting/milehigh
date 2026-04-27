"""Convert EXECUTIVE_SUMMARY.md to a clean professional PDF."""
from markdown_pdf import MarkdownPdf, Section

with open("analysis/EXECUTIVE_SUMMARY.md", "r") as f:
    md = f.read()

pdf = MarkdownPdf(toc_level=2, optimize=True)

# Professional CSS — serif body, clean spacing, conservative palette
css = """
@page { size: Letter; margin: 0.85in 0.85in 0.85in 0.85in; }
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 10.5pt;
    line-height: 1.5;
    color: #222;
}
h1 {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 22pt;
    color: #1a1a1a;
    border-bottom: 2px solid #1a1a1a;
    padding-bottom: 6pt;
    margin-top: 0;
    margin-bottom: 12pt;
}
h2 {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 14pt;
    color: #1a1a1a;
    margin-top: 22pt;
    margin-bottom: 6pt;
    border-bottom: 1px solid #888;
    padding-bottom: 3pt;
}
h3 {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 12pt;
    color: #2a3f5f;
    margin-top: 16pt;
    margin-bottom: 4pt;
}
p { margin: 6pt 0; }
ul, ol { margin: 6pt 0 6pt 18pt; }
li { margin-bottom: 3pt; }
strong { color: #1a1a1a; }
em { color: #444; }
hr {
    border: none;
    border-top: 1px solid #bbb;
    margin: 14pt 0;
}
code {
    font-family: "Menlo", "Courier New", monospace;
    font-size: 9pt;
    background: #f3f3f3;
    padding: 1pt 3pt;
    border-radius: 2pt;
}
blockquote {
    border-left: 3px solid #2a3f5f;
    margin-left: 0;
    padding-left: 12pt;
    color: #444;
    font-style: italic;
}
"""

pdf.add_section(Section(md, toc=False), user_css=css)
pdf.meta["title"] = "Operations Data — Executive Summary"
pdf.meta["author"] = "MHMW Operations Analysis"

out = "analysis/Executive_Summary_Operations_Analysis.pdf"
pdf.save(out)
print(f"saved: {out}")
