# MHMW Fasteners and Typical Parts

MHMW's fastener-selection standard (which fastener goes into which substrate, and
how oversized to drill the hole) plus the shop's typical-part catalog and its
naming convention.

Sources: `Codes and Fasteners.pdf` (p. 4), `Typ. Footpad Drawings.PDF`, `Typical parts.pdf`.

---

## Fastener Selection by Substrate

**The fastener must match the substrate.** A detail calling out the wrong fastener
for its base material is a defect (e.g. a lag screw into concrete, or a Titen HD into
wood).

| Fastener | Fastens to | Hole oversizing | Notes |
| :--- | :--- | :--- | :--- |
| **Lag screw** | Wood | 1/16" – 1/8" oversized | — |
| **Simpson SDS screw** | Wood | 1/16" oversized | Only available in ¼" Ø |
| **Self-tapping / Tek screw** | Steel (steel-to-steel) | 1/16" oversized | — |
| **Simpson Titen HD anchor** | Concrete / masonry | 1/8" oversized | — |
| **Wedge anchor** | Concrete / masonry | 1/16" oversized | — |
| **Toggle bolt** | Drywall | 1/16" – 1/8" oversized | — |
| **Powder-actuated fastener (PAF)** | (shot into concrete/steel) | — | See abbreviations |

**Substrate → fastener quick map:**
- **Wood** → Lag screw *or* Simpson SDS (¼"Ø only)
- **Steel** → Self-tapping / Tek screw
- **Concrete / masonry** → Simpson Titen HD *or* Wedge anchor
- **Drywall** → Toggle bolt

**Clevis assembly with turnbuckle** — for tension rod runs; ordered by the overall
dimension (clevis-to-clevis). Can be ordered without the turnbuckle. Made of a rod
with threaded ends and a clevis at each end.

---

## Rail Attachment Hardware

| Part | Purpose | Notes |
| :--- | :--- | :--- |
| **Wall handrail bracket** | Attach wall handrail to wall | Flat and round top available — see Typ. Parts book |
| **Grab rail bracket** | Attach grab rail to guardrail | Flat and round top available |
| **Top saddle clip** | Attach top rail of guardrail to wall | Multiple variations |
| **Bottom saddle clip** | Attach bottom rail of guardrail to wall | Multiple variations |

---

## Typical Parts Catalog & Naming Convention

MHMW keeps a standard SolidWorks typical-parts library (`S:\Solidworks\Typ. Parts\`).
Parts are referenced by short codes on shop drawings. In `Typical parts.pdf`, drawing
number `F<N>` = PDF page N (F1–F25).

### Footpads / base plates — `FP` codes

The base plate is a `PL n×n×3/16`; post/leg placement is centered on the footpad.

| Code | Sheet | Plate | Substrate | Fastening |
| :--- | :--- | :--- | :--- | :--- |
| **FP3** | F1 | PL 3×3×3/16 | — | (post centered) — cane rail or wall-mounted guardrail |
| **FP42.3** | F2 | PL 4×4×3/16, (2) 5/16"Ø holes | **Wood** | (2) ¼"Ø SDS |
| **FP44.3** | F3 | PL 4×4×3/16, (4) 5/16"Ø holes | **Wood** | (4) ¼"Ø SDS |
| **FP42.5** | F2 | PL 4×4×3/16, (2) ½"Ø holes | **Concrete** | (2) ⅜"Ø Titen HD or lag bolt |
| **FP44.5** | F3 | PL 4×4×3/16, (4) ½"Ø holes | **Concrete** | (4) ⅜"Ø Titen HD or lag bolt |

> Reading the code: `FP<plate size><count>.<fastener>` — the `.3` suffix = ¼"Ø SDS
> (**wood** mount), `.5` = ⅜"Ø Titen HD / lag (**concrete** mount); the second digit is
> the fastener count. F2 states the substrate explicitly: "Mounting Material Typ.:
> Wood" (FP42.3) vs "Concrete" (FP42.5).

### Saddle clips — `SC` codes

Naming: `SC<tube size>.<fastener>` — `15` = 1½" tube, `2` = 2" tube; `.5` = (1) ⅜"Ø
lag / HD Titen + (2) ¼" Tek; `.3` = (2) ¼"Ø SDS + (2) ¼" Tek; `-B` = bottom clip.
Wall plate is 3½"×2"(or 2½")×3/16"; body is 16 ga. bent plate (top) / 11 ga. plates
(bottom).

| Code | Sheet | Description |
| :--- | :--- | :--- |
| **SC15.5** / **SC15.5-B** | F12/F13 | 1½" top / bottom saddle clip — (1) ⅜"Ø lag/HD Titen + (2) ¼" Tek |
| **SC15.3** / **SC15.3-B** | F14/F15 | 1½" top / bottom saddle clip — (2) ¼"Ø SDS + (2) ¼" Tek |
| **SC2.5** / **SC2.5-B** | F16/F17 | 2" top / bottom saddle clip — (1) ⅜"Ø lag/HD Titen + (2) ¼" Tek |
| **SC2.3** / **SC2.3-B** | F18/F19 | 2" top / bottom saddle clip — (2) ¼"Ø SDS + (2) ¼" Tek |
| **CSC** | F20 | Corner saddle clip — 16 ga. bent plate, (4) ¼"Ø SDS |

### Stringer connection plates & tread clips

| Code | Sheet | Description |
| :--- | :--- | :--- |
| **SPB** | F6 | Stringer Bottom Plate — 3"×3"×¼", slotted; (1) ½"Ø wedge anchor (concrete) or lag bolt (wood) |
| **SPT** | F6 | Stringer Top Plate — 7"×3"×½", (2) ⅞"Ø holes; (2) ¾"Ø lag bolt / HD Titen / through bolt (two-part sheet with SPB) |
| **TCS** | F7 | Typ. **weld-on** tread clip for **steel** stringer — L3×2×3/16, slotted holes |
| **TCW** | F8 | Typ. **bolt-on** tread clip for **wood** stringer — L3×3×3/16, slots + (2) 9/16"Ø bolt holes |

> The tread-clip choice follows the stringer material: **TCS welds to steel; TCW bolts
> to wood.**

### Rail mount brackets

- **WM-RD** (F4) — typical wall-mount bracket for pipe: (2) ¼"Ø×1" Tek + (1) ⅜"Ø lag or HD Titen.
- **GR-RD** (F5) — typ. guardrail mount bracket **for pipe**: Wagner P# S101 top on ½" sq. solid bar; (2) ¼"Ø×1" Tek.
- **GR-SQ** (F5) — typ. guardrail mount bracket **for sq./rect. tube**: PL 11 ga. top on ½" sq. solid bar; (2) ¼"Ø×1" Tek.
- **Top bent saddle — 1½" tube** (F9) — ⅛" pre-bent plate; (2) ¼"Ø SDS + (2) ¼"Ø Tek.
- **Bent bottom plate — 1½" tube** (F10) — ⅛" pre-bent plate; (2) ¼"Ø SDS + (2) ¼"Ø Tek.
- **Top bent saddle (face-mounted) — 1½" tube** (F11) — (2) ¼"Ø SDS + (2) ¼"Ø Tek.

### Gate hardware

- **4" HD hinge** (F21) — welded on, ¼" fillet 3 sides typ.
- **Typ. lock box** (F22) — ordered from Keedex; (2) 16 ga. U plates; 8" × 4½" × 1¾".
- **Typ. spring closure** (F23) — (4) ¼"Ø Tek screws; ordered part — *supplier part # is a
  `###` placeholder in the source; unresolved.*
- **Gravity latch + bar catch** (F24) — paired; (6) ¼"Ø Tek screws.
- **Cane bolt assembly** (F25) — 18"; (4) ¼"Ø Tek screws; ordered part — *supplier part #
  is a `###` placeholder in the source; unresolved.*

The full drawn catalog (25 pp.) is in `source-pdfs/Typical parts.pdf`; footpad details
(5 pp.) in `source-pdfs/Typ. Footpad Drawings.PDF`.
