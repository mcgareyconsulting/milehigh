# Knowledge Base: Fabrication Compliance Rules
**Domain:** Fabrication Design Document Compliance System
**Author:** Manus AI

This document distills the core compliance rules and data standards required for verifying fabricated steel members (columns and beams) against structural design drawings.

## 1. Column Fabrication Compliance

The primary compliance check for columns is verifying that the fabricated length matches the required length derived from the structural elevations.

**Rule:** A column is compliant if its fabricated length equals the calculated required length, within an acceptable erection tolerance (e.g., ± 1/8").

### Required Length Calculation

The required length is the distance from the base elevation to the top of the column.
- **Base Elevation:** The elevation of the concrete foundation, embed plate, or lower-level framing where the column is anchored.
- **Top Elevation:** The elevation of the column cap plate, shear tab, or top flange connection.

**Calculation:**
> `Required Column Length = Top Elevation − Base Elevation`

If the column supports a beam that sits on top of its cap plate (a common framing condition), the Top Elevation must be calculated from the Top of Steel (TOS) of that beam:
> `Top Elevation = TOS Elevation − Beam Depth (d)`

### Non-Compliance Categorization

When a column's fabricated length does not match the required length, it falls into one of two non-compliant categories:

**1. Fabricated Too Long (Overage)**
- **Condition:** Fabricated Length > Required Length.
- **Impact:** The column will push the supported framing above the required TOS elevation.
- **Resolution:** The column must be cut in the field to the required length. The system must calculate the exact "Cut Amount" (`Fabricated Length − Required Length`).

**2. Fabricated Too Short (Underage)**
- **Condition:** Fabricated Length < Required Length.
- **Impact:** The column will not reach the required TOS elevation, leaving a gap below the supported framing.
- **Resolution:** The column cannot be corrected by simply cutting. It requires an extension (shim plates or a spliced section) or complete replacement. The system must flag these columns for an immediate Request for Information (RFI) to the Engineer of Record (EOR).

## 2. Beam Span Verification

The primary compliance check for beams is verifying that the fabricated length matches the physical distance between its connection points on the supporting columns or girders.

**Rule:** A beam is compliant if its fabricated length matches the span distance calculated from the grid coordinates of its endpoints, accounting for connection setbacks.

### Span Distance Calculation

The span distance is the straight-line distance between the (X, Y) coordinates of the beam's endpoints.
- **Endpoints:** The grid coordinates of the columns or girders the beam connects to.

**Calculation:**
> `Span Distance = √((X2 − X1)² + (Y2 − Y1)²)`

### Setback Accounting

Beams rarely span the full distance between column centerlines. They are typically fabricated slightly shorter to allow for connection clearances (setbacks).
- **Setback:** The distance from the column centerline to the end of the beam.
- **Calculation:** The expected fabricated length is the span distance minus the setbacks at both ends.

**Compliance Checks:**
- The system must calculate the span distance from the structural grid.
- The system must determine the expected setback based on the connection type (e.g., shear tab, double angle, seated connection) and the supporting member's dimensions.
- The system must verify that the fabricated length equals the span distance minus the total setback. Discrepancies indicate an incorrect fabricated length or an incorrect endpoint assignment in the compliance model.

## 3. Data Standards and Sources

A compliance system must pull data from specific sources within the drawing set to perform accurate verifications.

| Data Element | Source Drawing Type |
|---|---|
| Base Elevations | Foundation Plans, Slab Plans, Embed Plans |
| TOS Elevations | Framing Plans, Elevations, Sections |
| Column Grid Locations | Slab Plans, Anchor Bolt Plans |
| Beam Endpoints | Framing Plans |
| Beam Sections (Sizes) | Framing Plans, Beam Schedules |
| Fabricated Lengths | Shop Drawings (Fabrication Details) |
| Connection Types | Connection Details, Typical Details |
| Beam Depths ($d$) | AISC Steel Construction Manual |
