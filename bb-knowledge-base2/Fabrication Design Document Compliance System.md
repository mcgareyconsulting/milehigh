# Fabrication Design Document Compliance System
**Knowledge Base Master Index**
**Author:** Manus AI

This knowledge base contains distilled rules, methodologies, and data standards derived from real-world structural steel compliance and recovery operations. These modules are designed to serve as context for an automated fabrication design document compliance system.

## Core Modules

### 1. [Structural Drawing Interpretation](kb_drawing_interpretation.md)
*File: `kb_drawing_interpretation.md`*
- Top of Steel (TOS) vs. Column Height definitions
- Formula for required column length calculation
- Translating dimension chains into global grid coordinates
- Handling local vs. global grids and structural rotation
- Instance mapping for piece marks
- Parsing structural notes and exceptions

### 2. [Fabrication Compliance Rules](kb_fabrication_compliance.md)
*File: `kb_fabrication_compliance.md`*
- Column fabrication compliance (Required vs. Fabricated length)
- Overage vs. Underage column categorization and impact
- Beam span verification using grid coordinates
- Accounting for connection setbacks in span calculations
- Required data standards and drawing source mapping

### 3. [Recovery Methodology and QA Protocols](kb_recovery_and_qa.md)
*File: `kb_recovery_and_qa.md`*
- Decision matrix for field recovery (Top Cut vs. Bottom Cut)
- Evaluating base connections and anchor bolt constraints
- Rigorous QA protocols for compliance models
- Grid span, key beam span, and TOS elevation verification checklists
- Handling discrepancies and preventing false positives

---
*Note: These modules are intended to be ingested by an LLM or rules engine to guide the automated analysis of structural drawings (PDFs/IFCs) against fabrication shop drawings or cut lists.*
