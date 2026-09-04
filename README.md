# Delega Python SDK

> **Maintenance status:** Delega’s public hosted service retired on July 28, 2026. This SDK remains public as a verifiable engineering artifact and for Ryan McMillan’s existing private deployment. New public accounts and hosted access are not available. See the [case study](https://ryanmcmillan.com/delega).

Python SDK for the Delega API.

## Installation

```bash
pip install delega
```

For async support:

```bash
pip install 'delega[async]'
```

## Existing owner credentials

```python
from delega import Delega

client = Delega(api_key="dlg_...")

# List tasks
tasks = client.tasks.list()

# Create a task
task = client.tasks.create("Deploy to production", priority=1, labels=["ops"])

# Complete a task
client.tasks.complete(task.id)
```

## Authentication

Pass your API key directly or set the `DELEGA_API_KEY` environment variable. `DELEGA_AGENT_KEY` is also accepted as a fallback for shells that are already configured for the Delega MCP; when both are set, `DELEGA_API_KEY` wins.

For a deployment protected by Cloudflare Access, set both `DELEGA_CF_ACCESS_CLIENT_ID` and `DELEGA_CF_ACCESS_CLIENT_SECRET`, or pass `cf_access_client_id=` and `cf_access_client_secret=` to the client constructor. Partial Access configuration is rejected without exposing either value.

```python
# Explicit
client = Delega(api_key="dlg_...")

# From environment
# export DELEGA_API_KEY=dlg_...
# or: export DELEGA_AGENT_KEY=dlg_...
client = Delega()
```

To target a custom endpoint (advanced), point `base_url` at the API namespace:

```python
client = Delega(api_key="dlg_...", base_url="http://localhost:18890")
# or: Delega(api_key="dlg_...", base_url="https://delega.yourcompany.com/api")
```

Passing a bare localhost URL defaults to the `/api` namespace. Passing a bare HTTPS remote URL defaults to `/v1`; include `/api` explicitly for custom endpoints that expose the `/api` namespace. Plain HTTP is rejected unless the host is localhost.

## Tasks

```python
# List with filters
tasks = client.tasks.list(priority=1, completed=False)
tasks = client.tasks.list(labels=["urgent"], due_before="2026-12-31")

# Search
tasks = client.tasks.search("deploy")

# CRUD
task = client.tasks.create("Fix bug", description="Crash on login", priority=1)
task = client.tasks.get("task_id")
task = client.tasks.update("task_id", content="Updated title", priority=3)
client.tasks.delete("task_id")

# Completion
client.tasks.complete("task_id")
client.tasks.uncomplete("task_id")

# Delegation and assignment
subtask = client.tasks.delegate(
    "parent_task_id",
    "Research options",
    priority=2,
    assigned_to_agent_id="agent_id",
)
task = client.tasks.assign("task_id", "agent_id")  # or None to unassign
chain = client.tasks.chain("task_id")

# Duplicate detection
dedup = client.tasks.find_duplicates("Research options", threshold=0.7)

# Comments
client.tasks.add_comment("task_id", "Looks good, shipping it")
comments = client.tasks.list_comments("task_id")
```

### Claiming (work queues)

Worker agents can pull tasks from a shared queue with `claim()`. Claims are atomic (no two workers get the same task) and ordered by priority, then creation time. A claim holds a lease — extend it with `heartbeat()` while you work, release it with `release()` if you can't finish, or `complete()` the task when done:

```python
import time

while True:
    task = client.tasks.claim(labels=["worker"], lease_seconds=300)
    if task is None:
        time.sleep(10)  # queue empty — back off (or break)
        continue

    try:
        # ... do the work, periodically extending the lease:
        client.tasks.heartbeat(task.id, lease_seconds=300)
        # ...
        client.tasks.complete(task.id)
    except Exception:
        client.tasks.release(task.id)  # hand it back to the queue
        raise
```

`claim()` returns `None` when no claimable task is available. Pass `task_id="..."` to claim a specific task instead of pulling the next available task from the queue. `lease_seconds` accepts 30-3600 (default 300); if the lease expires without a heartbeat, the task becomes claimable again. Claiming sets `status` to `"claimed"` but never touches `assigned_to_agent_id`. Filter claimed/unclaimed tasks with `client.tasks.list(claimed=True)` or `claimed=False`.

## Session State

Report what a worker is doing on a task — without touching the claim lease — so orchestrators and dashboards can see `working`, `waiting_input`, or `errored` states:

```python
client.tasks.set_state(task.id, "waiting_input", detail="Need repo credentials")
```

## Task Context & Provenance

Each task carries a persistent context blob shared across sessions and agents. Writes merge (existing keys are preserved) and every write is recorded in an append-only provenance ledger:

```python
# Read the current context and its version
snap = client.tasks.get_context(task.id, include_provenance=True)
print(snap.context, snap.version, snap.provenance)

# Merge keys, attributing the write and guarding against concurrent writers
client.tasks.update_context(
    task.id,
    {"decision": "use Postgres", "files": ["db.py"]},
    source="agent_observed",        # human_stated | agent_inferred | agent_observed | imported
    expected_version=snap.version,  # raises a 409 DelegaAPIError on conflict
)

# Audit who wrote what, when
history = client.tasks.context_history(task.id, key="decision")
for entry in history.entries:
    print(entry.version, entry.author_name, entry.source, entry.value)

# Mark a live entry as stale without changing the value
client.tasks.supersede_context(task.id, "decision")
```

## Task Links

Attach repo activity or URLs to a task (the hosted GitHub integration creates these automatically from `delega:#<task-id>` mentions):

```python
link = client.tasks.add_link(task.id, "pr", "42", repo="acme/webapp")
links = client.tasks.list_links(task.id)
client.tasks.delete_link(task.id, link.id)
```

## Recurrences

Recurring task templates spawn normal task instances on a schedule. Completing a spawned task does not delete the recurrence.

```python
recurrences = client.recurrences.list()
recurrence = client.recurrences.create(
    "Replace furnace filter",
    rule_type="monthly",
    timezone="America/Chicago",
    anchor_day=1,
    labels=["home-family"],
)
client.recurrences.update(recurrence.id, active=False)
client.recurrences.delete(recurrence.id)
```

## Agents

```python
agents = client.agents.list()
agent = client.agents.create("deploy-bot", display_name="Deploy Bot")
print(agent.api_key)  # Only available at creation time

# Role presets (admin key required): worker (own-task scope, default),
# coordinator (sees + can comment on all account tasks), admin
scrum = client.agents.create("scrum-bot", role="coordinator")
agent = client.agents.set_role(agent.id, "coordinator")
print(agent.role)

client.agents.update(agent.id, description="Handles deployments")
result = client.agents.rotate_key(agent.id)
print(result["api_key"])

client.agents.delete(agent.id)
```

## Projects

```python
projects = client.projects.list()
project = client.projects.create("Backend", emoji="⚙️", color="#3498db")
```

## Webhooks

```python
webhooks = client.webhooks.list()
webhook = client.webhooks.create(
    "https://example.com/webhook",
    events=["task.created", "task.completed"],
    secret="whsec_...",
)
client.webhooks.delete(webhook["id"])
```

Verify incoming webhook signatures with the raw payload bytes and the `X-Delega-Signature` / `X-Delega-Timestamp` header values:

```python
from delega import verify_webhook

verify_webhook(payload, signature, timestamp, "whsec_...")
```

## Account

```python
me = client.me()       # Get authenticated agent info
usage = client.usage()  # Get API usage stats
```

`usage()` is only available on the hosted API (`api.delega.dev`) and raises `DelegaError` before making a request when the client is pointed at a custom `/api` namespace. Custom `/api`-namespace endpoints expose task, recurrence, agent, project, and webhook APIs; `me()` depends on whether that endpoint is implemented by the target API.

## Async Client

```python
from delega import AsyncDelega

async with AsyncDelega(api_key="dlg_...") as client:
    tasks = await client.tasks.list()
    task = await client.tasks.create("Async task")
    await client.tasks.complete(task.id)
```

The async client mirrors the sync client for tasks, recurrences, agents, and projects; those methods are coroutines. The async webhooks namespace currently supports `list()` and `create()`, while `webhooks.delete()` is sync-only. Requires `httpx` (`pip install 'delega[async]'`).

## Error Handling

```python
from delega import DelegaError, DelegaAPIError, DelegaAuthError, DelegaNotFoundError, DelegaRateLimitError

try:
    task = client.tasks.get("nonexistent")
except DelegaNotFoundError:
    print("Task not found")
except DelegaAuthError:
    print("Invalid API key")
except DelegaRateLimitError:
    print("Too many requests")
except DelegaAPIError as e:
    print(f"API error {e.status_code}: {e.error_message}")
except DelegaError as e:
    print(f"SDK error: {e}")
```

## Models

All resource methods return typed dataclasses:

- `Task` - id, content, description, priority, labels, due_date, completed, project_id, parent_id, parent_task_id, root_task_id, delegation_depth, status, assigned_to_agent_id, created_by_agent_id, completed_by_agent_id, claimed_by_agent_id, claimed_at, lease_expires_at, session_state, session_state_detail, accountable_agent_id, context, context_version, created_at, updated_at

The claiming fields (`claimed_by_agent_id`, `claimed_at`, `lease_expires_at`) are set while a task is claimed via `tasks.claim()` and are `None` otherwise. A claimed task has `status == "claimed"`.
- `Recurrence` - id, content, description, project_id, priority, labels, assigned_to_agent_id, rule_type, interval, timezone, anchor_day, anchor_month, anchor_weekday, next_due_at, last_spawned_at, active, skip_if_open, created_by_agent_id, created_at, updated_at
- `DelegationChain` - root_id, chain, depth, completed_count, total_count
- `TaskLink` - id, task_id, kind (`branch`/`commit`/`pr`/`url`), repo, ref, url, created_by_agent_id, created_at
- `ContextSnapshot` - context, version, provenance (from `tasks.get_context()`)
- `ContextEntry` / `ContextHistory` - the provenance ledger (from `tasks.context_history()` / `tasks.supersede_context()`)
- `DedupResult` / `DuplicateMatch` - duplicate-detection result and matches from `tasks.find_duplicates()`
- `Comment` - id, task_id, content, created_at
- `Agent` - id, name, display_name, description, role, api_key, created_at, updated_at

The `api_key` field is returned on agent creation and key rotation responses, but it is hidden from the default dataclass `repr()` to reduce accidental secret leakage in logs.
- `Project` - id, name, emoji, color, created_at, updated_at

## Development

The CI workflow installs and tests the package with:

```bash
pip install -e ".[async]"
pip install pytest pytest-asyncio
pytest tests/ -v
```

## License

MIT
