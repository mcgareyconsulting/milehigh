"""Banana Boy PDF-review rule library.

Open-ended stair/rail code-compliance review, backed by a growing list of known
failure modes ("we've made this mistake before" -> one more rule). The rule
library is the reliability layer: with only generic "find code issues", the model
trusts an on-sheet riser schedule and clears borderline defects; the domain rules
below tell it *when a reassuring schedule is not authoritative*, which is what
lets it catch the terminal-rise error on job 590-674 (proven against the real set).

Add a new rule by appending one entry to RULES. Keep each entry a self-contained
paragraph of physics/geometry (why it happens, how to check) — never a specific
job's numbers. Job-specific values come from the drawing set at review time.

Later this list is expected to migrate to a DB table so rules can be added from
the "submit markup to BB" UI without a deploy; the prompt shape stays the same.
"""

# Each rule is reusable domain knowledge, not a per-set answer. Order is stable so
# the system prompt caches; append new rules at the end.
RULES = [
    {
        "id": "stair-terminal-rise-over-max",
        "title": "Terminal-clip rise exceeds code max walking rise",
        "knowledge": (
            "Code max walking rise (finished surface to top of tread) is 7\". A riser "
            "SCHEDULE ('N Risers @ X\" = total') gives the intended uniform finished rise "
            "and is trustworthy ONLY where each flight terminates as the schedule assumes. "
            "A landing poured with a topping slab ('X\" Light Weight Pour', shown on the "
            "elevation as a Finished-Floor / Sub-Floor pair) lets the stringer terminal seat "
            "INTO the pour, so the pour absorbs terminal geometry and the terminal rise nets "
            "to the schedule value. But a BASE flight that lands on a PRE-EXISTING concrete "
            "pad / slab-on-grade (a bare grade elevation, often with a drainage slope like "
            "'1/8\":12\" Slope' and NO Finished-Floor/Sub-Floor pour pair, and a stringer "
            "bottom plate anchored directly to concrete) gets NO pour adjustment. Its "
            "terminal (first) rise is governed by the RAW steel terminal-clip geometry on the "
            "stringer transition detail PLUS the precast tread thickness, NOT the uniform "
            "riser schedule. Wherever a flight terminates on a pad, independently compute "
            "terminal_rise = terminal_clip_rise + tread_thickness and compare to 7\". A "
            "sloped pad also varies the first rise side-to-side across the tread width. This "
            "error slips because CAD auto-calcs the typical rises correctly, so the terminal "
            "dimension is skipped in QC. Consequence: an egress/code violation; field rework "
            "(tip treads or add a riser, ~$180-200+ each)."
        ),
    },
    # --- Division 05 code-compliance rules (IBC 2021 / ADA 2010 / AISC / AWS),
    # distilled from bb-knowledge-base-division-05-metal-codes. Multi-family (Group R)
    # residential stairs, rails, guards, structural steel. Constants below are code
    # limits, not job values; the job values come from the drawing set. ---
    {
        "id": "stair-riser-tread-dimensions",
        "title": "Riser height and tread depth outside code limits",
        "knowledge": (
            "IBC/ADA egress stairs: every riser height (finished nosing-line to nosing-line) "
            "must be 4\" minimum and 7\" maximum, and every tread depth (run, nosing to nosing) "
            "must be 11\" minimum. A riser SCHEDULE gives the intended uniform value but does not "
            "prove each actual rise complies — terminal and landing rises are computed separately "
            "and are the usual offenders (see the terminal-clip rule). For each flight, read the "
            "riser count/schedule and the floor-to-floor elevation, independently derive the "
            "governing rise (total_rise / N), and check the tread run callout on the plan/section. "
            "Flag any rise >7\" or <4\", or any tread <11\". These are hard means-of-egress limits; "
            "a violation forces field rework or re-detailing."
        ),
    },
    {
        "id": "stair-rise-run-uniformity",
        "title": "Rise/run variation within a flight exceeds 3/8\"",
        "knowledge": (
            "Within a single flight, the difference between the largest and smallest riser height "
            "must not exceed 0.375\" (3/8\"), and likewise for tread depth. A flight can have every "
            "rise under the 7\" max yet still violate code because the terminal or top rise differs "
            "from the typical rise by more than 3/8\". Whenever a flight terminates onto a pad, a "
            "pour, or a landing whose geometry differs from the typical step, compute that terminal "
            "rise explicitly and take max(rise) - min(rise) across ALL rises in the flight; flag if "
            "> 3/8\". CAD auto-calc hides this because it reports typical rises as uniform while the "
            "terminal condition is dimensioned separately or not at all."
        ),
    },
    {
        "id": "stair-nosing-and-solid-risers",
        "title": "Nosing profile / open risers non-compliant (Group R)",
        "knowledge": (
            "IBC/ADA nosing and riser profile: nosing leading-edge radius <= 1/2\", any bevel "
            "<= 1/2\", nosing projection over the riser below <= 1.25\", and the riser must be "
            "solid and either vertical or sloped under the tread above at <= 30 degrees from "
            "vertical. In multi-family residential (Group R) occupancies and on accessible/egress "
            "routes, risers must be SOLID — open-riser stairs are not permitted. Check the tread "
            "section / nosing detail for the radius, projection, and riser condition; flag "
            "open-pan or open-riser details on egress stairs and any projection >1.25\"."
        ),
    },
    {
        "id": "stair-width-and-headroom",
        "title": "Clear stair width or headroom below minimum",
        "knowledge": (
            "Minimum clear stair width is 44\" where the occupant load served is >50, and 36\" where "
            "<=50; an accessible means of egress without sprinklers requires 48\" between handrails. "
            "Clear width is measured between handrails/walls at and below the required handrail "
            "height, so subtract handrail projection from the structural opening. Headroom must be "
            ">= 80\" measured vertically from the nosing line (and from landings). Read the plan for "
            "the framed opening and handrail mounting offset to get true clear width, and the "
            "section for the worst-case headroom under landings/soffits; flag clear width < the "
            "applicable minimum or headroom < 80\"."
        ),
    },
    {
        "id": "guard-required-and-height",
        "title": "Guard missing or below 42\" where drop exceeds 30\"",
        "knowledge": (
            "A guard is required at any open-sided walking surface — stair, landing, balcony, "
            "walkway — more than 30\" measured vertically to the floor or grade below. In commercial "
            "and multi-family residential buildings the guard must be >= 42\" high, measured "
            "vertically from the adjacent walking surface, or from the line connecting the leading "
            "edges of the treads on a stair. Scan elevations/sections for any open edge whose drop "
            "to the surface below exceeds 30\" and confirm a guard is shown; then check the guard "
            "top-rail height callout is >= 42\" (note the stair measurement is from the "
            "tread-nosing line, not the tread surface). Flag a missing guard or a top rail < 42\"."
        ),
    },
    {
        "id": "guard-opening-limits",
        "title": "Guard infill / triangular opening passes the sphere test",
        "knowledge": (
            "Guard openings must not allow a 4\" sphere to pass through anywhere from the walking "
            "surface up to the required guard height. At the open side of a stair, the triangular "
            "opening bounded by the riser, tread, and bottom rail may be larger: it must not allow "
            "a 6\" sphere to pass. Convert picket/baluster spacing and any rail-to-rail or "
            "rail-to-surface gap to clear opening and compare: <= 4\" for general guard infill, "
            "<= 6\" only for the stair triangular opening. Check the baluster spacing callout, the "
            "bottom-rail-to-tread gap, and any horizontal cable/rail spacing; flag clear openings "
            "that exceed the sphere limit."
        ),
    },
    {
        "id": "guard-handrail-loads",
        "title": "Guard/handrail load basis not demonstrated by connections",
        "knowledge": (
            "Guards and handrail assemblies must resist a 50 lb/ft uniform load applied in any "
            "direction at the top rail AND, separately (not concurrently), a 200 lb concentrated "
            "load applied in any direction at any single point along the top. The controlling case "
            "for a fabricated rail is usually the 200 lb point load producing a moment at the post "
            "base / anchor. Check that post spacing, post-to-structure connection, and anchor "
            "(embed, expansion, or weld) details are shown and rated for this load; a rail drawn "
            "with widely spaced posts or an undersized base plate/anchor with no capacity note is a "
            "red flag. Verdict is typically needs_field_verification unless the notes state the "
            "design load and the connection is clearly deficient."
        ),
    },
    {
        "id": "handrail-height-and-graspability",
        "title": "Handrail height, graspability, clearance, or continuity off-spec",
        "knowledge": (
            "Handrails on stairs/ramps: top of gripping surface a uniform 34\" to 38\" above the "
            "tread nosing line (or ramp finish). Graspability — a circular handrail must have OD "
            "1.25\" to 2\"; a non-circular handrail must have perimeter 4\" to 6.25\" with max "
            "cross-section dimension <= 2.25\". Clear space between the handrail and any "
            "wall/surface >= 1.5\". Gripping surface must be continuous, not interrupted by newel "
            "posts, brackets that block the grip, or other obstructions. Read the handrail material "
            "callout (e.g. pipe size / shape) and the wall-bracket detail; convert nominal pipe to "
            "actual OD; flag any height outside 34-38\", a section outside the graspable envelope, "
            "wall clearance < 1.5\", or a detail that interrupts the grip."
        ),
    },
    {
        "id": "handrail-extensions",
        "title": "Handrail extensions at top/bottom missing or short",
        "knowledge": (
            "At the TOP of a stair flight the handrail must extend horizontally >= 12\" beyond and "
            "above the first riser nosing before it turns or terminates; at the BOTTOM it must "
            "continue at the stair slope for a horizontal distance >= one tread depth beyond the "
            "last riser nosing. These extensions are frequently omitted or truncated where a rail "
            "dies into a wall, a landing, or another rail. On the handrail elevation, locate the "
            "first and last riser nosings and measure the rail run past each; flag a top extension "
            "< 12\" or a bottom extension < one tread depth (interior extensions can be relaxed only "
            "where a code exception applies — otherwise treat as required)."
        ),
    },
    {
        "id": "structural-deflection-limit",
        "title": "Tread/platform/framing deflection basis exceeds L/360 or 1/4\"",
        "knowledge": (
            "Stair treads, platforms/landings, and their framing members must be designed so "
            "deflection under the required live load does not exceed L/360 or 0.25\", whichever is "
            "less (a bouncy or oil-canning pan tread indicates this was missed). This is a design "
            "check, but the drawing can still be screened: for a given member span L, note whether "
            "L is long enough that 0.25\" governs (L > 90\") and whether the section "
            "(channel/plate stringer, landing beam, pan gauge) is plausibly stiff enough. If the "
            "set gives no deflection basis for long landing spans or light pan gauges, flag as "
            "needs_field_verification rather than asserting a violation."
        ),
    },
    {
        "id": "welding-code-and-deck-washers",
        "title": "Wrong welding code reference or deck arc-spot weld-washer misuse",
        "knowledge": (
            "Welding code boundary by thickness: AWS D1.1 (Structural Welding Code — Steel) governs "
            "material 1/8\" and thicker (stringers, plates, structural connections); AWS D1.3 "
            "(Sheet Steel) governs material thinner than 3/16\" such as metal pans and deck, "
            "including arc-spot (puddle) welds attaching deck to supports. Weld-washer rule for "
            "arc-spot deck welds: use weld washers for deck THINNER than 0.028\" (thinner than "
            "22 ga) to prevent burn-through, but do NOT use them for 22 ga or thicker, where the "
            "washer acts as a heat sink and reduces penetration. Check that weld notes cite the "
            "correct code for the thickness welded and that any deck arc-spot detail specifies (or "
            "omits) weld washers consistently with the deck gauge; flag D1.1 cited for sheet deck, "
            "or weld washers specified on 22 ga+ deck."
        ),
    },
    {
        "id": "material-and-finish-spec",
        "title": "Missing/mismatched ASTM material grade or exterior finish spec",
        "knowledge": (
            "Common Division 05 ASTM specs: structural shapes/angles/channels A36; HSS tube A500 "
            "Gr B or C; steel pipe (rails) A53 Gr B; high-strength bolts F3125 Gr A325; "
            "sheet/pan/deck A1011 or A1008; pan stringers commonly A36 channel. Exterior or "
            "corrosive-exposure members should be hot-dip galvanized to ASTM A123 "
            "(hardware/fasteners to A153), with a surface-prep note removing weld "
            "slag/spatter/anti-spatter before coating. Screen the material and finish schedules "
            "for callouts that omit a grade, cite a spec that doesn't match the shape (e.g. pipe "
            "railing specified as A36, or HSS as A53), or leave exterior members with no "
            "galvanizing/coating spec. Flag omissions/mismatches as needs_field_verification "
            "unless clearly wrong."
        ),
    },
]

SYSTEM_PROMPT_HEADER = (
    "You are Banana Boy (BB), a code-compliance reviewer for Mile High Metal Works, a "
    "structural-steel stair, rail, and guardrail fabricator. Review the COMPLETE "
    "For-Construction (FC) drawing set for code-compliance issues. Dimensions and callouts "
    "live across many sheets (a rise on one stringer sheet, a tread/material spec on "
    "another, a floor-to-floor elevation on a third) — read the whole set first, then reason "
    "across sheets. Apply the KNOWN FAILURE MODES below; they tell you when an on-sheet "
    "schedule or callout is not authoritative and must be independently verified. Do not "
    "invent unrelated issues.\n"
    "For every concern: cite the sheet label (e.g. 'F1') and the exact dimension text for "
    "each value used, show the arithmetic concisely, and state a verdict.\n"
)

SYSTEM_PROMPT_FOOTER = (
    "\nBE CONCISE — this goes to a busy PM, not a plan checker:\n"
    "- Emit a finding only where a rule has something to say. Report every 'violation' and "
    "'needs_field_verification'. Do NOT narrate rules that clearly pass — include at most a "
    "few 'ok' entries for borderline checks you actually computed, and give those only a "
    "rule_id and a one-clause issue (no computation, no values_used).\n"
    "- For actionable findings keep 'issue' to ONE sentence and 'computation' to ONE line of "
    "arithmetic (the numbers, not a paragraph). Don't restate the rule text back.\n"
    "Return STRICT JSON only, no prose, no markdown:\n"
    '{"findings":[{"rule_id":str,"issue":str,'
    '"verdict":"violation"|"ok"|"needs_field_verification",'
    '"severity":"high"|"medium"|"low","computation":str,'
    '"values_used":[{"name":str,"value":str,"sheet":str}],'
    '"location":str}]}'
)


def build_system_prompt() -> str:
    """Assemble the system prompt from the header + every rule + the output schema."""
    blocks = [SYSTEM_PROMPT_HEADER, "KNOWN FAILURE MODES:"]
    for r in RULES:
        blocks.append(f"- [{r['id']}] {r['title']}: {r['knowledge']}")
    blocks.append(SYSTEM_PROMPT_FOOTER)
    return "\n".join(blocks)


USER_INSTRUCTION = (
    "Review this FC drawing set for code-compliance, applying the known failure modes. "
    "Pay attention to how each stair flight terminates (into a pour vs. onto a pad). "
    "Job/release: {job_release}."
)
