# KB-01 — Fabrication Design Document Structure and Anatomy

**Knowledge Base:** Steel Fabrication Compliance System  
**Document ID:** KB-01  
**Source:** Observed directly from `AmenitySteel.449.pdf` (46-page Advance Steel fabrication set, Mile High Metal Works, Inc., 2026). All structural claims are drawn from that document unless otherwise noted.  
**Status:** Verified against one real-world fabrication set. Patterns should be treated as representative, not exhaustive.

---

## 1. What a Fabrication Set Is

A structural steel fabrication set is the complete package of shop drawings issued by a steel fabricator to govern the cutting, drilling, welding, and assembly of all steel members before they leave the shop. It is the fabricator's interpretation of the engineer of record's (EOR) design drawings, translated into piece-by-piece manufacturing instructions.

The fabrication set is distinct from the structural design drawings (DWG/IFC/model) produced by the EOR. The design drawings define what must be built; the fabrication set defines how each piece will be manufactured. Conflicts between these two document sets are the primary target of a compliance system.

---

## 2. Standard Page Types Observed in a Fabrication Set

The following page types were observed in the Amenity Steel fabrication set. This structure is consistent with industry practice for Advance Steel-generated shop drawing packages.

| Page Code | Page Type | Content | Typical Page Size |
|-----------|-----------|---------|-------------------|
| Cover | Job Start Worksheet | Project metadata, member list, hardware schedule, vendor list | Letter (8.5" × 11") |
| C1, C2, … | 3D Isometric Views | Overall assembly views showing all members in position | Tabloid (11" × 17") |
| E1, E2, … | Framing Plan Sheets | Plan views per level showing member marks, section sizes, T.O.S. elevations, and dimensions | Tabloid |
| E4, E5, … | Typical Detail Sheets | Standard connection details (column base, beam-to-column, beam-to-beam) | Tabloid |
| F1 | Plate Schedule | All flat plates and miscellaneous items with dimensions, quantities, and supplier notes | Tabloid |
| F2, F3, … | Column Shop Drawings | Individual shop drawings per column mark | Tabloid |
| F8, F9, … | Beam Shop Drawings | Individual shop drawings per beam mark | Tabloid |
| F28, F29, … | Plate Detail Sheets | Detailed dimensioned drawings of each connection plate | Tabloid |

The Amenity Steel set used the following specific page coding convention:

- **C-series:** 3D assembly views (pages 2–3)
- **E-series:** Erection plans and details (pages 4–10)
- **F-series:** Fabrication shop drawings — plates, columns, beams (pages 11–46)

---

## 3. The Cover Sheet (Job Start Worksheet)

The cover sheet is the single most important administrative page in a fabrication set. In the Amenity Steel set it was titled **"Job Start Worksheet"** and contained the following fields, all of which are candidates for automated extraction and validation:

| Field | Description | Compliance Relevance |
|-------|-------------|----------------------|
| Job # / PO # | Internal job number and purchase order number | Links the fabrication set to a contract |
| Job Name | Project name | Cross-reference against DWG title block |
| Job Description | Scope description (e.g., "Amenity Steel") | Defines the scope boundary |
| Paint | Paint specification (e.g., "1HR Intumescent") | Must match spec section in contract documents |
| Fabrication Completion Date | Scheduled completion | Schedule compliance |
| Install Due Date | Scheduled field installation date | Schedule compliance |
| Install Hours | Estimated field installation labor hours | Budget reference |
| Member List | Two-column table listing every mark and section size in scope | **Primary compliance target** — all marks with shop drawings must appear here |
| Total Part Counts | Quantity and total linear footage | Must match count of individual shop drawings |
| Hardware Schedule | Bolt sizes, grades, and quantities | Must match connection details in E-series sheets |
| Vendor List | Suppliers (e.g., DenCol for plates, Metro, Platte Anchor) | Procurement tracking |

> **Key compliance rule derived from observation:** The cover sheet member list is frequently incomplete in practice. In the Amenity Steel set, 8 of 25 beam marks (B1, B2, B3, B4, B8, B11, B24, B25) had individual shop drawings and appeared on plan sheets but were absent from the cover sheet list. The total part count of 29 was therefore understated. A compliance system must treat the plan sheets and individual shop drawings as the authoritative member inventory, not the cover sheet.

---

## 4. Framing Plan Sheets (E-Series)

Framing plan sheets show the overhead view of each structural level. Each member shown on a plan sheet carries a **member mark label** in the format:

```
[Mark]  [Section Size]
[T.O.S. Elevation]
```

For example: `B23  W18X50 / [137'-1 1/2"]`

The bracket notation `[...]` around an elevation was used consistently in the Amenity Steel set to denote T.O.S. (Top of Steel) elevations on plan sheets. This is a common Advance Steel convention.

Each framing plan sheet is associated with a specific structural level. The level name appears in the drawing title block (e.g., "Level 3 Plan", "Level 4 Plan"). A member's level assignment is determined by which plan sheet it appears on, and this assignment must be consistent with its T.O.S. elevation.

**Elevation bands observed in the Amenity Steel set:**

| Level | T.O.S. Elevation Range | Base Reference |
|-------|----------------------|----------------|
| Level 2 (base / embed) | 116'-0" | Column base / embed plate |
| Level 3 | 126'-4 1/2" to 126'-6 1/2" | ~10'-5" above base |
| Level 4 | 136'-7 1/2" to 137'-1 1/2" | ~20'-7" above base |
| Top of tallest column | 137'-1 1/2" | C1 T.O.C. |

---

## 5. Individual Shop Drawings (F-Series)

Each structural member (column or beam) has its own shop drawing page. The shop drawing is the definitive manufacturing document for that piece. It contains:

- The **member mark** (e.g., B11) and **section size** (e.g., W10X22) in the title block
- The **length** of the member
- The **orientation** (e.g., "1 x West", "1 x South-West")
- All **connection plates** (with plate marks, dimensions, and weld symbols)
- **Hole patterns** for bolted connections
- **Weight** of the finished piece

> **Key compliance rule derived from observation:** The individual shop drawing is the ground truth for a member's section size and length. If a plan sheet annotation conflicts with a shop drawing, the shop drawing governs for fabrication purposes. The plan sheet annotation should be flagged for correction.

---

## 6. Plate Schedules (F1 and F28–F41)

Plate schedules list all flat plates used as connection hardware. In the Amenity Steel set, plates were divided into two categories:

- **DenCol plates** (p1001–p1030): Laser-cut connection plates ordered from an external supplier (DenCol). Each plate has a mark, quantity, material thickness, and dimensions.
- **In-house plates** (p1000): Embed plates fabricated in-house by the fabricator.
- **Miscellaneous items** (X1): Backer bars and other weld backing materials.

The plate schedule page (F1) also contains **procurement status notes**. In the Amenity Steel set, backer bar X1 carried the annotation "Did Not Order From DenCol" — a procurement flag with no resolution noted. A compliance system should scan plate schedule pages for unresolved procurement language.

---

## 7. Typical Detail Sheets (E4–E7)

Detail sheets show standard connection configurations that apply to multiple members. They do not reference specific member marks but instead define connection geometry by member type (e.g., "Typ. W16 @ Column Detail"). Elevations shown on detail sheets represent the T.O.S. for that connection type and serve as a cross-reference for plan sheet elevations.

In the Amenity Steel set, detail sheets confirmed the following T.O.S. values:
- W18 connections: 137'-1 1/2"
- W12 connections: 136'-9 13/16"
- W10 connections: 136'-7 1/2"
- Stub column connections: 126'-5 5/8"

These values can be used as a secondary validation source when plan sheet elevations are suspect.

---

## 8. 3D Isometric Views (C-Series)

The C-series pages show rendered 3D assembly views of the complete structure. They are primarily visual and do not contain member-level data beyond marks and section callouts. However, they do contain the project's **general notes**, which in the Amenity Steel set included:

1. Verify all column locations.
2. Verify all beam elevations.
3. All Simpson Hangers to be provided by others.
4. Provide sizes of all girder trusses that connect to steel.
5. Plan Elev 5516.10' = MHMW Elev 100'-0" (the project elevation datum).
6. Reference to typical detail pages (E4–E7).

The elevation datum note (item 5) is critical for any system that needs to convert between absolute elevation and project-relative elevation.

---

## 9. Member Mark Naming Conventions Observed

The Amenity Steel fabrication set used the following mark conventions, which are consistent with common Advance Steel practice:

| Prefix | Member Type | Example |
|--------|-------------|---------|
| C | Column (HSS or W-shape) | C1, C8, C13 |
| B | Beam (W-shape, C-shape, or HSS) | B1, B23, B25 |
| EP | Embed Plate assembly | EP1 |
| p | Connection plate (lowercase) | p1001, p1024 |
| X | Miscellaneous weld item | X1 |

> **Observed anomaly:** Column marks skipped C10, jumping from C9 to C11. This type of intentional gap — common when a member is removed during design development — is not self-documenting and should be flagged by a compliance system as requiring confirmation.

---

## 10. DWG File Structure (Advance Steel / AutoCAD)

The DWG file used in this analysis was an **AutoCAD AC1032 format** file created by **Advance Steel 2026** (Build 191). Key metadata extracted from the file:

| Field | Value |
|-------|-------|
| DWG Format Version | AC1032 (AutoCAD 2026) |
| Authoring Software | Advance Steel 2026, Build 191 |
| Creation Date | 2025-09-12 |
| Last Modified | 2026-04-02 |
| Last Modified By | dpauley |

The DWG contained 257 extractable text strings. Structural data was embedded as text entities within the drawing rather than as structured database records. This means extraction requires text parsing rather than schema-based querying.

The DWG used **[A]** and **[B]** type suffixes on column section sizes (e.g., `HSS5X5X1/4 [A]`) to distinguish connection configurations within the same section size. This typing system is not present in the fabrication set, which uses individual marks instead. The mapping between DWG type designations and fabrication marks must be established externally.
