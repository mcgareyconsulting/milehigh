# Knowledge Base: Recovery Methodology and QA Protocols
**Domain:** Fabrication Design Document Compliance System
**Author:** Manus AI

This document distills the methodologies for developing recovery plans when fabrication errors are detected, as well as the Quality Assurance (QA) protocols required to verify the accuracy of a compliance model.

## 1. Recovery Methodology for Overage Columns

When columns are fabricated too long, they must be cut to the required length in the field. The recovery plan must dictate *where* to cut the column (top or bottom) based on the structural connection details at each end.

### Decision Matrix: Top Cut vs. Bottom Cut

The system should evaluate the base and top connections of each overage column to determine the optimal cutting method. The goal is to minimize field welding of complex or critical connections.

**1. Bottom Cut Method (Preferred)**
- **Condition:** The column base sits on a flat embed plate (e.g., EP-1) or a simple base plate without complex anchor bolt patterns, AND the drawing notes explicitly allow field trimming (e.g., "Trim Excess In Field").
- **Rationale:** The top connection (cap plates, shear tabs) is often shop-welded and complex. Cutting the bottom preserves the integrity of the shop-welded top connection.
- **Execution:** Crane-pick the column, cut the required amount from the base, re-set, and re-weld to the embed plate.

**2. Top Cut Method**
- **Condition:** The column has a heavy, shop-welded base plate (e.g., 3/4" thick) designed to fit over a specific anchor bolt pattern.
- **Rationale:** Removing and re-welding a heavy base plate in the field risks heat distortion, which could prevent the plate from fitting back over the anchor bolts. It is safer to leave the base intact and cut the column shaft from the top.
- **Execution:** Leave the base anchored, cut the column shaft at the new required height, and field-weld the cap plate and shear tabs at the correct elevation.

## 2. QA Protocols for Compliance Models

A compliance system must implement rigorous QA protocols to verify its internal model of the structure before flagging fabrication errors. False positives (flagging a correct piece as an error) undermine trust in the system.

### Verification Checklists

The system should perform the following verification checks against the drawing data:

**1. Grid Span Verification**
- **Action:** Calculate the distance between all major grid lines in the model.
- **Validation:** Verify that these calculated distances exactly match the cumulative dimension chains shown on the slab or foundation plans.

**2. Key Beam Span Verification**
- **Action:** Calculate the span distance of several key continuous beams (e.g., main girders spanning across multiple bays).
- **Validation:** Verify that these calculated spans match the fabricated lengths of those beams (accounting for setbacks) found in the shop drawings. If the beam spans match, the column grid coordinates are highly likely to be correct.

**3. TOS Elevation Verification**
- **Action:** Extract the Top of Steel (TOS) elevations assigned to each framing level in the model.
- **Validation:** Cross-reference these elevations against the explicit callouts on the framing plans and section views. Ensure that the system is correctly interpreting whether the TOS refers to the top of the beam or the top of the column.

**4. Anchor Point and Rotation Verification (for Sub-structures)**
- **Action:** Verify the global coordinates of the anchor point for any rotated or offset sub-structures (e.g., Area 2-3).
- **Validation:** Confirm that the rotation angle and anchor point coordinates align with the overall plan and local dimension chains.

### Handling Discrepancies

If any of the QA verification checks fail, the system must halt the compliance analysis and flag the model for review. A failed grid span or beam span check indicates a fundamental error in the system's interpretation of the drawing coordinates, rendering any subsequent fabrication error flags unreliable.
