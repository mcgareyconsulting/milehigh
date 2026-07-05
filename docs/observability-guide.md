# Observability & Logging: A Field Guide for milehigh

A deep-dive on how to think about logs/telemetry as the system grows, how to feed
signal into the Brain, and where our current setup sits. Written to be re-read.

---

## 0. The one reframe to start with

Stop thinking "logging." Start thinking **telemetry**: structured records about what
the system did, emitted so a *machine* can query them later, not so a *human* can read
them scroll by. The moment you internalize that, most decisions fall out of it:
messages become events with fields, "levels" matter less, and "is this line readable
in the terminal" stops being the design goal.

The industry has been on a 15-year march from **logs → structured logs → wide events**.
We are currently at "structured logs, unevenly applied." The target is wide events. The
rest of this doc is about why, and how to get there without boiling the ocean.

---

## 1. The three kinds of telemetry (and the debate about them)

Classic model — the **"three pillars":**

- **Logs** — discrete timestamped records of "something happened." Cheap to emit,
  expensive to store and query at volume. Good for *narrative* ("what happened in this
  one request").
- **Metrics** — pre-aggregated numbers over time (counters, gauges, histograms). Tiny
  and cheap because they're aggregated at write time. Good for *trends and alerts*
  ("error rate over the last hour"). **Cannot** carry high-cardinality data like a
  user_id (that would explode the number of time series).
- **Traces** — a request's path across services/functions, as a tree of timed spans.
  Good for *"where did the time go / where did it break"* across async boundaries.

The critique (Charity Majors / Honeycomb, "Observability 2.0"): three pillars means
**three copies of the same truth in three tools**, and the relationships between them
get "ripped apart." You pay to store the same event as a log, a metric, and a trace,
and you still can't ask a question you didn't predefine. Their answer: **one source of
truth — arbitrarily-wide structured events per request** — from which logs, metrics,
and traces can all be *derived*. You keep the raw high-cardinality event; you compute
aggregates at read time instead of throwing away detail at write time.

You don't have to pick a camp today. The practical takeaway that's true in *both*
camps: **emit rich structured events; put as much context on each as you can; don't
pre-shred your data into un-joinable pieces.**

---

## 2. The distinction we are currently blurring — and it's the important one

There are **two completely different streams** that both happen to be called "logs,"
and conflating them is the root of most confusion (including "should we stream logs to
the Brain?"):

### A. Operational telemetry
For *operators / debugging*. "This webhook took 800ms," "the outbox retried 3×,"
"this request 500'd with this stack trace." High volume, mostly disposable, sampled
when hot, tunable by level/env. Audience: us, at 2am, when something's broken.

### B. Domain / business events
For *the product and the Brain*. "Submittal 1234 moved to Closed," "release entered
Complete zone," "PM assigned." Low(er) volume, **durable, must-not-lose**, schema'd,
often the source of truth for a feature. Audience: the application, the audit trail,
and eventually an agent reasoning over the business.

**We already do (B) correctly and don't fully realize it.** `ReleaseEvents` /
`SubmittalEvents` with payload-hash dedup, the outbox tables, `JobChangeLog` — that's a
domain-event store. It's event sourcing in spirit. That is the thing the Brain should
consume.

**The mistake to avoid: piping operational logs (stream A) into the Brain.** Raw app
logs are noisy, unstructured-ish, full of retries and debug chatter, and semantically
shallow ("HTTP 200 on /brain/jobs"). An agent reasoning over that will drown. What the
Brain wants is stream B — curated, meaningful, entity-anchored domain events ("release
X shipped," "submittal Y is 4 days overdue"). We already have the table shape for it.

So the honest answer to *"how do we stream logs to the brain"* is: **you mostly don't
stream logs — you stream events.** Build/lean on the domain-event layer (B), give it
stable schemas and entity anchors (job/release/submittal/GC — the Hive Mind spine),
and let the Brain subscribe to *that*. Operational logs (A) go to an observability
backend for humans, on a separate pipe. More on both pipes in §6.

---

## 3. The formatting answer: canonical log lines / wide events

This is the single most valuable pattern to adopt for stream A, and it directly answers
"how do I format outputs as the system grows."

**Canonical log line** (Stripe's term; "wide event" is the modern name): instead of
scattering 8 log lines across a request, you emit **exactly one fat structured event
per unit of work** (per HTTP request, per webhook, per scheduled job), containing
everything you'd want to know about it:

```
event=request_complete method=GET path=/brain/jobs status=200 duration_ms=42
  user_id=17 rows_returned=0 since_present=true trello_locked=false
  db_ms=31 request_id=a1b2c3 release_count=0
```

Why this wins as you scale:

- **Correlation, not just visibility.** Everything about the request is on one row, so
  you query `path=/brain/jobs status>=500 duration_ms>1000` in one shot — no stitching
  lines together at 2am. Stripe/Brandur are explicit that the real power is correlation.
- **Cheap for the machine.** One wide row aggregates and retrieves far faster than
  N narrow lines the backend has to join.
- **One line per request = predictable volume.** Volume scales with *requests*, not
  with how chatty a given code path is. (Contrast our current webhook paths that emit
  4–12 lines each.)

**How you implement it:** a request-scoped accumulator (Flask `g` or a
`structlog.contextvars` bound dict) created in `before_request`; middleware and business
logic *add fields* to it as work happens (`ctx["db_ms"] = ...`, `ctx["rows"] = ...`);
`after_request`/`teardown` emits the single event. Wrap the emit so it fires even on
exception (Stripe logs it in an `ensure`/`finally` block so a thrown error still
produces the line). Debug-level narrative logs can still exist for deep dives, off by
default — but the canonical line is the backbone.

**logfmt vs JSON:** logfmt (`key=value key=value`) is human-skimmable and grep-able;
JSON is universal and nests. For us, **JSON to stdout in prod** (machines/Render/agents
consume it) is the right default; logfmt is a nicety for local dev. We already render
JSON via structlog — the gap is (a) it's one-line-per-event not one-per-request, and
(b) the console handler double-wraps it (see §7 / the cleanup branch).

**Stable field names are a contract.** `user_id` is always `user_id`, never also
`uid`/`user`/`userId`. Stripe eventually codified theirs in a protobuf schema. We don't
need protobuf, but we should keep a short list of canonical field names and reuse them.
OpenTelemetry **semantic conventions** (§5) give us that vocabulary for free.

---

## 4. What matters, what doesn't, what we're missing

### Matters a lot
- **Structure** (fields, not f-strings). `logger.info("submittal_created",
  submittal_id=…, project=…)` — queryable. Our `meetings`/`lake` code already nails this.
- **One event per unit of work** (canonical line, §3).
- **High cardinality on events** — put the ids on (user, release, submittal, request).
  Cardinality is *the* thing that makes debugging possible ("which user, which release").
- **Correlation / request id** on every line, propagated across async hops.
- **Errors are sacred** — never suppress/sample a non-2xx or an exception. Volume cuts
  apply to the success path only.
- **Runtime-tunable level** (env), so you can turn up detail in prod without a deploy.
  (Just added: `LOG_LEVEL`.)
- **Cost awareness** — log volume is a bill and a signal-to-noise ratio. Volume must
  scale with *activity*, never with *reader/user count* (our poll-endpoint problem).

### Doesn't matter much
- **Pretty console formatting in prod.** Nobody reads raw stdout at scale; a machine does.
- **Log *levels* as your primary tool.** Useful as a coarse dial, but Majors' point
  stands: reaching for "should this be info or debug" a hundred times is a smell. A wide
  event with a `status`/`error` field you can filter on beats level discipline. Levels
  are a crutch; structure is the fix.
- **Perfect prose in messages.** The event *name* + fields carry meaning; the sentence
  doesn't need to be beautiful.
- **Chasing every debug line to zero.** Debug is fine when it's off by default.

### What we're missing (the "don't know what you don't know" list)
- **Correlation IDs are effectively absent.** `SyncContext`/`log_sync_operation` exist
  but are *never called*; no `before_request` binds a request id. So today you cannot
  reconstruct one request's or one webhook's full story. This is the highest-leverage gap.
- **No metrics at all.** We have zero RED/Golden-Signal instrumentation (§5). We can't
  answer "what's the webhook error rate" or "outbox queue depth over time" without
  grepping logs. Metrics are cheap and we have none.
- **No tracing across async boundaries.** Our hardest-to-debug paths are exactly the
  async ones: webhook → threadpool → sync → outbox → Procore. A trace id propagated
  through those would turn "grep and guess" into one waterfall view.
- **No sampling strategy.** It's currently all-or-nothing per level. Hot paths should be
  sampled (log 1-in-N), not just demoted.
- **PII / secret governance is ad hoc.** We literally shipped a DB-credential leak in a
  startup log. There's no redaction layer, no policy on what fields are safe to emit.
- **No retention/tier thinking.** All logs are treated the same; audit/business events
  (durable, cheap, keep for years) vs debug logs (voluminous, keep for days) should live
  in different tiers with different costs.

---

## 5. The monitoring-signals canon (what to actually measure)

Three named recipes, all worth knowing. They're about **metrics**, the pillar we're
missing entirely.

- **Google's Four Golden Signals** (SRE book): **Latency, Traffic, Errors, Saturation.**
  If you instrument only four things on a user-facing service, these. Latency must split
  success vs failure (a fast 500 lies to you).
- **RED** (Tom Wilkie) — for request-driven services: **Rate, Errors, Duration.** The
  per-endpoint version of the golden signals. This is the one to apply to our HTTP
  routes and webhook handlers first.
- **USE** (Brendan Gregg) — for resources: **Utilization, Saturation, Errors.** For
  hosts/queues/pools. Our outbox queue depth, threadpool saturation, and DB pool are
  textbook USE targets.

Mapped to us: RED on `/brain/*` routes and the Trello/Procore webhook handlers; USE on
the outbox queue (depth = saturation), the `ThreadPoolExecutor(max_workers=10)`, and the
APScheduler pool. Emit these as real metrics (Prometheus client or StatsD) — then the
poll-endpoint noise *becomes a metric* (a request counter) and disappears from logs
entirely, which is the correct end state for it (§4: it's a metric, not a log).

---

## 6. Streaming telemetry — the architecture (two pipes)

### Pipe A — operational telemetry → an observability backend (for humans)
```
app (structured JSON to stdout)
  → collector/agent (OTel Collector | Vector | Fluent Bit)
      → backend (Grafana Loki | ClickHouse | Honeycomb | our Postgres)
```
On **Render** specifically: the app writes structured JSON to stdout; Render captures it;
use a **log drain** (or run a collector as a sidecar/worker) to ship it somewhere
queryable. Don't try to query logs in the Render dashboard forever — it doesn't scale and
has no real query language.

The collector choices (all mature; pick by need):
- **OpenTelemetry Collector** — the universal, vendor-neutral, multi-signal (logs +
  metrics + traces) pipeline. Heavier (~100–300MB under load) but it's the strategic bet
  (§8). If we're going to add metrics and traces anyway, standardize here.
- **Vector** (Datadog, Rust) — fast, efficient, great transformation/routing language;
  logs+metrics. Excellent if we want a lightweight router into our own Postgres/ClickHouse.
- **Fluent Bit** (C, ~5–10MB) — the featherweight forwarder; ubiquitous at the node/edge
  layer. Overkill-avoidant if we just need to move bytes.

### Pipe B — domain events → the Brain (for the product/agent)
This is *not* the same pipe and shouldn't reuse the observability backend. It's:
```
domain event written (ReleaseEvents / SubmittalEvents / a new EventOutbox)
  → durable store / event log (we already have the tables)
      → Brain / Banana Boy subscribes, reasons, anchors to entities
```
The Brain should read **stream B**, not stream A. If you want the Brain to be aware of
operational health too (e.g., "Procore sync has been failing for an hour"), the clean
way is: compute that from **metrics/SLOs** (pipe A) and emit a *domain event* ("integration_degraded")
into pipe B — i.e., promote a meaningful operational condition into a first-class event
the agent can reason about. Don't hand the agent the raw log firehose.

**Rule of thumb:** logs and metrics are for humans and dashboards; *events* are for the
product and the agent. Convert, don't cross the streams.

---

## 7. Our current state, honestly

- **Good bones:** structlog is configured; `meetings`/`lake` already emit clean
  structured events; we have a real domain-event store (`*Events` tables, dedup hashing,
  outbox); `LOG_LEVEL` is now env-tunable; the gunicorn access-log noise filter exists.
- **Rough edges (being addressed on `chore/logging-cleanup`):** the console handler wraps
  structlog's already-rendered JSON in a plaintext formatter (double timestamps/levels);
  ~48% of logger calls are f-strings (un-queryable); 5 modules bypass structlog with
  stdlib logging; ~700 `print()` calls on runtime paths that ignore levels entirely.
- **Strategic gaps (not yet touched):** no correlation IDs (dead `SyncContext`), no
  metrics, no tracing, no sampling, no redaction policy, no log→event distinction wired
  into how we feed the Brain.

---

## 8. A maturity ladder for us (in order)

1. **Uniformity** — finish the cleanup branch: one JSON format to stdout, kill the
   double-render, migrate stray stdlib loggers, convert hot-path `print()`s. *(in progress)*
2. **Correlation** — `before_request` binds a `request_id` (and user id) via
   `structlog.contextvars`; propagate it into the Trello/Procore worker threads and the
   outbox. Suddenly every line is joinable. *(highest leverage, small effort)*
3. **Canonical log lines** — one wide event per request/webhook/job (§3). Demote the
   narrative lines to debug. Volume drops, query power jumps.
4. **Metrics** — add RED on routes+webhooks and USE on the queues/pools (§5). Move the
   poll endpoints from logs to counters. Now you can alert.
5. **A pipeline** — pick a collector (OTel Collector if we're committing to the standard;
   Vector if we want a lean router into our own store) and a backend; set up a Render log
   drain. Stop living in the dashboard.
6. **Tracing** — OpenTelemetry spans across the async boundaries (webhook→threadpool→
   outbox→Procore). This is where the hardest bugs currently hide.
7. **Event → Brain** — formalize the domain-event stream (schema, entity anchors) as the
   thing the Brain subscribes to; promote operational conditions into events rather than
   feeding raw logs. *(ties into Hive Mind / Banana Boy)*

**OpenTelemetry is the strategic bet** underneath 4–6. Instrument once with the OTel SDK
+ semantic conventions and you can route logs, metrics, and traces to *any* backend
without re-instrumenting, and you get automatic trace↔log correlation (a log emitted
inside a span carries the trace/span id). If we're adding metrics and traces anyway,
standardizing on OTel avoids three bespoke integrations.

---

## 9. Reading list (annotated thought leadership)

**Start here — the wide-events / canonical-log-lines core (most directly useful to us):**
- Brandur Leach, *Using Canonical Log Lines for Online Visibility* — the definitive
  practitioner write-up. https://brandur.org/canonical-log-lines
- Brandur Leach, *Canonical Log Lines 2.0* — updated thinking. https://brandur.org/nanoglyphs/025-logs
- Stripe Engineering, *Fast and flexible observability with canonical log lines* —
  the source. https://stripe.com/blog/canonical-log-lines

**The observability-2.0 / wide-events argument (the "why"):**
- Honeycomb, *There Is Only One Key Difference Between Observability 1.0 and 2.0* —
  the single-source-of-truth thesis. https://www.honeycomb.io/blog/one-key-difference-observability1dot0-2dot0
- Honeycomb, *The Cost Crisis in Observability Tooling* — why three pillars is a bill
  you can't sustain. https://www.honeycomb.io/blog/cost-crisis-observability-tooling
- Charity Majors, *charity.wtf* (observability 2.0 tag) — the primary voice.
  https://charity.wtf/tag/observability-2-0/
- *Observability: the present and future* (Pragmatic Engineer, interview w/ Majors) — a
  good long-form orientation. https://newsletter.pragmaticengineer.com/p/observability-the-present-and-future
- Book: **Majors, Fong-Jones & Miranda, *Observability Engineering* (O'Reilly)** — the
  canonical text; read if you read one thing cover to cover.

**Foundational monitoring (the metrics canon):**
- Google SRE Book, *Monitoring Distributed Systems* — origin of the Four Golden Signals.
  https://sre.google/sre-book/monitoring-distributed-systems/
- RED method (Tom Wilkie) & USE method (Brendan Gregg) — request-side and resource-side
  recipes. Good overview: https://betterstack.com/community/guides/monitoring/sre-golden-signals/
- Cindy Sridharan, *Distributed Systems Observability* (free O'Reilly report) + her blog
  (copyconstruct) — the clearest logs-vs-metrics-vs-traces explainer written.

**Standards & tooling (the "how to ship it"):**
- OpenTelemetry — Logs concepts: https://opentelemetry.io/docs/concepts/signals/logs/
- OpenTelemetry — Semantic Conventions (your field-name vocabulary):
  https://opentelemetry.io/docs/concepts/semantic-conventions/
- Collector comparisons: OTel Collector vs Fluent Bit (SigNoz)
  https://signoz.io/comparisons/opentelemetry-collector-vs-fluentbit/ ; and a 2026
  Kubernetes log-collector benchmark incl. Vector
  https://victoriametrics.com/blog/log-collectors-benchmark-2026/

---

*The through-line: emit structured events, one wide one per unit of work, with ids and a
correlation key on every one; send operational telemetry to a real backend for humans and
curated domain events to the Brain for the product; add metrics for trends and traces for
async debugging; and treat OpenTelemetry as the standard you instrument against once.*
