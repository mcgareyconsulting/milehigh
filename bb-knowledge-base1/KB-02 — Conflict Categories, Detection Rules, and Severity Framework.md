# KB-02 — Conflict Categories, Detection Rules, and Severity Framework

**Knowledge Base:** Steel Fabrication Compliance System  
**Document ID:** KB-02  
**Source:** All rules and examples in this document are derived directly from conflicts observed in the comparison of `AmenitySteel.449.pdf` against `AmenitySteel.dwg`. No rules have been inferred or assumed beyond what the documents explicitly demonstrated.  
**Status:** Verified against one real-world fabrication set. Treat as a starting taxonomy, not a complete ruleset.

---

## 1. The Two-Document Compliance Model

A fabrication compliance check compares two document types that describe the same structure from different perspectives:

| Document Type | Role | Governs |
|---------------|------|---------|
| **Fabrication Set (PDF)** | Fabricator's manufacturing instructions | How each piece is cut, drilled, and welded |
| **Design Model (DWG / IFC)** | Engineer of Record's design intent | What the finished structure must achieve |

Conflicts arise when these two documents disagree. The compliance system's job is to find every disagreement, classify it, and assign a severity so the team can prioritize resolution.

A third check — the **PDF self-consistency check** — compares the fabrication set against itself, looking for internal contradictions (e.g., a plan sheet elevation that contradicts the shop drawing for the same member). This check requires only the PDF and no design model.

> **Architecture principle observed in practice:** These two checks — PDF self-consistency and PDF-vs-DWG cross-document comparison — must be implemented as independent, separately callable functions. The PDF self-check should produce useful results even when no DWG is available.

---

## 2. Conflict Severity Framework

Three severity levels were used in the Amenity Steel analysis. The criteria below are derived from the actual consequences of each conflict found.

### HIGH Severity

A conflict is HIGH severity when it would directly cause one or more of the following if unresolved:

- A member is fabricated from the wrong section size (wrong weight, wrong capacity, wrong connection geometry)
- A member is fabricated but cannot be erected because its elevation is wrong
- A member required by the design is entirely absent from the fabrication scope

HIGH conflicts must be resolved before any fabrication of affected members begins.

### MEDIUM Severity

A conflict is MEDIUM severity when it would cause one or more of the following if unresolved:

- A dimensional discrepancy that propagates through multiple members (e.g., a base elevation error that affects all column lengths)
- A member is placed on the wrong level plan, creating erection sequencing confusion
- A naming or designation system in the design model cannot be mapped to fabrication marks, making it impossible to verify completeness

MEDIUM conflicts should be resolved before fabrication of affected members begins, but do not necessarily stop all work.

### LOW Severity

A conflict is LOW severity when it represents a documentation gap or administrative omission that does not directly affect fabrication accuracy but creates risk of confusion, incomplete records, or procurement failure:

- A member exists in the set but is missing from the cover sheet inventory
- A mark number is intentionally skipped but not documented
- A procurement item is flagged as unresolved with no follow-up noted

LOW conflicts should be resolved before the fabrication set is finalized and issued for construction.

---

## 3. Conflict Category Taxonomy

The following five categories cover all 10 conflicts found in the Amenity Steel analysis. Each category has a defined detection rule.

---

### Category 1: Section Size Mismatch

**Definition:** The same member location carries a different section size designation in the fabrication set versus the design model.

**Detection rule:** For each member that can be matched between the two documents (by mark, by position, or by elevation), compare the section size string character-by-character after normalizing to uppercase and removing spaces. Any difference is a Section Size Mismatch.

**Severity:** HIGH — a section size difference means the wrong material will be ordered and cut.

**Observed instance (C-001):** Beam B23 is designated W18X50 in the fabrication set and W18X55 in the DWG. W18X55 is a heavier section with different flange geometry, requiring different connection hardware.

**Normalization required before comparison:**
- Convert to uppercase: `w18x50` → `W18X50`
- Remove spaces: `W18 X50` → `W18X50`
- Normalize the × character: `W18×50` → `W18X50`
- Treat `HSS5X5X1/4` and `HSS5x5x1/4` as identical

---

### Category 2: Member Present in Design Model but Absent from Fabrication Set

**Definition:** A section size or member appears in the DWG that has no corresponding mark or shop drawing in the fabrication set.

**Detection rule:** Extract all unique section size strings from the DWG. For each section size, verify that at least one fabrication mark with that section exists in the PDF. If a section size found in the DWG has no match in the PDF, flag it. Additionally, check whether the DWG references any framing marks (e.g., F5, F6) that are not represented in the fabrication set.

**Severity:** HIGH — a member in the design that is not in the fabrication set will not be fabricated, creating a structural gap.

**Observed instance (C-002):** The DWG contained `HSS7X7X3/8` near framing mark F5 at elevation 88'-6". No HSS7X7X3/8 member exists anywhere in the 46-page fabrication set. This member was either out of scope (another trade's responsibility) or was missed during detailing.

**Important distinction:** Not every section size in a DWG belongs to the steel fabricator's scope. The DWG may reference wood members (LVL, 2×10, 2×12), concrete elements, or other trades. A compliance system must filter out non-steel section types before running this check. Section types that belong to structural steel scope: W-shapes, HSS, C-shapes (channels), angles (L-shapes), plates (PL).

---

### Category 3: Impossible or Out-of-Range Elevation

**Definition:** A T.O.S. or T.O.C. elevation value in the fabrication set is either negative, zero, or falls outside the established elevation range for the project.

**Detection rule:** This is a PDF self-consistency check requiring no DWG. Steps:
1. Extract the project base elevation from the cover sheet or general notes (in Amenity Steel: 116'-0" for column bases).
2. Extract the highest T.O.C. elevation from the column schedule (in Amenity Steel: 137'-1 1/2").
3. Define the valid elevation window as [base elevation − 1'-0"] to [highest T.O.C. + 2'-0"]. The tolerances account for embed plates below grade and potential future additions.
4. Any elevation value outside this window, or any negative value, is flagged as impossible.

**Severity:** HIGH — an impossible elevation means the plan sheet annotation is wrong. The member cannot be erected to a negative elevation. If fabricated to the wrong elevation, it will not fit.

**Observed instances (C-003, C-004):** Beams B11 and B24 both showed T.O.S. = -5 13/16" on the Level 4 framing plan. The correct value, inferred from neighboring members of the same type (B8, B9, B10 all at 136'-7 1/2"), is almost certainly 136'-7 1/2". The negative value appears to be a software annotation error in Advance Steel.

**Root cause pattern:** Negative elevations in Advance Steel shop drawings are a known symptom of a member whose elevation reference was not properly set in the model. The elevation displayed on the plan sheet is the model's internal offset value rather than the absolute project elevation. This pattern should be treated as a software data entry error, not a design intent.

---

### Category 4: Level Assignment Conflict

**Definition:** A member appears on a framing plan for one level but carries a T.O.S. elevation that belongs to a different level.

**Detection rule:** This is a PDF self-consistency check. Steps:
1. Define elevation bands for each level from the framing plans (see KB-01, Section 4 for Amenity Steel values).
2. For each member on each plan sheet, verify that its T.O.S. elevation falls within the elevation band for that level.
3. If a member's elevation falls in a different level's band, flag it as a Level Assignment Conflict.

**Severity:** MEDIUM — the member itself may be correct, but placing it on the wrong plan sheet creates erection sequencing confusion and makes it impossible to verify completeness of each level.

**Observed instance (C-006):** Beam B9 (W10X15) appeared on the Level 3 framing plan but carried T.O.S. = 136'-7 1/2", which is solidly within the Level 4 elevation band (136'-7 1/2" to 137'-1 1/2"). Every other beam on the Level 3 plan had a T.O.S. in the 126' range.

---

### Category 5: Designation System Mismatch

**Definition:** The design model uses a naming or typing convention for members that cannot be directly mapped to the fabrication mark system used in the fabrication set.

**Detection rule:** This is a cross-document check. Extract all member identifiers from both documents. Identify any identifier format in the DWG that does not correspond to any mark format in the PDF. Flag the unmapped identifier system.

**Severity:** MEDIUM — the mismatch does not prevent fabrication but makes it impossible for the compliance system (or a human reviewer) to verify that every designed member has a corresponding fabrication mark.

**Observed instance (C-007):** The DWG used `[A]` and `[B]` type suffixes on column section sizes (e.g., `HSS5X5X1/4 [A]`, `HSS6X6X3/8 [B]`) to distinguish connection configurations. The fabrication set used individual marks (C1–C13) with no [A]/[B] designation. The mapping between these two systems was not defined in either document.

---

### Category 6: Cover Sheet Inventory Omission

**Definition:** A member has a shop drawing and appears on a plan sheet but is absent from the cover sheet member list.

**Detection rule:** This is a PDF self-consistency check. Steps:
1. Build a complete member inventory from plan sheets and individual shop drawings (these are the authoritative sources).
2. Build a second inventory from the cover sheet member list.
3. Any mark in the first inventory that is absent from the second is flagged.

**Severity:** LOW — the member will still be fabricated correctly because its shop drawing exists. However, the cover sheet piece count and weight summary will be wrong, which affects procurement, shipping, and field erection planning.

**Observed instance (C-008):** 8 of 25 beam marks were absent from the cover sheet: B1, B2, B3, B4, B8, B11, B24, B25. The cover sheet listed 29 total pieces; the correct count including all shop drawings is higher.

---

### Category 7: Intentional Mark Gap (Undocumented)

**Definition:** The mark numbering sequence has a gap (a number is skipped) with no documentation explaining the omission.

**Detection rule:** This is a PDF self-consistency check. Extract all mark numbers for each prefix (C, B, EP, etc.). Sort numerically. Flag any gap in the sequence. Cross-reference against the DWG to confirm the missing mark does not appear there either.

**Severity:** LOW — the missing mark likely represents a member removed during design development. It does not affect fabrication, but the undocumented gap creates confusion during erection when field crews reference mark numbers.

**Observed instance (C-009):** Column marks went C9 → C11, skipping C10. C10 was absent from both the PDF and the DWG.

---

### Category 8: Unresolved Procurement Flag

**Definition:** A material item in the fabrication set carries a notation indicating it was not ordered, not confirmed, or has an unresolved supplier status.

**Detection rule:** This is a PDF self-consistency check. Scan all plate schedule and material list pages for text strings matching patterns such as: "Did Not Order", "Not Ordered", "TBD", "Confirm", "N/A", "To Be Determined", or similar procurement uncertainty language.

**Severity:** LOW — the item may still be procured through other means, but the unresolved flag means there is no documented confirmation that the material will be available when needed.

**Observed instance (C-010):** Backer bar X1 (1/4" × 10-5/16" wide) on the plate schedule page (F1) carried the annotation "Did Not Order From DenCol" with no alternative supplier or resolution noted.

---

## 4. Conflict Priority Matrix

The following matrix summarizes all eight conflict categories with their default severity, the document check type required, and the consequence of leaving them unresolved.

| Category | Default Severity | Check Type | Consequence if Unresolved |
|----------|-----------------|------------|--------------------------|
| 1. Section Size Mismatch | HIGH | Cross-document | Wrong material fabricated; structural capacity compromised |
| 2. Member Absent from Fab Set | HIGH | Cross-document | Member not fabricated; structural gap in field |
| 3. Impossible Elevation | HIGH | PDF self-check | Member cannot be erected; field fit-up failure |
| 4. Level Assignment Conflict | MEDIUM | PDF self-check | Erection sequencing confusion; completeness unverifiable |
| 5. Designation System Mismatch | MEDIUM | Cross-document | Completeness of design-to-fab mapping unverifiable |
| 6. Cover Sheet Inventory Omission | LOW | PDF self-check | Piece count wrong; procurement and shipping planning affected |
| 7. Intentional Mark Gap (Undocumented) | LOW | PDF self-check | Field confusion during erection |
| 8. Unresolved Procurement Flag | LOW | PDF self-check | Material may not be available at fabrication time |

---

## 5. Elevation String Parsing Rules

Elevations in Advance Steel fabrication sets appear in several formats. A compliance system must handle all of them.

| Format | Example | Notes |
|--------|---------|-------|
| Feet-inches-fractions | `137'-1 1/2"` | Standard format; most common |
| Bracketed | `[137'-1 1/2 "]` | Advance Steel plan sheet convention for T.O.S. |
| Negative | `-5 13/16"` | Indicates a software data entry error (see Category 3) |
| Decimal feet | `116.104` | May appear in DWG text strings |
| Absolute elevation | `5516.10'` | Project survey elevation; requires datum conversion |

**Parsing algorithm for feet-inches-fractions:**

```
Pattern: (-?\d+)'[-\s](\d+)\s+(\d+)/(\d+)"
Groups:  (sign+feet) (whole_inches) (numerator) (denominator)
Value:   feet + (whole_inches / 12) + (numerator / denominator / 12)

Example: 137'-1 1/2"
= 137 + (1/12) + (1/2/12)
= 137 + 0.0833 + 0.0417
= 137.125 ft

Example: -5 13/16"
= -5/12 - 13/16/12  [negative feet-only value, no whole feet component]
= -0.417 - 0.068
= -0.484 ft  [clearly impossible for a Level 4 beam]
```

**Datum conversion for Amenity Steel:**

The Amenity Steel set established: Plan Elevation 5516.10' = MHMW (project) Elevation 100'-0"

Therefore: `MHMW elevation = absolute elevation − 5416.10`

This datum note appeared in the general notes on the C-series 3D view pages. A compliance system should extract and store this datum relationship for any project that defines one.

---

## 6. Section Size String Normalization

Before any section size comparison, normalize all strings using the following rules in order:

1. Convert to uppercase
2. Remove all whitespace
3. Replace Unicode × (U+00D7) with ASCII X
4. Remove any bracketed suffixes: `HSS5X5X1/4 [A]` → `HSS5X5X1/4`
5. Standardize fraction notation: `1/4` stays as `1/4`; do not convert to decimal

After normalization, the following pairs are equivalent and must not be flagged as mismatches:

| Raw String A | Raw String B | Normalized |
|-------------|-------------|------------|
| `W18x50` | `W18X50` | `W18X50` |
| `HSS5X5X1/4 [A]` | `HSS5X5X1/4` | `HSS5X5X1/4` |
| `W 18X50` | `W18X50` | `W18X50` |
| `hss6x6x3/8` | `HSS6X6X3/8` | `HSS6X6X3/8` |

The following pairs are **not** equivalent and must be flagged:

| String A | String B | Difference |
|---------|---------|------------|
| `W18X50` | `W18X55` | Weight/size difference — HIGH conflict |
| `HSS5X5X1/4` | `HSS5X5X3/8` | Wall thickness difference — HIGH conflict |
| `HSS6X6X3/8` | `HSS7X7X3/8` | Nominal size difference — HIGH conflict |

---

## 7. Member Identity Matching Strategy

Matching a member in the fabrication set to its counterpart in the DWG is non-trivial because the two documents use different identification systems. The following matching strategy was used in the Amenity Steel analysis and is recommended as a general approach:

**Step 1 — Exact mark match:** If the DWG contains explicit member marks (e.g., B23, C1), match directly to the same mark in the fabrication set. This is the most reliable method.

**Step 2 — Section-size-and-elevation match:** If the DWG does not use marks, match by section size and approximate elevation. A member in the DWG with section W18X50 at elevation ~137' should match the fabrication set member with section W18X50 at elevation 137'-1 1/2".

**Step 3 — Section-size-only match (for presence/absence checks):** If elevation data is unavailable, match by section size alone to determine whether a section type is represented at all in the fabrication set. This is sufficient for Category 2 (Member Absent from Fab Set) checks.

**Unmatched members:** Any section size in the DWG that cannot be matched by any of the three steps above should be flagged as a potential Category 2 conflict (Member Absent from Fab Set), pending scope confirmation.
