# MHMW Drafting Workflows — DRR and Submittal-for-GC

MHMW's two drafting-side process flows, transcribed from the company flowcharts.
These define the vocabulary and stage sequence that lifecycle-aware agents (e.g. BB
chat's release/submittal lifecycle summaries) reason about.

Sources: `DRR Work flow.pdf`, `Submittal for GC workflow.pdf`.

Both flows run **on Procore** and share a common review loop: *submit → reviewed by
the next person in the workflow → the response determines next steps.*

---

## DRR — Drafting Release Review (production/installation drawings)

The DRR flow turns an approved/returned submittal into the drawings the shop and
field build from.

1. **DRR: Drafting Release Review** — kick off from the returned submittal + field
   measurements.
2. **Create the drawings** — use the returned submittal and field measurements to
   create drawings for production and installation.
3. **Create the Release number** — open a **Job Start document**, which creates the
   Release number. Save it to the **Release folder** in the project file on the
   **Active projects server**.
4. **Produce drawings + PDF** — produce the production/installation drawings and
   create a PDF to upload to Procore.
5. **Complete the Job Start document** — fill out **all** information including **BOM
   and hardware**. Ensure the **proper budget** is applied to the Job Start. Create a
   PDF of the **Drafting Cover Sheet** to upload to Procore.
6. **Submit for approval** — submit the Drafting Cover Sheet (from Job Start) along
   with the PDF drawings to Procore for approval.
7. **Review** — the submittal is reviewed by the next person in the workflow; the
   response determines next steps:
   - **Revise and Resubmit** — make revisions per markups; take time to ask questions
     if clarification is needed; submit back into the workflow when complete (loops
     back to review).
   - **Approved as noted** — make corrections to the marked-up drawings and **proceed
     to FC Release**.
   - **Approved** — **proceed to FC Release**.

### Print labeling conventions (DRR)

- Label prints for **Fabrication** with **"F"** page numbers; prints for **Erection**
  with **"E"** page numbers.
- **Include the Release # on every print.**

---

## Submittal for GC Approval

The submittal flow produces the package the General Contractor (and Architect /
Structural engineer) approve before drafting release.

1. **Submittal for GC approval** — begin the submittal.
2. **Create the submittal** — use the **Architectural and Structural drawings along
   with the quote** to create the submittal for GC approval. **Complete submittals are
   critical.** **Cloud** any major changes and RFIs that are part of the submittal.
3. **Submit to workflow** — once complete, submit to the workflow on Procore for
   approval.
4. **Review** — reviewed by the next person in the workflow; the response determines
   next steps:
   - **Revise and Resubmit** — make revisions per markups; ask questions to clarify if
     needed; submit back into the workflow when complete (loops back to review).
   - **Approved** — the **PM distributes to the GC** for approval by **GC, Architect,
     and Structural**.
5. **Returned Submittal from GC** — the GC returns the reviewed submittal.
6. **Corrections** — make all corrections per markups and resubmit into the workflow if
   needed.

---

## How the two flows connect

```
Arch + Structural drawings + quote
        │
        ▼
  Submittal for GC approval ──► GC / Arch / Structural review ──► Returned submittal
        │                                                              │
        └──────────────────────────────────────────────────────────────┘
                                     │ (approved / returned)
                                     ▼
        DRR (returned submittal + field measurements) ──► Job Start doc + Release #
                                     │
                                     ▼
             Drafting Cover Sheet + drawings submitted on Procore
                                     │
                          approved / approved-as-noted
                                     ▼
                               FC Release
```

- A **submittal** is the GC-facing approval artifact; a **Release** is the internal
  drafting/production unit created at the Job Start step of DRR. (This mirrors the app
  data model: `Submittals` vs `Releases`.)
- "Cloud any major changes and RFIs" = revision clouds on the submittal drawings.
- **FC Release** = For-Construction release — the point at which the FC drawing set is
  produced (the set the PDF code-compliance reviewer checks — see
  [mhmw-code-conventions.md](mhmw-code-conventions.md)).
