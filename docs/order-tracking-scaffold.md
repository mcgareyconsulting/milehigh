# Order Tracking — Full-Stack Scaffold (living plan)

Status: **scaffold / not yet built.** This is the high-level shape we align on before
wiring mechanics. Daniel steers the details (parsers, keyword maps, UI) as we go deeper.

## The pivot in one paragraph

Move supplier-order handling from *LLM-reads-every-email* to **deterministic,
domain-routed parsing** for known suppliers (Dencol, AZZ Denver / "AZZDEN", Drexel),
with the LLM demoted to an opt-in fallback for *unknown* domains only — to cut token
spend. Track the **whole lifecycle loop** (we place an order → supplier confirms →
supplier says ready → picked up / received) by linking the emails of one **conversation
thread** into one order record. Surface each order in three places: the canonical
`MaterialOrder` row, a **rollup on the Release**, and a **card on the shipping-planning
timeline lane** — and **notify** the shipping person on the key transitions.

## Target flow (the loop)

```
  MHMW → Dencol   "here's our order"  (CC bb@mhmw.com)
        └─ BB: create MaterialOrder (state=placed, ordered_at=today),
                 link to release, drop a card on the shipping lane
  Dencol → MHMW   "order is ready for pickup"   (reply, same thread)
        └─ BB: match by conversation → advance SAME order to state=ready,
                 update release rollup, move the lane card, NOTIFY shipping
  (later)         "picked up" / "received"      → state=closed, card leaves the lane
```

Plus the shortcut case: **a bare order confirmation** arrives with no prior outbound —
create the order directly at `confirmed`/`ready`.

## Core principles

1. **Domain over subject/body.** Route by the sender/recipient **email domain**, not by
   matching words in the subject or body. Suppliers are uniform at the domain level.
2. **Direction from domains.** Supplier domain in **From** → inbound (a status/confirm).
   Supplier domain in **To/Cc** → outbound (we placed it). This is the whole classifier.
3. **Thread = order.** One `conversation_id` groups the outbound order + all replies into
   ONE order lifecycle. Replies **update**, never duplicate.
4. **Deterministic-first.** Known domains never touch the LLM. LLM is a flag-gated
   fallback for unregistered domains only, with a per-call cost log.
5. **Never fudge a Releases row.** Releases is the app's heart (Trello/scheduling/DWL/PM
   board/submittal-match/BB-chat/undo all sweep it). Order state lives on `MaterialOrder`;
   the release only gets a *computed rollup* and the timeline is a *read-model union*.

## What already exists (build on, don't reinvent)

- **Ingestion:** `bb@mhmw.com` mailbox → `app/lake/ingest/m365_mail.py` poll →
  `RawSourceRecord`. Payload already carries `from`, `to`, `cc`, `conversation_id`,
  `internet_message_id`, `received_at`, `sent_at`. Everything routing + chaining needs.
- **Once-only scan marker:** `RawSourceRecord.material_order_scanned_at`.
- **Parsers today:** `app/brain/material_orders/extractors/` (drexel_inline, dencol_confirm,
  dencol_drawing, azz_galvanizing, dencol_stock) + `classify.py` (tries each shape) + the
  LLM fallback. These become the *internals* of the per-supplier adapters below.
- **Records:** `MaterialOrder` (now with `order_kind` + `shipping_status`), `Releases`,
  `Notification` (in-app bell). Reuse.

## Proposed module layout

Under `app/brain/material_orders/` (keep the package; broaden it):

```
suppliers/
  base.py        SupplierAdapter: DOMAINS, parse(record, direction) -> OrderEvent
  dencol.py      folds dencol_confirm + dencol_drawing + dencol_stock + inbound status
  azz.py         folds azz_galvanizing (structured status block)
  drexel.py      folds drexel_inline
routing.py       domain+direction detection, supplier resolution, conversation key
lifecycle.py     state machine: (current_state, OrderEvent) -> (new_state, side_effects)
service.py       upsert order by conversation key; write release rollup; project + notify
events.py        append-only OrderEvent audit (dedup by internet_message_id)  [recommended]
notifications.py dispatch on transition (in-app now; email/Teams later)
extractors/llm.py  DEMOTED: unregistered domains only, flag-gated, cost-logged
```

`classify.py`'s "try every extractor" loop is replaced by `routing.py`: resolve supplier
by domain → hand the record to that one adapter. Deterministic and cheap.

## Data model deltas (to reconcile as we build)

**`MaterialOrder`** — add:
- `conversation_id` (thread linkage key; the upsert key for the loop)
- `direction` ('outbound' | 'inbound')
- `lifecycle_state` ('placed' | 'confirmed' | 'ready' | 'closed' | 'needs_review')
- `delivery_method` ('pickup' | 'ship' | 'deliver' | …)
- milestone dates: `ordered_at` (have it), `confirmed_at`, `ready_at`, `closed_at`
- Reconcile: `shipping_status` (planning/complete) becomes a *derived* 2-value view of
  `lifecycle_state`; `order_kind` stays (material/galvanizing/stock).

**`Release` rollup** — prefer **computed** (query MaterialOrders for (job, release):
open count, latest state, next milestone date) exposed in the release payload. Add a
denormalized `material_order_state` column ONLY if the list/timeline needs cheap
filter/sort without a join — decide when we hit it.

**`OrderEvent`** (recommended, mirrors `ReleaseEvents`) — append-only row per email that
touches an order, keyed/deduped by `internet_message_id`. Gives the loop a real audit
trail and makes replays idempotent.

## Lifecycle state machine (deterministic)

| Trigger (deterministic signal)                          | From → To            | Side effects |
|---------------------------------------------------------|----------------------|--------------|
| Outbound email to supplier domain                       | — → placed           | create order, ordered_at, parse delivery_method, drop lane card |
| Inbound confirmation / order confirm                    | placed → confirmed   | set confirmed_at |
| Inbound "ready for pickup" / AZZ "Ready to Ship"        | confirmed → ready    | ready_at, move lane card, **notify shipping** |
| Inbound "shipped" / "picked up" / "received" / "complete" | ready → closed     | closed_at, card leaves lane |
| Bare confirmation, no prior outbound                    | — → confirmed/ready  | create order directly |
| Known domain, unrecognized phrase                       | keep state           | flag `needs_review` (NO LLM) |

Per-supplier keyword/status maps live in each adapter (AZZ ships a structured status
block; Dencol is free-text phrases). We tune these together against real samples.

### Supplier notes (confirmed against samples)

- **AZZ (AZZDEN, `@azz.com`, sender `AZZGalvDEN@azz.com`).** Match = domain `@azz.com`,
  then a deterministic pass for **`Customer PO xxx-yyy`** in the body — the six-digit
  (job `xxx` / release `yyy`) is the job-release link. Verified the sample is NOT a PDF:
  it's an HTML `<table>` (plus a plain-text twin), so the PO is real text in both bodies —
  no OCR needed. The AZZ adapter anchors on the `Customer PO` label (a decoy PO-like token
  elsewhere can't hijack it) and falls back to attached-PDF text for the contingency where
  a future notification carries the block only as a PDF. The one shape this can't recover
  is an inline *image*-only PO (would need OCR) — not seen in current samples.
  `AZZ Job` = AZZ's own six-digit order # (the per-galv-job upsert key).

## Notification loop

On transition into `ready` (and optionally `closed`):
- In-app `Notification` (existing bell) to the shipping role/user(s), `type='order_status'`.
- Later: outbound email / Teams ping to the shipping person.
- Needs: who is "shipping" — a role flag on `User`, or a configured recipient list?

## Build phases (sequencing)

- **A. Routing + adapters** — `routing.py` (domain+direction+conversation key) + supplier
  adapters returning `OrderEvent`; keep persisting MaterialOrder as today. *Deletes the
  subject/body guessing; proves domain routing on the three suppliers.*
- **B. Lifecycle + model** — state machine, MaterialOrder deltas, `OrderEvent` audit,
  upsert-by-conversation. *The loop becomes real.*
- **C. Release rollup + modal** — computed rollup in the release payload + JobDetailsModal
  "Orders" section with lifecycle status.
- **D. Shipping timeline lane** — read-model union (MaterialOrders + release ship
  milestones) → day buckets; lifecycle drives card lane/color. No Releases rows.
- **E. Notifications** — dispatch on transition; wire the shipping recipient.
- **F. Demote LLM** — registry-first; LLM only for unregistered domains, flag + cost log.

## Open questions (Daniel steers)

1. **"Attach BB" mechanism** — CC vs BCC vs dedicated forward on outbound orders? Confirms
   the outbound copy lands in `bb@mhmw.com` with usable From/To for direction detection.
2. **Shipping recipient** — in-app bell only to start, or email/Teams too? Role vs named user?
3. **Release rollup** — computed-only, or a denormalized state column for cheap filtering?
4. **`shipping_status` vs `lifecycle_state`** — collapse into one field (lifecycle) and
   derive the lane's 2-value view? (Recommended.)
5. **Delivery-method taxonomy** — pickup / ship / deliver / freight? Per supplier.
6. **OrderEvent audit** — append-only stream (recommended) or just mutate the row?
7. **Package rename** — keep `material_orders/`, or rename to `orders/` as scope broadens?
```
