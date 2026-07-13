"""Dry-run supplier-order scanner — see how an .eml would parse, no DB, no LLM.

Runs the DETERMINISTIC extractor routing over one or more .eml files (defaults to the
bundled fixtures) and prints the routing decision + the normalized order it would land
as a MaterialOrder — without touching the database or spending any tokens. Use it to
eyeball parser output while tuning the deterministic suppliers (Dencol, AZZ, Drexel).

Usage:
    python scripts/scan_orders.py                          # scan the fixtures dir
    python scripts/scan_orders.py path/to/order.eml ...    # scan specific files
    python scripts/scan_orders.py --json                   # dump the raw parsed dicts
    python scripts/scan_orders.py --llm                    # also allow the LLM fallback

Notes:
  - Deterministic only by default: the LLM fallback is OFF, so this is hermetic and
    free. Pass --llm to see what the fallback would recover for unmatched shapes.
  - The "routing preview" shows the domain signals the coming domain-router will key
    on (from/to/cc domains, supplier domain seen, inferred direction). Today's samples
    are forwarded copies (envelope From = the MHMW forwarder), so direction reads
    'forwarded' — the supplier domain lives in the quoted body, not the envelope.
"""
import argparse
import json
import os
import sys
from types import SimpleNamespace

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# Keep the dry-run output clean — suppress the app's INFO startup log line.
os.environ.setdefault("LOG_LEVEL", "ERROR")

DEFAULT_DIR = os.path.join(ROOT_DIR, "tests", "material_orders", "fixtures")


def _fmt(value):
    return "—" if value in (None, "") else str(value)


def _domains_of(addr_list):
    """The set of email domains in a payload address list ([{name, address}])."""
    out = []
    for a in addr_list or []:
        addr = (a.get("address") or "").lower()
        if "@" in addr:
            out.append(addr.split("@")[-1])
    return out


def _routing_preview(payload):
    """Best-effort read of the domain signals the domain-router will use."""
    from app.brain.material_orders import parser

    supplier_domains = parser.SUPPLIER_DOMAINS
    from_addr = ((payload.get("from") or {}).get("address") or "").lower()
    from_domain = from_addr.split("@")[-1] if "@" in from_addr else None
    to_domains = _domains_of(payload.get("to"))
    cc_domains = _domains_of(payload.get("cc"))

    # Which supplier domain appears, and where?
    seen = sorted(d for d in supplier_domains if d in (payload_text(payload).lower()))
    supplier_in_from = from_domain in supplier_domains
    supplier_in_recipients = any(d in supplier_domains for d in to_domains + cc_domains)
    if supplier_in_from:
        direction = "inbound (supplier is the sender)"
    elif supplier_in_recipients:
        direction = "outbound (we emailed the supplier)"
    elif seen:
        direction = "forwarded (supplier only in the quoted body)"
    else:
        direction = "unknown (no supplier domain)"

    return {
        "from_domain": from_domain,
        "to_domains": to_domains,
        "cc_domains": cc_domains,
        "supplier_domain_seen": seen,
        "direction": direction,
    }


def payload_text(payload):
    from app.brain.material_orders import parser
    return (payload.get("subject") or "") + "\n" + parser._html_to_text(
        payload.get("body"), payload.get("body_content_type")
    )


def _deterministic(record):
    """(extractor_name, parsed) for the first deterministic extractor that yields lines."""
    from app.brain.material_orders.extractors import classify

    for ex in classify.DETERMINISTIC:
        try:
            if not ex.matches(record):
                continue
            result = ex.extract(record)
        except Exception as exc:  # noqa: BLE001 — a broken extractor shouldn't stop the scan
            print(f"    ! {ex.NAME} raised: {exc}")
            continue
        if result and result.get("lines"):
            return ex.NAME, result
    return None, None


def _print_order(name, parsed):
    print(f"    matched extractor : {name}")
    contact = parsed.get("supplier_contact")
    supplier = _fmt(parsed.get("supplier"))
    print(f"    supplier          : {supplier}" + (f"  ({contact})" if contact else ""))
    print(f"    order_kind        : {_fmt(parsed.get('order_kind'))}")
    jr = (f"{parsed['job']}-{parsed['release']}"
          if parsed.get("job") is not None else "— (release-less)")
    print(f"    job-release       : {jr}")
    print(f"    PO                : {_fmt(parsed.get('po_number'))}")
    print(f"    supplier order #  : {_fmt(parsed.get('supplier_order_no'))}")
    print(f"    event / shipping  : {_fmt(parsed.get('event_type'))} / "
          f"{_fmt(parsed.get('shipping_status'))}")
    print(f"    ordered_at        : {_fmt(parsed.get('ordered_at'))}")
    print(f"    ready_at          : {_fmt(parsed.get('ready_at'))}")
    print(f"    ordered_by        : {_fmt(parsed.get('ordered_by'))}"
          + (f" <{parsed['ordered_by_email']}>" if parsed.get("ordered_by_email") else ""))
    lines = parsed.get("lines") or []
    print(f"    lines ({len(lines)}):")
    for ln in lines:
        qty = f"{ln['quantity']:g}" if ln.get("quantity") is not None else "—"
        bits = [b for b in (
            f"[{ln['finish']}]" if ln.get("finish") else None,
            f"${ln['unit_price']:g}/ea" if ln.get("unit_price") is not None else None,
        ) if b]
        print(f"      • qty {qty:>4}  {_fmt(ln.get('description'))}"
              + (f"   {' '.join(bits)}" if bits else ""))


def scan(paths, use_llm=False, as_json=False):
    from app.brain.material_orders.eml_adapter import eml_to_payload
    from app.brain.material_orders.extractors import llm

    results = []
    for i, path in enumerate(paths):
        payload = eml_to_payload(path)
        record = SimpleNamespace(id=i + 1, source="m365_mail", payload=payload)

        name, parsed = _deterministic(record)
        if parsed is None and use_llm:
            parsed = llm.extract(record)
            name = "llm" if parsed else None

        if as_json:
            results.append({"file": os.path.basename(path), "extractor": name,
                            "order": parsed})
            continue

        print(f"\n━━ {os.path.basename(path)}")
        rp = _routing_preview(payload)
        print(f"    routing preview   : from @{_fmt(rp['from_domain'])}"
              f" | to {rp['to_domains'] or '—'} | cc {rp['cc_domains'] or '—'}")
        print(f"                        supplier domain: {rp['supplier_domain_seen'] or '—'}"
              f" → {rp['direction']}")
        if parsed is None:
            print("    matched extractor : NONE (no deterministic match)"
                  + ("" if use_llm else " — re-run with --llm to try the fallback"))
            continue
        _print_order(name, parsed)

    if as_json:
        print(json.dumps(results, indent=2, default=str))


def _collect(paths):
    """Expand dirs to their .eml files; keep explicit files as-is."""
    out = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(os.path.join(p, f) for f in os.listdir(p)
                              if f.lower().endswith(".eml")))
        else:
            out.append(p)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Dry-run supplier-order scanner (no DB, no LLM).")
    ap.add_argument("paths", nargs="*", default=[DEFAULT_DIR],
                    help="An .eml file or a directory of them (default: the fixtures dir).")
    ap.add_argument("--llm", action="store_true", help="Allow the LLM fallback for unmatched shapes.")
    ap.add_argument("--json", action="store_true", help="Dump raw parsed dicts as JSON.")
    args = ap.parse_args()

    scan(_collect(args.paths), use_llm=args.llm, as_json=args.json)
