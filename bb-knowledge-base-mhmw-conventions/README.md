# BB Knowledge Base — MHMW Conventions

MHMW's **own** shop conventions, glossary, code build-standards, fastener/part
catalogs, and drafting workflows — the "how Mile High Metal Works actually does it"
layer for all agentic BB workflows.

This complements the other knowledge bases in this repo:

| KB | Scope |
| :--- | :--- |
| `bb-knowledge-base1` / `bb-knowledge-base2` | Generic fabrication-design compliance *system* (schemas, conflict-detection framework) |
| `bb-knowledge-base-division-05-metal-codes` | Generic **code minimums** (IBC 2021 / ADA 2010 / AISC / AWS) |
| **`bb-knowledge-base-mhmw-conventions`** (this) | **MHMW-specific** conventions, glossary, build standards, parts, and workflows |

Where this KB and the division-05 code KB overlap, division-05 gives the *code
minimum* and this KB gives *what MHMW builds to* — MHMW's tighter value governs the
shop drawing.

Provenance: ingested from `bbknowledge_03.zip`, 2026-07-20. Original PDFs are kept in
`source-pdfs/` (and `weld-symbols/`) for traceability; the markdown files below are the
consolidated source of truth.

---

## Contents

| File | What it covers | Distilled into prompting? |
| :--- | :--- | :--- |
| [`BB-RULES-FOR-REVIEW.md`](BB-RULES-FOR-REVIEW.md) | **Client-facing rules reference** — plain-language list of every rule BB works from, with open questions for the shop; the review/markup surface for this KB | (it *describes* the prompting; reissue on every rule change) |
| [`mhmw-abbreviations-and-lumber.md`](mhmw-abbreviations-and-lumber.md) | Drawing abbreviations/terms glossary + lumber-sizing guide (nominal vs. actual) | PDF reviewer header (abbrev. subset) |
| [`mhmw-code-conventions.md`](mhmw-code-conventions.md) | MHMW build standards for stairs/guards/handrails/fall-protection; SFD vs. MFB; the "reduce by ¼" " standard | PDF reviewer `rules.py` (MHMW-convention rules) |
| [`mhmw-fasteners-and-parts.md`](mhmw-fasteners-and-parts.md) | Fastener-by-substrate matrix + hole oversizing; typical-parts catalog (`FP`/`SC` naming) | PDF reviewer `rules.py` (fastener rule) |
| [`mhmw-drafting-workflows.md`](mhmw-drafting-workflows.md) | DRR (Drafting Release Review) + Submittal-for-GC process flows; F/E print labels; Release # convention | BB chat lifecycle prompt (process vocabulary) |
| [`weld-symbols/`](weld-symbols/README.md) | AWS weld-symbol chart + textbook chapter — **third-party copyrighted, reference only** | ✗ (do not inline — see its README) |
| `source-pdfs/` | Original ingested PDFs | — |

### Duplicate handling

`MHMW 101.pdf` (7 pp.) is a compilation packet — pp. 1–2 = `Abbreviations and
Lumber.pdf`, p. 3 = `Code Requrements.pdf`, pp. 4–7 = the four sheets of `Codes and
Fasteners.pdf`. All four PDFs are preserved in `source-pdfs/`; their content is
consolidated without duplication into the markdown files above. (The `Requrements`
filename typo is the original's — kept as-is for traceability.)

### Known source gaps (confirm with the shop)

- `Typical parts.pdf` F23 (Spring Closure) and F25 (Cane Bolt Assembly) say
  "Ordered Part **###**" — the supplier/part number was never filled in at the source.
- `Codes and Fasteners.pdf` sheet 1 carries un-interpreted `36"` and `<27"` dims near
  the "80\" Min Headroom Clearance" callout under the stair (likely an under-stair
  protruding-object / cane-detection convention, but not stated); see the note in
  `mhmw-code-conventions.md`.

---

## How this KB is distributed into prompting

The reusable, checkable knowledge is distilled into the prompt-facing code of the two
agentic BB workflows (same pattern the division-05 KB already follows — "distilled
from bb-knowledge-base-…"):

1. **PDF code-compliance reviewer** — `app/brain/pdf_review/rules.py`
   - MHMW-convention `RULES` entries (graduated guard openings, fall-protection
     geometry, MFB build dims + `11-1/16"` run preference, precast-tread standard,
     fastener-to-substrate correctness).
   - A compact MHMW build-conventions / abbreviations note in `SYSTEM_PROMPT_HEADER`.
2. **BB chat lifecycle summarizer** — `app/brain/bb_chat/lifecycle_prompt.py`
   - A short MHMW process-vocabulary block (DRR, Job Start → Release #, F/E prints,
     submittal → GC → FC path) so lifecycle answers use MHMW's terms correctly.

Markdown here stays the source of truth; the prompt copies are intentionally compact.
When a convention changes, update the markdown **and** the corresponding prompt block.
