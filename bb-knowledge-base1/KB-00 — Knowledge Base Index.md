# KB-00 — Knowledge Base Index

**System:** Steel Fabrication Design Document Compliance  
**Version:** 1.0  
**Date:** April 18, 2026  
**Derived from:** Amenity Steel compliance analysis (AmenitySteel.449.pdf vs. AmenitySteel.dwg)  
**Prepared by:** Manus AI

---

## What This Knowledge Base Is

This knowledge base contains the distilled, reusable knowledge extracted from a real-world structural steel fabrication compliance analysis. Every rule, schema, pattern, and example in these documents was observed directly in actual project files — nothing has been assumed or inferred beyond what the documents explicitly demonstrated.

The intended use is as a **context engine** for a fabrication design document compliance system. Each document in this knowledge base addresses a distinct layer of the system and can be loaded independently as context for an AI agent, a rules engine, or a developer implementing the system.

---

## What This Knowledge Base Is Not

This knowledge base does not contain:

- Rules derived from AISC, AWS, NISD, ASTM, or any other industry standard (those were not consulted during the source analysis)
- Rules inferred from general engineering knowledge not demonstrated in the source files
- Project-specific data from the Amenity Steel project (that data lives in the project files and the handoff document)
- Claims about what a fabrication set "should" contain beyond what was observed in one real example

If a future version of this knowledge base is expanded with industry standard citations, each new rule must be clearly tagged with its source.

---

## Document Index

| File | Title | What It Covers |
|------|-------|----------------|
| `KB-00_Index.md` | This file | Navigation, scope, and usage guide |
| `KB-01_Document_Structure.md` | Fabrication Document Structure and Anatomy | Page types, cover sheet fields, framing plan conventions, shop drawing contents, DWG file structure |
| `KB-02_Conflict_Detection_Rules.md` | Conflict Categories, Detection Rules, and Severity Framework | All 8 conflict categories, detection algorithms, severity criteria, elevation parsing, section size normalization, member matching strategy |
| `KB-03_Data_Schemas_and_Architecture.md` | Data Schemas, Output Formats, and System Architecture | JSON schemas for Project/Member/Conflict objects, complete Amenity Steel conflict dataset, output format specs, technology stack, processing pipeline, scope boundary determination |

---

## How to Use This Knowledge Base as Context

### For an AI agent performing compliance analysis:

Load KB-01 first to establish document structure recognition. Load KB-02 to apply conflict detection rules. Load KB-03 for output formatting. The Amenity Steel conflict dataset in KB-03 Section 1.4 serves as a validation reference.

### For a developer building the compliance system:

KB-03 Section 5 (Processing Pipeline Architecture) defines the implementation sequence. KB-02 Section 3 defines the eight detection functions. KB-03 Section 1 defines the data schemas. KB-01 Section 3 defines the cover sheet fields to extract.

### For a rules engine:

Each conflict category in KB-02 Section 3 is a self-contained rule with: a definition, a detection algorithm, a severity assignment, and a verified real-world example. Rules can be implemented independently.

---

## Key Facts Established by the Source Analysis

The following facts were directly observed and are not assumptions. They are the most important inputs for any system built on this knowledge base.

**Document relationship:** A fabrication set PDF and a structural DWG describe the same structure from different perspectives. The PDF governs manufacturing; the DWG governs design intent. Conflicts between them require resolution by the Engineer of Record before fabrication proceeds.

**Cover sheet reliability:** The cover sheet member list is not a reliable inventory of all members in scope. In the observed example, 8 of 25 beam marks were absent from the cover sheet despite having individual shop drawings. Plan sheets and shop drawings are the authoritative member inventory.

**Elevation format:** Advance Steel fabrication sets express elevations in feet-inches-fractions notation with bracket delimiters on plan sheets: `[137'-1 1/2"]`. Negative values (e.g., `-5 13/16"`) indicate a software data entry error, not a valid below-grade elevation.

**DWG text encoding:** Advance Steel 2026 DWG files (AC1032 format) store text strings in UTF-16 Little Endian encoding. Standard ASCII string extraction will miss most text content. The Aspose.CAD library is required for reliable extraction from AC1032 files.

**Section size normalization:** Section size strings must be normalized before comparison (uppercase, no spaces, ASCII X for ×, no bracket suffixes). The strings `W18X50` and `W18X55` are not equivalent and represent a HIGH severity conflict.

**Scope boundary:** Not all section sizes in a structural DWG belong to the steel fabricator's scope. Wood members (LVL, dimensional lumber), cold-formed headers, and premanufactured trusses appear in the same DWG as structural steel and must be filtered out before scope comparison.

**Two-check architecture:** PDF self-consistency checks (requiring only the PDF) and cross-document checks (requiring both PDF and DWG) must be implemented as independent functions. Self-checks should produce results even when DWG parsing fails.

---

## Amenity Steel Ground Truth Reference

The following conflict counts from the Amenity Steel analysis serve as a validation benchmark for any implementation of this knowledge base:

| Check Type | Conflicts Found | Severity Breakdown |
|------------|----------------|-------------------|
| PDF self-check only | 6 | 2 HIGH, 1 MEDIUM, 3 LOW |
| Cross-document (PDF + DWG) | 4 | 2 HIGH, 2 MEDIUM |
| **Total** | **10** | **4 HIGH, 3 MEDIUM, 3 LOW** |

A correctly implemented compliance system applied to the Amenity Steel files should reproduce all 10 conflicts. The complete conflict dataset is in KB-03 Section 1.4.
