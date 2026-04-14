# Danny OS: Automated Bug Ingestion + Agent Fix Pipeline

## Context

The Board (bug tracker) currently only supports in-app notifications via @mentions. When a bug or feature request is created, the developer has to manually check the UI. Danny OS is an agentic pipeline that automatically:
1. Detects new bugs/features/comments on The Board
2. Runs AI triage (lightweight analysis + proposed fix)
3. Sends a Slack notification with the triage
4. Lets the developer click "Fix It" to invoke a Claude Code agent that implements the fix on a branch

The existing codebase has strong patterns to build on: outbox + retry, event sourcing with dedup, APScheduler + daemon worker threads, webhook handling.

---

## Pipeline Flow

```
BoardItem/BoardActivity created or updated
  -> DannyOSOutbox record (stage: pending)
  -> danny_os_worker picks it up
  -> Claude Sonnet API triage (summary, proposed fix, relevant files, confidence)
  -> Slack Bot posts Block Kit message with triage + [Fix It] button
  -> Developer clicks "Fix It" in Slack
  -> Slack interaction webhook -> AgentRun record (status: queued)
  -> agent_worker picks it up
  -> Claude Code CLI runs on a feature branch
  -> Results posted back to Slack thread + BoardActivity comment
```

---

## New Models (`app/models.py`)

### DannyOSOutbox
Follows `TrelloOutbox`/`ProcoreOutbox` pattern. Tracks the full triage-to-notification pipeline.

| Column | Type | Purpose |
|--------|------|---------|
| id | Integer PK | |
| board_item_id | FK -> board_items | The bug/feature that triggered this |
| board_activity_id | FK -> board_activity (nullable) | The specific comment, if applicable |
| trigger_type | String(50) | `new_item`, `new_comment`, `status_change`, `priority_change` |
| stage | String(30) | `pending` -> `analyzing` -> `notifying` -> `completed` (or `failed`) |
| ai_summary | Text (nullable) | One-paragraph triage |
| ai_proposed_fix | Text (nullable) | Proposed solution approach |
| ai_relevant_files | Text (nullable) | JSON array of file paths |
| ai_confidence | String(20) (nullable) | `high`, `medium`, `low` |
| slack_message_ts | String(50) (nullable) | For updating the Slack message |
| slack_channel_id | String(50) (nullable) | |
| retry_count | Integer, default=0 | |
| max_retries | Integer, default=3 | |
| next_retry_at | DateTime (nullable) | |
| error_message | Text (nullable) | |
| created_at / completed_at | DateTime | |

### AgentRun
Tracks Claude Code agent invocations, always gated behind human approval (Slack button).

| Column | Type | Purpose |
|--------|------|---------|
| id | Integer PK | |
| outbox_id | FK -> danny_os_outbox | Links to the triage that spawned this |
| board_item_id | FK -> board_items | |
| status | String(30) | `queued` -> `running` -> `completed`/`failed` |
| branch_name | String(200) | e.g. `danny-os/board-42-login-500` |
| prompt | Text | The full prompt sent to Claude Code |
| stdout | Text (nullable) | Agent output (truncated to ~10k chars) |
| files_changed | Text (nullable) | JSON array of changed file paths |
| commit_sha | String(40) (nullable) | |
| pr_url | String(500) (nullable) | |
| error_message | Text (nullable) | |
| approved_by | String(100) (nullable) | Slack user who clicked "Fix It" |
| started_at / completed_at / created_at | DateTime | |

---

## New Services

### `app/services/danny_os_service.py` — Orchestrator
- **`enqueue(board_item_id, board_activity_id=None, trigger_type)`** — creates `DannyOSOutbox` record, called from board routes after commit
- **`process_pending(limit=5)`** — picks up pending outbox items, runs triage -> Slack pipeline, handles retries with exponential backoff (mirrors `OutboxService.process_item()`)
- **`create_agent_run(outbox_id, approved_by)`** — creates `AgentRun` record from Slack interaction
- **`process_agent_queue(limit=1)`** — picks up queued agent runs, executes one at a time

### `app/services/ai_triage_service.py` — Claude API Analysis
- Uses `anthropic` Python SDK, calling **Claude Sonnet** (fast + cheap for triage)
- Prompt includes: bug title/body/comments, project context doc, quick grep results for keywords from the bug
- System prompt instructs structured JSON output: `{summary, proposed_fix, relevant_files, confidence}`
- Uses prompt caching on the project context block (static across calls)

### `app/services/slack_service.py` — Slack Bot Integration
- Uses `slack-sdk` Python package with Bot Token auth
- **`send_triage(outbox_item)`** — posts Block Kit message with triage results + action buttons
- **`post_agent_result(outbox_item, agent_run)`** — threaded reply with fix results (files changed, PR link)
- **`send_simple_notification(board_item, event_type)`** — plain text for non-AI events (status changes, low-priority)

### `app/services/agent_execution_service.py` — Claude Code Agent Runner
- Creates a git branch `danny-os/board-{id}-{slug}`
- Builds prompt from board item + triage results + all comments
- Invokes Claude Code via subprocess: `claude --print -p <prompt>` (or `claude-code-sdk`)
- 5-minute timeout, one agent at a time
- After completion: captures stdout, parses git diff, creates commit, optionally creates PR via `gh pr create`
- Posts results back to Slack thread + creates a `BoardActivity` comment on the board item

### Slack Message Format
```
:bug: New Bug: "Login page 500 error after deploy"
Priority: urgent | Category: Job Log | By: Danny

AI Triage (confidence: high)
> The 500 is likely from the auth middleware not handling expired
> sessions. Error in app/auth/utils.py get_current_user().

Proposed Fix:
> Add try/except around session lookup, return 401 redirect
> instead of letting exception propagate as 500.

Files: app/auth/utils.py, app/auth/routes.py

[View on Board]  [Fix It]  [Dismiss]
```

---

## New Routes — `app/brain/danny_os/routes.py`

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/brain/danny-os/slack/interactions` | Slack interaction webhook (button clicks). Returns 200 immediately, enqueues work. |
| GET | `/brain/danny-os/runs` | List agent runs (admin UI, future) |
| GET | `/brain/danny-os/runs/<id>` | Agent run detail |
| GET | `/brain/danny-os/status` | Pipeline health (pending counts, worker status) |

---

## Background Workers (in `app/__init__.py`)

Following the existing `outbox_retry_worker` daemon thread pattern (line ~187):

**danny_os_worker** — triage + Slack pipeline:
- Polls `DannyOSOutbox` for `stage='pending'` items
- 2s sleep when idle, 0.5s when processing

**agent_worker** — Claude Code agent execution:
- Polls `AgentRun` for `status='queued'`
- 10s sleep when idle (agent runs are infrequent/expensive)
- `limit=1` ensures serial execution

---

## Integration Points

### Files to modify:
- **`app/brain/board/routes.py`** — Add `DannyOSService.enqueue()` calls after `db.session.commit()` in `create_board_item()`, `add_board_activity()`, and `update_board_item()` (for status/priority changes)
- **`app/models.py`** — Add `DannyOSOutbox` and `AgentRun` models
- **`app/__init__.py`** — Start two new daemon threads, register danny_os blueprint
- **`app/brain/__init__.py`** — Import danny_os routes
- **`app/config.py`** — Add env var reads for Anthropic, Slack, Danny OS config
- **`requirements.txt`** — Add `anthropic`, `slack-sdk`

### New files:
- `app/services/danny_os_service.py`
- `app/services/ai_triage_service.py`
- `app/services/slack_service.py`
- `app/services/agent_execution_service.py`
- `app/brain/danny_os/__init__.py`
- `app/brain/danny_os/routes.py`
- `migrations/m_danny_os.py`

### Environment variables:
```
ANTHROPIC_API_KEY=sk-ant-...
DANNY_OS_ENABLED=true
DANNY_OS_AI_MODEL=claude-sonnet-4-20250514
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
DANNY_OS_SLACK_CHANNEL=danny-os-alerts
DANNY_OS_AGENT_ENABLED=true
DANNY_OS_AGENT_TIMEOUT=300
```

---

## Feedback Loop

When an agent run completes:
1. **BoardActivity comment** added to the board item (system comment with branch, files changed, PR link)
2. **Board item status** optionally moved to `in_progress`
3. **Slack thread reply** on the original triage message with results
4. **On failure** — error posted to Slack thread + board comment; developer can retry or fix manually

---

## Safety

- Agent runs always happen on a **separate branch**, never main
- Agent runs are **human-gated** — requires Slack button click
- **5-minute timeout** on agent subprocess
- **Serial execution** — only one agent at a time
- Outbox pattern ensures **no lost events** — failures retry with backoff
- Slack interaction webhook **responds immediately** (< 3s), work happens async

---

## Verification

1. Create a test board item with category "bug" and priority "urgent"
2. Confirm `DannyOSOutbox` record created with `stage='pending'`
3. Confirm danny_os_worker picks it up, calls Claude Sonnet API, stores triage
4. Confirm Slack message appears in configured channel with triage + buttons
5. Click "Fix It" in Slack, confirm `AgentRun` record created
6. Confirm agent_worker picks it up, creates branch, runs Claude Code, posts results
7. Confirm Slack thread reply + BoardActivity comment on the board item
8. Test retry: kill the worker mid-triage, confirm it retries on next poll
