# KB-03 — Data Schemas, Output Formats, and System Architecture

**Knowledge Base:** Steel Fabrication Compliance System  
**Document ID:** KB-03  
**Source:** All schemas and patterns in this document were derived from the actual data extracted from `AmenitySteel.449.pdf` and `AmenitySteel.dwg` during the Amenity Steel compliance analysis. No fields have been added speculatively.  
**Status:** Verified against one real-world project. Field names and structures are stable; additional fields should be added only when observed in future projects.

---

## 1. Core Data Model

The compliance system operates on three primary data objects. These were derived by observing what information was actually needed to detect and describe all 10 conflicts in the Amenity Steel analysis.

---

### 1.1 Project

The Project object holds metadata extracted from the cover sheet. It provides the context for all member and conflict records.

```json
{
  "project": {
    "job_number": "500",
    "po_number": "449",
    "job_name": "Brinkman - Novel Flatiron",
    "description": "Amenity Steel",
    "fabricator": "Mile High Metal Works, Inc.",
    "fabricator_address": "7399 Miller Court, Frederick, CO 80504",
    "paint_spec": "1HR Intumescent",
    "fab_completion_date": "2026-03-16",
    "install_hours": 101.28,
    "cover_sheet_piece_count": 29,
    "datum_note": "Plan Elev 5516.10' = MHMW Elev 100'-0\"",
    "base_elevation_ft": 116.0,
    "top_elevation_ft": 137.125,
    "source_pdf": "AmenitySteel.449.pdf",
    "source_dwg": "AmenitySteel.dwg",
    "dwg_format": "AC1032",
    "dwg_software": "Advance Steel 2026",
    "dwg_last_modified": "2026-04-02",
    "dwg_last_modified_by": "dpauley"
  }
}
```

---

### 1.2 Member

The Member object represents one structural member as extracted from the fabrication set. It is the primary unit of analysis.

```json
{
  "mark": "B23",
  "member_type": "beam",
  "section_pdf": "W18X50",
  "section_dwg": "W18X55",
  "length_inches": null,
  "length_string": "24'-3 13/16\"",
  "level": 4,
  "tos_elevation_string": "137'-1 1/2\"",
  "tos_elevation_ft": 137.125,
  "tos_elevation_valid": true,
  "orientation": "1 x South",
  "on_cover_sheet": true,
  "shop_drawing_page": 37,
  "plan_sheet_pages": [6],
  "conflicts": ["C-001"],
  "position_3d": { "x": -8.0, "y": 6.5, "z": 0.0 }
}
```

**Field notes:**

- `section_pdf` and `section_dwg` are both stored (pre-normalization) so the raw source values are preserved for display in reports.
- `tos_elevation_valid` is `false` when the elevation is negative, zero, or outside the project's valid elevation window.
- `level` is the integer level number derived from the plan sheet the member appears on.
- `position_3d` is an approximate 3D coordinate in a project-relative coordinate system, used for 3D visualization. Units are feet.
- `conflicts` is an array of conflict IDs that reference this member.

---

### 1.3 Conflict

The Conflict object is the primary output of the compliance system. Every detected discrepancy produces one Conflict record.

```json
{
  "id": "C-001",
  "severity": "HIGH",
  "category": "section_mismatch",
  "member_marks": ["B23"],
  "member_type": "beam",
  "pdf_value": "W18X50",
  "dwg_value": "W18X55",
  "pdf_pages": [6, 37],
  "description": "Section size mismatch: fabrication set shows W18X50; DWG shows W18X55.",
  "recommended_action": "Confirm correct section with EOR and revise the incorrect document before fabrication.",
  "check_type": "cross_document",
  "position_3d": { "x": -8.0, "y": 6.5, "z": 0.0 },
  "resolved": false,
  "resolution_note": null
}
```

**Field notes:**

- `category` must be one of the eight values defined in KB-02: `section_mismatch`, `member_absent_from_fab`, `impossible_elevation`, `level_assignment_conflict`, `designation_system_mismatch`, `cover_sheet_omission`, `mark_gap_undocumented`, `procurement_flag_unresolved`.
- `check_type` is either `cross_document` (requires both PDF and DWG) or `pdf_self_check` (requires only PDF).
- `member_marks` is an array because some conflicts affect multiple members simultaneously (e.g., C-008 affected 8 beam marks).
- `pdf_value` and `dwg_value` hold the raw extracted values that conflicted. For self-check conflicts where no DWG value exists, `dwg_value` is `null`.
- `resolved` and `resolution_note` support a workflow where conflicts are tracked through resolution.

---

### 1.4 Complete Conflict Record — All 10 Amenity Steel Conflicts

The following is the complete, verified conflict dataset from the Amenity Steel analysis. This serves as a ground-truth validation set for testing a compliance system implementation.

```json
[
  {
    "id": "C-001",
    "severity": "HIGH",
    "category": "section_mismatch",
    "member_marks": ["B23"],
    "pdf_value": "W18X50",
    "dwg_value": "W18X55",
    "pdf_pages": [6, 37],
    "check_type": "cross_document"
  },
  {
    "id": "C-002",
    "severity": "HIGH",
    "category": "member_absent_from_fab",
    "member_marks": [],
    "pdf_value": null,
    "dwg_value": "HSS7X7X3/8",
    "pdf_pages": [6],
    "check_type": "cross_document",
    "dwg_context": "Near framing mark F5 at elevation 88'-6\""
  },
  {
    "id": "C-003",
    "severity": "HIGH",
    "category": "impossible_elevation",
    "member_marks": ["B11"],
    "pdf_value": "-5 13/16\"",
    "dwg_value": null,
    "pdf_pages": [6, 44],
    "check_type": "pdf_self_check",
    "probable_correct_value": "136'-7 1/2\""
  },
  {
    "id": "C-004",
    "severity": "HIGH",
    "category": "impossible_elevation",
    "member_marks": ["B24"],
    "pdf_value": "-5 13/16\"",
    "dwg_value": null,
    "pdf_pages": [6, 45],
    "check_type": "pdf_self_check",
    "probable_correct_value": "136'-7 1/2\""
  },
  {
    "id": "C-005",
    "severity": "MEDIUM",
    "category": "section_mismatch",
    "member_marks": ["EP1"],
    "pdf_value": "116'-0\"",
    "dwg_value": "116'-1 1/4\"",
    "pdf_pages": [4],
    "check_type": "cross_document",
    "note": "Affects all 12 embed plates; 1.25\" discrepancy propagates through all column lengths"
  },
  {
    "id": "C-006",
    "severity": "MEDIUM",
    "category": "level_assignment_conflict",
    "member_marks": ["B9"],
    "pdf_value": "Shown on Level 3 Plan, T.O.S. = 136'-7 1/2\"",
    "dwg_value": null,
    "pdf_pages": [5, 6, 25],
    "check_type": "pdf_self_check"
  },
  {
    "id": "C-007",
    "severity": "MEDIUM",
    "category": "designation_system_mismatch",
    "member_marks": ["C1","C2","C3","C4","C5","C6","C7","C8","C9","C11","C12","C13"],
    "pdf_value": "Individual marks C1-C13",
    "dwg_value": "[A] and [B] type designations",
    "pdf_pages": [4],
    "check_type": "cross_document"
  },
  {
    "id": "C-008",
    "severity": "LOW",
    "category": "cover_sheet_omission",
    "member_marks": ["B1","B2","B3","B4","B8","B11","B24","B25"],
    "pdf_value": "Absent from cover sheet",
    "dwg_value": null,
    "pdf_pages": [1, 5, 6, 42, 43, 44, 45, 46],
    "check_type": "pdf_self_check"
  },
  {
    "id": "C-009",
    "severity": "LOW",
    "category": "mark_gap_undocumented",
    "member_marks": ["C10"],
    "pdf_value": "C9 → C11 (C10 absent, undocumented)",
    "dwg_value": null,
    "pdf_pages": [1],
    "check_type": "pdf_self_check"
  },
  {
    "id": "C-010",
    "severity": "LOW",
    "category": "procurement_flag_unresolved",
    "member_marks": ["X1"],
    "pdf_value": "Did Not Order From DenCol",
    "dwg_value": null,
    "pdf_pages": [11],
    "check_type": "pdf_self_check"
  }
]
```

---

## 2. Document Extraction Data Model

The following fields describe what must be extracted from each document type to support the conflict detection rules in KB-02.

### 2.1 Fields to Extract from the Fabrication Set PDF

| Field | Source Page Type | Extraction Method |
|-------|-----------------|-------------------|
| Project metadata (job #, name, date, etc.) | Cover sheet | Text extraction from table cells |
| Cover sheet member list (marks + sections) | Cover sheet | Table row parsing |
| Cover sheet piece count | Cover sheet | Numeric field |
| Hardware schedule (bolt sizes, grades, quantities) | Cover sheet | Table row parsing |
| Vendor list and procurement notes | Cover sheet | Text scan for vendor names |
| Member marks on plan sheets | E-series framing plans | Text entity extraction |
| Section sizes on plan sheets | E-series framing plans | Text entity extraction |
| T.O.S. elevations on plan sheets | E-series framing plans | Text entity extraction (bracket notation) |
| Level assignment per member | E-series framing plans | Page title + member position |
| T.O.S. values on detail sheets | E-series detail sheets | Text entity extraction |
| Plate marks, dimensions, quantities | F1 plate schedule | Table row parsing |
| Procurement flags on plate schedule | F1 plate schedule | Text scan for flag phrases |
| Member mark, section, length, weight | F-series shop drawings | Title block extraction |
| Connection plate marks on shop drawings | F-series shop drawings | Text entity extraction |
| General notes (including datum note) | C-series 3D views | Text block extraction |

### 2.2 Fields to Extract from the DWG File

| Field | Extraction Method |
|-------|-------------------|
| DWG format version | File header (bytes 0–5) |
| Authoring software and version | APPID or HEADER section |
| Creation and modification dates | HEADER section |
| Last modified by (username) | HEADER section |
| All text strings in the drawing | Text entity scan (UTF-16 LE for AC1032) |
| Section size strings | Filter text strings against known section size patterns |
| Elevation strings | Filter text strings against feet-inches-fraction pattern |
| Member marks (if present) | Filter text strings against mark pattern (letter + digits) |
| Column type designations ([A], [B]) | Filter text strings for bracket-suffix pattern |
| Framing marks (F1, F2, etc.) | Filter text strings for F + digit pattern |
| Grid line labels | Filter text strings for single/double letters and digits |

---

## 3. Output Formats

Three output formats were produced in the Amenity Steel analysis. Each serves a different audience.

### 3.1 Structured Conflict Report (Markdown / PDF)

The conflict report is the primary deliverable for the engineering and fabrication team. It contains:

- Executive summary with conflict counts by severity
- Full structural model (column schedule, beam schedule, embed plate schedule)
- One section per conflict with: conflict ID, severity, source comparison table, description, and recommended action
- Conclusion with prioritized resolution guidance

The report is generated from the Conflict data objects and Member data objects. It requires no additional data beyond what is in those schemas.

### 3.2 Red-Annotated PDF

The marked-up PDF is the primary deliverable for field use and RFI generation. It is the original fabrication set PDF with conflict annotations added directly to the affected pages.

**Annotation types used:**

| Annotation Type | When Used | Implementation |
|----------------|-----------|----------------|
| Revision cloud (dashed border) | Around the specific conflicting element | `draw_rect()` with `dashes="[4 2] 0"` |
| Callout box (filled rectangle + text) | Below or beside the conflict area | `draw_rect()` + `insert_textbox()` |
| Leader note (line + small box) | When space is tight near the conflict | `draw_line()` + small `draw_rect()` |
| Legend page | Appended as final page | `new_page()` + full conflict table |

**Color coding:**

| Severity | Border Color (RGB) | Fill Color (RGB) |
|----------|--------------------|------------------|
| HIGH | (0.85, 0.05, 0.05) — red | (1.0, 0.85, 0.85) — light red |
| MEDIUM | (0.80, 0.35, 0.00) — amber | (1.0, 0.93, 0.82) — light amber |
| LOW | (0.20, 0.40, 0.85) — blue | (0.88, 0.92, 1.00) — light blue |

**Coordinate system:** PyMuPDF uses points (1 pt = 1/72 inch) with origin at top-left. For tabloid landscape pages (1224 × 792 pts), the drawing area is approximately x: 40–1180, y: 40–720. The title block occupies y: 720–792.

**Page size reference:**

| Page Type | Width (pts) | Height (pts) | Paper Size |
|-----------|------------|-------------|------------|
| Cover sheet | 612 | 792 | Letter portrait |
| All other pages | 1224 | 792 | Tabloid landscape |

### 3.3 Interactive 3D Model

The 3D model is a supplementary deliverable for design review meetings. It shows all structural members in approximate position with conflict markers overlaid.

**Geometry approach:**

| Member Type | Geometry | Dimensions |
|-------------|----------|------------|
| HSS Column | `BoxGeometry` (vertical) | Width/depth ≈ HSS nominal size; height = member length |
| W-Shape Beam | `BoxGeometry` (horizontal) | Width ≈ flange width; height ≈ section depth; length = member length |
| Conflict marker | `SphereGeometry` (pulsing) | Radius = 0.3 ft; positioned at member centroid |

**Coordinate system:** Project-relative feet. X = east-west, Y = elevation, Z = north-south. Origin at the project's base elevation (116'-0" = Y:0).

**Interaction model:**
- Orbit, pan, zoom: standard Three.js OrbitControls
- Click conflict in list → camera flies to member (lerp animation over ~1 second)
- Click member in 3D → opens conflict detail panel
- Severity filter buttons toggle visibility of HIGH/MEDIUM/LOW markers

---

## 4. Technology Stack (Verified Working)

The following tools were confirmed working for the Amenity Steel analysis. Alternatives are noted where relevant.

| Task | Tool | Version | Install | Notes |
|------|------|---------|---------|-------|
| PDF reading and annotation | PyMuPDF (`fitz`) | 1.27.2 | `pip install pymupdf` | Reads and writes PDF annotations |
| DWG parsing (AC1032 / 2026) | Aspose.CAD | latest | `pip install aspose-cad` | Requires `libssl1.1` on Ubuntu 22.04 |
| DWG parsing (AC1015–AC1027) | ezdxf | latest | `pip install ezdxf` | Cannot read AC1032 format |
| 3D rendering | Three.js | r160+ | `pnpm add three @types/three` | Browser-based; no server required |
| Web framework | React 19 + Vite | latest | (template) | |
| Styling | Tailwind CSS 4 | latest | (template) | |

**Critical dependency note for Aspose.CAD on Ubuntu 22.04:**

Aspose.CAD requires `libssl1.1` which is not included in Ubuntu 22.04 by default (which ships with `libssl3`). The correct package must be downloaded and installed manually:

```
http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2_amd64.deb
```

Without this, Aspose.CAD will fail with a symbol lookup error for `ERR_put_error`.

**DWG format version reference:**

| AutoCAD Version | DWG Format Code |
|----------------|----------------|
| AutoCAD 2000–2002 | AC1015 |
| AutoCAD 2004–2006 | AC1018 |
| AutoCAD 2007–2009 | AC1021 |
| AutoCAD 2010–2012 | AC1024 |
| AutoCAD 2013–2017 | AC1027 |
| AutoCAD 2018–2022 | AC1032 |
| AutoCAD 2023–2026 | AC1032 |

ezdxf can read up to AC1027. AC1032 requires Aspose.CAD or the ODA File Converter.

---

## 5. Processing Pipeline Architecture

The following pipeline was validated in the Amenity Steel analysis. Each stage is independent and can fail without blocking subsequent stages that do not depend on it.

```
Stage 1: PDF Ingestion
  Input:  Fabrication set PDF
  Output: Structured member list, project metadata, elevation data, plate schedule
  Tool:   PyMuPDF (fitz)
  Fails:  If PDF is password-protected or image-only (no text layer)

Stage 2: DWG Ingestion
  Input:  DWG file
  Output: Section size strings, elevation strings, member marks (if present)
  Tool:   ezdxf (AC1015–1027) or Aspose.CAD (AC1032)
  Fails:  If DWG format is unsupported or file is corrupt
  Note:   Stage 2 failure does not block Stage 3 (PDF self-check)

Stage 3: PDF Self-Consistency Check
  Input:  Stage 1 output
  Output: Conflicts of categories 3, 4, 6, 7, 8
  Depends on: Stage 1 only

Stage 4: Cross-Document Comparison
  Input:  Stage 1 output + Stage 2 output
  Output: Conflicts of categories 1, 2, 5
  Depends on: Stage 1 AND Stage 2

Stage 5: Report Generation
  Input:  All conflict records + member data
  Output: Markdown/PDF conflict report
  Depends on: Stage 3 and/or Stage 4

Stage 6: PDF Markup
  Input:  Original PDF + all conflict records
  Output: Annotated PDF
  Depends on: Stage 1 + Stage 3 and/or Stage 4

Stage 7: 3D Model
  Input:  Member data + conflict records
  Output: Interactive Three.js visualization
  Depends on: Stage 1 + Stage 3 and/or Stage 4
```

---

## 6. Scope Boundary Determination

One of the most important and difficult problems in cross-document comparison is determining whether a member found in the DWG is within the steel fabricator's scope. The DWG for a building project will contain members from many trades and systems.

**Members that are within structural steel fabricator scope** (based on Amenity Steel observation):
- W-shapes (wide flange beams and columns): W10, W12, W14, W16, W18, W21, W24, etc.
- HSS sections (hollow structural sections): HSS5X5, HSS6X6, HSS7X7, HSS14X6, etc.
- C-shapes (channels): C10, C12, MC-series
- Embed plates and anchor rod assemblies

**Members that are NOT within structural steel fabricator scope** (observed in Amenity Steel DWG):
- LVL (laminated veneer lumber): `(3) 1 3/4"x18" LVL`, `(5) 1 3/4"x24" LVL`
- Dimensional lumber: `(3) 2X10`, `(3) 2X12`
- Premanufactured trusses: `PREMANUFACTURED TRUSS @ 24" O.C.`
- Cold-formed steel headers: `HDR-1`, `HDR-3`, `HDR-5`
- Shear walls: `SW6/35.0k/(7)`, `SW4/7.8k/(11)`, etc.

**Recommended scope filter:** Before running Category 2 checks (Member Absent from Fab Set), filter DWG text strings to retain only those matching structural steel section size patterns:
- W-shape: `W\d+X\d+`
- HSS: `HSS\d+X\d+X\d+(/\d+)?`
- Channel: `C\d+X\d+` or `MC\d+X\d+`
- Angle: `L\d+X\d+X\d+(/\d+)?`
- Plate: `PL\s*\d+/\d+"` or `\d+/\d+"\s*PL`
