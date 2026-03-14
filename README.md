# Delega Python SDK

Official Python SDK for the [Delega](https://delega.dev) API.

## Installation

```bash
pip install delega
```

For async support:

```bash
pip install 'delega[async]'
```

## Quick Start

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

Pass your API key directly or set the `DELEGA_API_KEY` environment variable:

```python
# Explicit
client = Delega(api_key="dlg_...")

# From environment
# export DELEGA_API_KEY=dlg_...
client = Delega()
```

For self-hosted instances, point `base_url` at the API namespace:

```python
client = Delega(api_key="dlg_...", base_url="http://localhost:18890")
# or: Delega(api_key="dlg_...", base_url="https://delega.yourcompany.com/api")
```

Passing a bare localhost URL defaults to the self-hosted `/api` namespace. For remote self-hosted deployments, include `/api` explicitly.

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

# Delegation
subtask = client.tasks.delegate("parent_task_id", "Research options", priority=2)

# Comments
client.tasks.add_comment("task_id", "Looks good, shipping it")
comments = client.tasks.list_comments("task_id")
```

## Agents

```python
agents = client.agents.list()
agent = client.agents.create("deploy-bot", display_name="Deploy Bot")
print(agent.api_key)  # Only available at creation time

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
```

## Account

```python
me = client.me()       # Get authenticated agent info
usage = client.usage()  # Get API usage stats
```

`me()` and `usage()` are hosted-account endpoints. Self-hosted OSS deployments expose task/agent/project/webhook APIs under `/api`, but may not implement those hosted account endpoints.

## Async Client

```python
from delega import AsyncDelega

async with AsyncDelega(api_key="dlg_...") as client:
    tasks = await client.tasks.list()
    task = await client.tasks.create("Async task")
    await client.tasks.complete(task.id)
```

The async client has the same interface as the sync client, but all methods are coroutines. Requires `httpx` (`pip install 'delega[async]'`).

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

- `Task` - id, content, description, priority, labels, due_date, completed, project_id, parent_id, created_at, updated_at
- `Comment` - id, task_id, content, created_at
- `Agent` - id, name, display_name, description, api_key, created_at, updated_at

The `api_key` field is returned on agent creation and key rotation responses, but it is hidden from the default dataclass `repr()` to reduce accidental secret leakage in logs.
- `Project` - id, name, emoji, color, created_at, updated_at

## License

MIT
