# Knowledge Base: Structural Drawing Interpretation
**Domain:** Fabrication Design Document Compliance System
**Author:** Manus AI

This document distills key principles and rules for interpreting structural steel drawings (plans, elevations, and details) to ensure compliance between design intent and fabrication data.

## 1. Top of Steel (TOS) vs. Column Height

A fundamental principle in structural steel interpretation is the distinction between the Top of Steel (TOS) elevation and the actual fabricated length of a column.

**Rule:** The TOS elevation called out on a framing plan typically refers to the top flange of the horizontal beam framing into or sitting upon the column, not the top of the column itself.

**Calculation Formula:**
To determine the required fabricated length of a column from plan elevations:
> `Required Column Length = TOS Elevation − Base Elevation − Beam Depth`

**Compliance Checks:**
- The system must identify the specific beam section (e.g., W14x22) framing over the column cap plate.
- The system must subtract the exact AISC tabulated depth ($d$) of that beam section from the TOS elevation to find the required column top elevation.
- A common error in manual interpretation is assuming `Column Top = TOS`, which results in columns being fabricated too long by exactly the depth of the beam.

## 2. Dimension Chains and Grid Coordinates

Structural drawings rely on cumulative dimension chains rather than absolute global coordinates. A compliance system must translate these chains into a unified coordinate system to verify spans and endpoint connections.

**Rule:** Column and beam endpoint positions must be derived by walking the dimension chains from a known global origin (e.g., Grid intersection W/30), not by estimating from plan visuals.

**Compliance Checks:**
- **Grid Offsets:** Columns are frequently offset from main grid lines (e.g., a column marked at Grid X may actually be dimensioned 7 1/4" away from Grid W). The system must parse the specific dimension string, not just the nearest grid bubble.
- **Local vs. Global Grids:** Sub-structures (e.g., "Area 2-3") often have local grid systems (e.g., Grids D, E, F, G) that are rotated and offset from the main building grid. The system must locate the anchor point and rotation angle from the overall plan to translate local coordinates into global coordinates.

## 3. Instance Mapping for Piece Marks

A single piece mark (e.g., C10 or B14) often represents multiple identical physical pieces in the structure.

**Rule:** A compliance system cannot assume a 1:1 mapping between a piece mark and a spatial location. It must map every *instance* of a piece mark to its specific grid coordinates.

**Compliance Checks:**
- When verifying beam spans, the system must not look up "the coordinates of C10" if there are five C10s. It must determine *which* C10 instance the beam connects to based on the framing plan visuals or callouts.
- Failure to perform instance mapping results in false span errors, where the system attempts to calculate a span between two unrelated locations sharing the same piece mark.

## 4. Notes and Exceptions

Text notes on drawings often override standard orthogonal assumptions.

**Rule:** The system must parse and apply structural notes regarding orientation, rotation, and field modifications.

**Examples:**
- **"No Perpendicular Grid Lines Present"** — Indicates a skewed or rotated sub-structure. The system must trigger an angle calculation protocol.
- **"Trim Excess In Field"** — Explicitly authorizes field modification (cutting) of specific components (e.g., column bases on flat embed plates), which dictates the permissible recovery methodology when fabrication errors occur.
