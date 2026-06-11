"""Unit tests for the Delega SDK with mocked HTTP."""

from __future__ import annotations

import json
import os
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from delega import (
    Agent,
    Comment,
    DedupResult,
    Delega,
    DelegaAPIError,
    DelegaAuthError,
    DelegaError,
    DelegaNotFoundError,
    DelegaRateLimitError,
    DelegationChain,
    Project,
    Task,
)
from delega._version import USER_AGENT


def _mock_response(data: Any, status: int = 200) -> MagicMock:
    """Create a mock urllib response."""
    body = json.dumps(data).encode("utf-8") if data is not None else b""
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _mock_http_error(status: int, data: Any = None) -> Exception:
    """Create a mock urllib.error.HTTPError."""
    import urllib.error

    body = json.dumps(data).encode("utf-8") if data else b""
    error = urllib.error.HTTPError(
        url="https://api.delega.dev/v1/test",
        code=status,
        msg="Error",
        hdrs=MagicMock(),  # type: ignore[arg-type]
        fp=MagicMock(),
    )
    error.read = MagicMock(return_value=body)
    return error


class TestClientInit(unittest.TestCase):
    def test_requires_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DELEGA_API_KEY", None)
            with self.assertRaises(DelegaError) as ctx:
                Delega()
            self.assertIn("No API key", str(ctx.exception))

    def test_api_key_from_env(self) -> None:
        with patch.dict(os.environ, {"DELEGA_API_KEY": "dlg_test"}):
            client = Delega()
            self.assertEqual(client._http._api_key, "dlg_test")

    def test_api_key_from_param(self) -> None:
        client = Delega(api_key="dlg_direct")
        self.assertEqual(client._http._api_key, "dlg_direct")

    def test_api_key_falls_back_to_DELEGA_AGENT_KEY(self) -> None:
        """Cross-client consistency with @delega-dev/mcp (which primaries DELEGA_AGENT_KEY)."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ["DELEGA_AGENT_KEY"] = "dlg_from_agent_env"
            client = Delega()
            self.assertEqual(client._http._api_key, "dlg_from_agent_env")

    def test_DELEGA_API_KEY_wins_over_DELEGA_AGENT_KEY(self) -> None:
        """When both env vars are set, DELEGA_API_KEY is the primary."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ["DELEGA_API_KEY"] = "dlg_primary"
            os.environ["DELEGA_AGENT_KEY"] = "dlg_fallback"
            client = Delega()
            self.assertEqual(client._http._api_key, "dlg_primary")

    def test_remote_base_url_defaults_to_v1_namespace(self) -> None:
        client = Delega(api_key="dlg_test", base_url="https://custom.host")
        self.assertEqual(client._http._base_url, "https://custom.host/v1")

    def test_base_url_trailing_slash_stripped(self) -> None:
        client = Delega(api_key="dlg_test", base_url="https://custom.host/")
        self.assertEqual(client._http._base_url, "https://custom.host/v1")

    def test_remote_base_url_with_explicit_path_is_preserved(self) -> None:
        client = Delega(api_key="dlg_test", base_url="https://custom.host/api")
        self.assertEqual(client._http._base_url, "https://custom.host/api")

    def test_localhost_base_url_defaults_to_api_namespace(self) -> None:
        client = Delega(api_key="dlg_test", base_url="http://localhost:18890")
        self.assertEqual(client._http._base_url, "http://localhost:18890/api")

    def test_remote_plain_http_is_rejected(self) -> None:
        with self.assertRaises(DelegaError) as ctx:
            Delega(api_key="dlg_test", base_url="http://custom.host")
        self.assertIn("HTTPS", str(ctx.exception))

    def test_has_namespaces(self) -> None:
        client = Delega(api_key="dlg_test")
        self.assertTrue(hasattr(client, "tasks"))
        self.assertTrue(hasattr(client, "agents"))
        self.assertTrue(hasattr(client, "projects"))
        self.assertTrue(hasattr(client, "webhooks"))


class TestTasksMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Delega(api_key="dlg_test")

    @patch("urllib.request.urlopen")
    def test_list_tasks(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([
            {"id": "t1", "content": "Task 1", "priority": 1},
            {"id": "t2", "content": "Task 2", "priority": 3},
        ])
        tasks = self.client.tasks.list()
        self.assertEqual(len(tasks), 2)
        self.assertIsInstance(tasks[0], Task)
        self.assertEqual(tasks[0].id, "t1")
        self.assertEqual(tasks[0].content, "Task 1")

    @patch("urllib.request.urlopen")
    def test_list_tasks_with_filters(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([])
        self.client.tasks.list(priority=1, completed=True)
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        self.assertIn("priority=1", request.full_url)
        self.assertIn("completed=True", request.full_url)

    @patch("urllib.request.urlopen")
    def test_create_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "t_new", "content": "New task", "priority": 2}
        )
        task = self.client.tasks.create("New task")
        self.assertIsInstance(task, Task)
        self.assertEqual(task.content, "New task")
        request = mock_urlopen.call_args[0][0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["content"], "New task")
        self.assertEqual(body["priority"], 2)

    @patch("urllib.request.urlopen")
    def test_create_task_with_options(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "t_new", "content": "Task", "priority": 1, "labels": ["urgent"]}
        )
        self.client.tasks.create(
            "Task", priority=1, labels=["urgent"], due_date="2026-12-31"
        )
        request = mock_urlopen.call_args[0][0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["priority"], 1)
        self.assertEqual(body["labels"], ["urgent"])
        self.assertEqual(body["due_date"], "2026-12-31")

    @patch("urllib.request.urlopen")
    def test_get_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "t1", "content": "Task 1", "completed": False}
        )
        task = self.client.tasks.get("t1")
        self.assertEqual(task.id, "t1")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1"))

    @patch("urllib.request.urlopen")
    def test_update_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "t1", "content": "Updated", "priority": 1}
        )
        task = self.client.tasks.update("t1", content="Updated", priority=1)
        self.assertEqual(task.content, "Updated")
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.get_method(), "PUT")

    @patch("urllib.request.urlopen")
    def test_delete_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(None)
        result = self.client.tasks.delete("t1")
        self.assertTrue(result)
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.get_method(), "DELETE")

    @patch("urllib.request.urlopen")
    def test_complete_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "t1", "content": "Task 1", "completed": True}
        )
        task = self.client.tasks.complete("t1")
        self.assertTrue(task.completed)
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/complete"))

    @patch("urllib.request.urlopen")
    def test_uncomplete_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "t1", "content": "Task 1", "completed": False}
        )
        task = self.client.tasks.uncomplete("t1")
        self.assertFalse(task.completed)

    @patch("urllib.request.urlopen")
    def test_search_tasks(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([
            {"id": "t1", "content": "Deploy app"}
        ])
        tasks = self.client.tasks.search("deploy")
        self.assertEqual(len(tasks), 1)
        request = mock_urlopen.call_args[0][0]
        self.assertIn("search=deploy", request.full_url)

    @patch("urllib.request.urlopen")
    def test_delegate_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "t_sub", "content": "Sub task", "parent_id": "t1"}
        )
        task = self.client.tasks.delegate("t1", "Sub task")
        self.assertEqual(task.parent_id, "t1")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/delegate"))

    @patch("urllib.request.urlopen")
    def test_add_comment(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "c1", "task_id": "t1", "content": "A comment"}
        )
        comment = self.client.tasks.add_comment("t1", "A comment")
        self.assertIsInstance(comment, Comment)
        self.assertEqual(comment.content, "A comment")

    @patch("urllib.request.urlopen")
    def test_list_comments(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([
            {"id": "c1", "task_id": "t1", "content": "Comment 1"},
            {"id": "c2", "task_id": "t1", "content": "Comment 2"},
        ])
        comments = self.client.tasks.list_comments("t1")
        self.assertEqual(len(comments), 2)
        self.assertIsInstance(comments[0], Comment)

    # ── 1.2.0 coordination methods ──

    @patch("urllib.request.urlopen")
    def test_delegate_task_with_assignee(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "id": "t_child",
            "content": "Child",
            "parent_task_id": "t1",
            "root_task_id": "t1",
            "delegation_depth": 1,
            "status": "open",
            "assigned_to_agent_id": "a2",
        })
        task = self.client.tasks.delegate(
            "t1", "Child", assigned_to_agent_id="a2", priority=2
        )
        self.assertEqual(task.parent_task_id, "t1")
        self.assertEqual(task.delegation_depth, 1)
        self.assertEqual(task.assigned_to_agent_id, "a2")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/delegate"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["assigned_to_agent_id"], "a2")
        self.assertEqual(body["priority"], 2)

    @patch("urllib.request.urlopen")
    def test_assign_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "id": "t1",
            "content": "x",
            "assigned_to_agent_id": "a5",
        })
        task = self.client.tasks.assign("t1", "a5")
        self.assertEqual(task.assigned_to_agent_id, "a5")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1"))
        self.assertEqual(request.get_method(), "PUT")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body, {"assigned_to_agent_id": "a5"})

    @patch("urllib.request.urlopen")
    def test_assign_task_unassign(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"id": "t1", "content": "x"})
        self.client.tasks.assign("t1", None)
        body = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertIsNone(body["assigned_to_agent_id"])

    @patch("urllib.request.urlopen")
    def test_chain_hosted_shape(self, mock_urlopen: MagicMock) -> None:
        # Hosted returns {root_id, chain, ...}.
        mock_urlopen.return_value = _mock_response({
            "root_id": "abc",
            "chain": [{"id": "abc", "content": "root", "delegation_depth": 0}],
            "depth": 0,
            "completed_count": 0,
            "total_count": 1,
        })
        chain = self.client.tasks.chain("abc")
        self.assertIsInstance(chain, DelegationChain)
        self.assertEqual(chain.root_id, "abc")
        self.assertEqual(len(chain.chain), 1)
        self.assertEqual(chain.chain[0].id, "abc")

    @patch("urllib.request.urlopen")
    def test_chain_self_hosted_shape(self, mock_urlopen: MagicMock) -> None:
        # Self-hosted returns {root: Task, chain, ...} with no root_id.
        mock_urlopen.return_value = _mock_response({
            "root": {"id": 42, "content": "root"},
            "chain": [{"id": 42, "content": "root", "delegation_depth": 0}],
            "depth": 0,
            "completed_count": 0,
            "total_count": 1,
        })
        chain = self.client.tasks.chain("42")
        # Client layer normalizes to root_id.
        self.assertEqual(chain.root_id, "42")

    @patch("urllib.request.urlopen")
    def test_update_context_hosted_bare_dict(self, mock_urlopen: MagicMock) -> None:
        # Hosted returns the merged context dict.
        mock_urlopen.return_value = _mock_response({"step": "done", "count": 2})
        merged = self.client.tasks.update_context("t1", {"count": 2})
        self.assertEqual(merged, {"step": "done", "count": 2})
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/context"))
        self.assertEqual(request.get_method(), "PATCH")

    @patch("urllib.request.urlopen")
    def test_update_context_self_hosted_full_task(self, mock_urlopen: MagicMock) -> None:
        # Self-hosted returns the full Task; we extract just the context.
        mock_urlopen.return_value = _mock_response({
            "id": 42,
            "content": "x",
            "completed": False,
            "context": {"step": "done", "count": 2},
        })
        merged = self.client.tasks.update_context("42", {"count": 2})
        self.assertEqual(merged, {"step": "done", "count": 2})

    @patch("urllib.request.urlopen")
    def test_find_duplicates(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "has_duplicates": True,
            "matches": [
                {"task_id": "abc", "content": "research pricing", "score": 0.85},
            ],
        })
        result = self.client.tasks.find_duplicates("Research pricing", threshold=0.7)
        self.assertIsInstance(result, DedupResult)
        self.assertTrue(result.has_duplicates)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].score, 0.85)
        body = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(body, {"content": "Research pricing", "threshold": 0.7})

    @patch("urllib.request.urlopen")
    def test_find_duplicates_no_matches(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"has_duplicates": False, "matches": []})
        result = self.client.tasks.find_duplicates("unique content")
        self.assertFalse(result.has_duplicates)
        self.assertEqual(result.matches, [])

    # ── 0.3.0 claiming methods ──

    @patch("urllib.request.urlopen")
    def test_claim_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "task": {
                "id": "t1",
                "content": "Queued work",
                "status": "claimed",
                "claimed_by_agent_id": "a1",
                "claimed_at": "2026-06-10T00:00:00Z",
                "lease_expires_at": "2026-06-10T00:05:00Z",
            }
        })
        task = self.client.tasks.claim(
            project_id="p1", labels=["worker"], lease_seconds=120
        )
        self.assertIsInstance(task, Task)
        assert task is not None
        self.assertEqual(task.status, "claimed")
        self.assertEqual(task.claimed_by_agent_id, "a1")
        self.assertEqual(task.claimed_at, "2026-06-10T00:00:00Z")
        self.assertEqual(task.lease_expires_at, "2026-06-10T00:05:00Z")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/claim"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            body, {"project_id": "p1", "labels": ["worker"], "lease_seconds": 120}
        )

    @patch("urllib.request.urlopen")
    def test_claim_task_empty_queue_returns_none(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"task": None})
        task = self.client.tasks.claim()
        self.assertIsNone(task)
        request = mock_urlopen.call_args[0][0]
        # No optional filters supplied — body should be empty JSON.
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body, {})

    @patch("urllib.request.urlopen")
    def test_heartbeat_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "id": "t1",
            "content": "Queued work",
            "status": "claimed",
            "claimed_by_agent_id": "a1",
            "lease_expires_at": "2026-06-10T00:10:00Z",
        })
        task = self.client.tasks.heartbeat("t1", lease_seconds=600)
        self.assertEqual(task.lease_expires_at, "2026-06-10T00:10:00Z")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/heartbeat"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body, {"lease_seconds": 600})

    @patch("urllib.request.urlopen")
    def test_release_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "id": "t1",
            "content": "Queued work",
            "status": "open",
            "claimed_by_agent_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
        })
        task = self.client.tasks.release("t1")
        self.assertEqual(task.status, "open")
        self.assertIsNone(task.claimed_by_agent_id)
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/release"))

    @patch("urllib.request.urlopen")
    def test_list_tasks_claimed_filter(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([])
        self.client.tasks.list(claimed=True)
        request = mock_urlopen.call_args[0][0]
        self.assertIn("claimed=true", request.full_url)

        self.client.tasks.list(claimed=False)
        request = mock_urlopen.call_args[0][0]
        self.assertIn("claimed=false", request.full_url)

        self.client.tasks.list()
        request = mock_urlopen.call_args[0][0]
        self.assertNotIn("claimed", request.full_url)


class TestAgentsMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Delega(api_key="dlg_test")

    @patch("urllib.request.urlopen")
    def test_list_agents(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([
            {"id": "a1", "name": "bot-1"},
        ])
        agents = self.client.agents.list()
        self.assertEqual(len(agents), 1)
        self.assertIsInstance(agents[0], Agent)

    @patch("urllib.request.urlopen")
    def test_create_agent(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "a_new", "name": "new-bot", "api_key": "dlg_new_key"}
        )
        agent = self.client.agents.create("new-bot", display_name="New Bot")
        self.assertEqual(agent.api_key, "dlg_new_key")

    @patch("urllib.request.urlopen")
    def test_delete_agent(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(None)
        result = self.client.agents.delete("a1")
        self.assertTrue(result)

    @patch("urllib.request.urlopen")
    def test_rotate_key(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"api_key": "dlg_rotated"})
        result = self.client.agents.rotate_key("a1")
        self.assertEqual(result["api_key"], "dlg_rotated")


class TestProjectsMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Delega(api_key="dlg_test")

    @patch("urllib.request.urlopen")
    def test_list_projects(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([
            {"id": "p1", "name": "Project 1"},
        ])
        projects = self.client.projects.list()
        self.assertEqual(len(projects), 1)
        self.assertIsInstance(projects[0], Project)

    @patch("urllib.request.urlopen")
    def test_create_project(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "p_new", "name": "New Project", "emoji": "🚀", "color": "#ff0000"}
        )
        project = self.client.projects.create("New Project", emoji="🚀", color="#ff0000")
        self.assertEqual(project.emoji, "🚀")


class TestWebhooksMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Delega(api_key="dlg_test")

    @patch("urllib.request.urlopen")
    def test_list_webhooks(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response([{"id": "w1", "url": "https://example.com"}])
        webhooks = self.client.webhooks.list()
        self.assertEqual(len(webhooks), 1)

    @patch("urllib.request.urlopen")
    def test_create_webhook(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"id": "w_new", "url": "https://example.com/hook"}
        )
        webhook = self.client.webhooks.create(
            "https://example.com/hook", events=["task.created"]
        )
        self.assertEqual(webhook["url"], "https://example.com/hook")

    @patch("urllib.request.urlopen")
    def test_delete_webhook(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(None, status=204)
        result = self.client.webhooks.delete("w1")
        self.assertTrue(result)


class TestTopLevelMethods(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Delega(api_key="dlg_test")

    @patch("urllib.request.urlopen")
    def test_me(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"id": "a1", "name": "my-agent"})
        result = self.client.me()
        self.assertEqual(result["name"], "my-agent")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/agent/me"))

    @patch("urllib.request.urlopen")
    def test_usage_hosted(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "plan": "free",
            "task_count_month": 42,
            "task_limit": 1000,
            "rate_limit_rpm": 60,
        })
        result = self.client.usage()
        self.assertEqual(result["plan"], "free")
        request = mock_urlopen.call_args[0][0]
        # Post-0.2.0 bug fix: was hitting /stats, now correctly /usage.
        self.assertTrue(request.full_url.endswith("/v1/usage"))

    @patch("urllib.request.urlopen")
    def test_usage_self_hosted_raises_before_fetch(
        self, mock_urlopen: MagicMock
    ) -> None:
        client = Delega(base_url="http://127.0.0.1:18890", api_key="dlg_test")
        with self.assertRaises(DelegaError) as ctx:
            client.usage()
        self.assertIn("only available on the hosted", str(ctx.exception))
        # Critical: no HTTP call should have been made.
        mock_urlopen.assert_not_called()


class TestErrorHandling(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Delega(api_key="dlg_test")

    @patch("urllib.request.urlopen")
    def test_auth_error_401(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(401, {"error": "Invalid API key"})
        with self.assertRaises(DelegaAuthError) as ctx:
            self.client.me()
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("urllib.request.urlopen")
    def test_auth_error_403(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(403, {"error": "Forbidden"})
        with self.assertRaises(DelegaAuthError) as ctx:
            self.client.me()
        self.assertEqual(ctx.exception.status_code, 403)

    @patch("urllib.request.urlopen")
    def test_not_found_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(404, {"error": "Not found"})
        with self.assertRaises(DelegaNotFoundError):
            self.client.tasks.get("nonexistent")

    @patch("urllib.request.urlopen")
    def test_rate_limit_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(429, {"error": "Rate limited"})
        with self.assertRaises(DelegaRateLimitError):
            self.client.tasks.list()

    @patch("urllib.request.urlopen")
    def test_generic_api_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = _mock_http_error(500, {"error": "Server error"})
        with self.assertRaises(DelegaAPIError) as ctx:
            self.client.tasks.list()
        self.assertEqual(ctx.exception.status_code, 500)

    def test_exception_hierarchy(self) -> None:
        self.assertTrue(issubclass(DelegaAPIError, DelegaError))
        self.assertTrue(issubclass(DelegaAuthError, DelegaAPIError))
        self.assertTrue(issubclass(DelegaNotFoundError, DelegaAPIError))
        self.assertTrue(issubclass(DelegaRateLimitError, DelegaAPIError))


class TestHeaders(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_auth_header(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"id": "a1", "name": "test"})
        client = Delega(api_key="dlg_mykey123")
        client.me()
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.get_header("X-agent-key"), "dlg_mykey123")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(request.get_header("User-agent"), USER_AGENT)

    @patch("delega.async_client._require_httpx")
    def test_async_client_sets_user_agent(self, mock_require_httpx: MagicMock) -> None:
        fake_httpx = MagicMock()
        fake_async_client = MagicMock()
        fake_httpx.AsyncClient = fake_async_client
        mock_require_httpx.return_value = fake_httpx

        from delega.async_client import AsyncDelega

        AsyncDelega(api_key="dlg_async")

        _, kwargs = fake_async_client.call_args
        self.assertEqual(kwargs["headers"]["User-Agent"], USER_AGENT)


class TestModels(unittest.TestCase):
    def test_task_from_dict(self) -> None:
        data = {
            "id": "t1",
            "content": "Test",
            "description": "A test task",
            "priority": 3,
            "labels": ["bug"],
            "completed": True,
        }
        task = Task.from_dict(data)
        self.assertEqual(task.id, "t1")
        self.assertEqual(task.description, "A test task")
        self.assertEqual(task.priority, 3)
        self.assertEqual(task.labels, ["bug"])
        self.assertTrue(task.completed)

    def test_task_from_dict_defaults(self) -> None:
        task = Task.from_dict({"id": "t1", "content": "Minimal"})
        self.assertIsNone(task.description)
        self.assertEqual(task.priority, 2)
        self.assertEqual(task.labels, [])
        self.assertFalse(task.completed)

    def test_comment_from_dict(self) -> None:
        comment = Comment.from_dict({"id": "c1", "task_id": "t1", "content": "Hello"})
        self.assertEqual(comment.id, "c1")
        self.assertEqual(comment.task_id, "t1")

    def test_agent_from_dict(self) -> None:
        agent = Agent.from_dict({"id": "a1", "name": "bot", "api_key": "dlg_key"})
        self.assertEqual(agent.name, "bot")
        self.assertEqual(agent.api_key, "dlg_key")

    def test_agent_repr_redacts_api_key(self) -> None:
        agent = Agent.from_dict({"id": "a1", "name": "bot", "api_key": "dlg_key"})
        self.assertNotIn("dlg_key", repr(agent))

    def test_project_from_dict(self) -> None:
        project = Project.from_dict({"id": "p1", "name": "Proj", "emoji": "🎯"})
        self.assertEqual(project.emoji, "🎯")


class TestAsyncImport(unittest.TestCase):
    def test_lazy_import(self) -> None:
        from delega import AsyncDelega

        self.assertTrue(callable(AsyncDelega))


class TestContextLinksState(unittest.TestCase):
    """Tests for context provenance, task links, and session state (0.4.0)."""

    def setUp(self) -> None:
        self.client = Delega(api_key="dlg_test")

    @patch("urllib.request.urlopen")
    def test_update_context_versioned_wrapper(self, mock_urlopen: MagicMock) -> None:
        """Hosted v1.8+ returns {context, version}; unwrap to the merged dict."""
        mock_urlopen.return_value = _mock_response(
            {"context": {"decision": "ship it", "files": ["a.py"]}, "version": 3}
        )
        merged = self.client.tasks.update_context("t1", {"decision": "ship it"})
        self.assertEqual(merged, {"decision": "ship it", "files": ["a.py"]})

    @patch("urllib.request.urlopen")
    def test_update_context_source_and_expected_version(
        self, mock_urlopen: MagicMock
    ) -> None:
        mock_urlopen.return_value = _mock_response({"context": {"k": 1}, "version": 5})
        self.client.tasks.update_context(
            "t1", {"k": 1}, source="agent_observed", expected_version=4
        )
        request = mock_urlopen.call_args[0][0]
        self.assertIn("/v1/tasks/t1/context?", request.full_url)
        self.assertIn("source=agent_observed", request.full_url)
        self.assertIn("expected_version=4", request.full_url)

    @patch("urllib.request.urlopen")
    def test_get_context(self, mock_urlopen: MagicMock) -> None:
        from delega import ContextSnapshot

        mock_urlopen.return_value = _mock_response(
            {"context": {"notes": "hello"}, "version": 2}
        )
        snap = self.client.tasks.get_context("t1")
        self.assertIsInstance(snap, ContextSnapshot)
        self.assertEqual(snap.context, {"notes": "hello"})
        self.assertEqual(snap.version, 2)
        self.assertIsNone(snap.provenance)
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/context"))

    @patch("urllib.request.urlopen")
    def test_get_context_with_provenance(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "context": {"notes": "hello"},
            "version": 2,
            "provenance": {
                "notes": {"source": "agent_observed", "author_agent_id": "a1"}
            },
        })
        snap = self.client.tasks.get_context("t1", include_provenance=True)
        assert snap.provenance is not None
        self.assertEqual(snap.provenance["notes"]["source"], "agent_observed")
        request = mock_urlopen.call_args[0][0]
        self.assertIn("include=provenance", request.full_url)

    @patch("urllib.request.urlopen")
    def test_context_history(self, mock_urlopen: MagicMock) -> None:
        from delega import ContextEntry, ContextHistory

        mock_urlopen.return_value = _mock_response({
            "entries": [
                {
                    "id": "ce2",
                    "key": "notes",
                    "value": {"step": 2},
                    "version": 2,
                    "source": "agent_inferred",
                    "author_agent_id": "a1",
                    "author_name": "Bot",
                    "created_at": "2026-06-11T00:00:00Z",
                    "superseded_by": None,
                    "superseded_at": None,
                },
            ],
            "next_cursor": "100",
        })
        history = self.client.tasks.context_history("t1", key="notes", limit=1)
        self.assertIsInstance(history, ContextHistory)
        self.assertEqual(len(history.entries), 1)
        self.assertIsInstance(history.entries[0], ContextEntry)
        self.assertEqual(history.entries[0].key, "notes")
        self.assertEqual(history.entries[0].value, {"step": 2})
        self.assertEqual(history.next_cursor, "100")
        request = mock_urlopen.call_args[0][0]
        self.assertIn("/v1/tasks/t1/context/history?", request.full_url)
        self.assertIn("key=notes", request.full_url)
        self.assertIn("limit=1", request.full_url)

    @patch("urllib.request.urlopen")
    def test_supersede_context(self, mock_urlopen: MagicMock) -> None:
        from delega import ContextEntry

        mock_urlopen.return_value = _mock_response({
            "superseded": {
                "id": "ce1",
                "key": "notes",
                "value": "old",
                "version": 1,
                "source": "agent_inferred",
                "superseded_at": "2026-06-11T00:00:00Z",
            }
        })
        entry = self.client.tasks.supersede_context("t1", "notes")
        self.assertIsInstance(entry, ContextEntry)
        self.assertEqual(entry.key, "notes")
        self.assertEqual(entry.superseded_at, "2026-06-11T00:00:00Z")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/context/supersede"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body, {"key": "notes"})

    @patch("urllib.request.urlopen")
    def test_set_state(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "id": "t1",
            "content": "Work",
            "session_state": "waiting_input",
            "session_state_detail": "need API credentials",
        })
        task = self.client.tasks.set_state(
            "t1", "waiting_input", detail="need API credentials"
        )
        self.assertEqual(task.session_state, "waiting_input")
        self.assertEqual(task.session_state_detail, "need API credentials")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/state"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            body, {"state": "waiting_input", "detail": "need API credentials"}
        )

    @patch("urllib.request.urlopen")
    def test_add_link(self, mock_urlopen: MagicMock) -> None:
        from delega import TaskLink

        mock_urlopen.return_value = _mock_response({
            "id": "lnk1",
            "task_id": "t1",
            "kind": "pr",
            "repo": "acme/webapp",
            "ref": "42",
            "url": "https://github.com/acme/webapp/pull/42",
        })
        link = self.client.tasks.add_link(
            "t1", "pr", "42", repo="acme/webapp",
            url="https://github.com/acme/webapp/pull/42",
        )
        self.assertIsInstance(link, TaskLink)
        self.assertEqual(link.kind, "pr")
        self.assertEqual(link.repo, "acme/webapp")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/links"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["kind"], "pr")
        self.assertEqual(body["ref"], "42")

    @patch("urllib.request.urlopen")
    def test_list_links(self, mock_urlopen: MagicMock) -> None:
        from delega import TaskLink

        mock_urlopen.return_value = _mock_response([
            {"id": "lnk1", "task_id": "t1", "kind": "branch", "ref": "main"},
            {"id": "lnk2", "task_id": "t1", "kind": "commit", "ref": "abc123"},
        ])
        links = self.client.tasks.list_links("t1")
        self.assertEqual(len(links), 2)
        self.assertIsInstance(links[0], TaskLink)
        self.assertEqual(links[1].kind, "commit")

    @patch("urllib.request.urlopen")
    def test_delete_link(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True})
        result = self.client.tasks.delete_link("t1", "lnk1")
        self.assertTrue(result)
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t1/links/lnk1"))
        self.assertEqual(request.get_method(), "DELETE")

    @patch("urllib.request.urlopen")
    def test_claim_specific_task(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "task": {"id": "t9", "content": "Targeted", "status": "claimed"}
        })
        task = self.client.tasks.claim(task_id="t9", lease_seconds=60)
        assert task is not None
        self.assertEqual(task.id, "t9")
        request = mock_urlopen.call_args[0][0]
        self.assertTrue(request.full_url.endswith("/v1/tasks/t9/claim"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body, {"lease_seconds": 60})

    @patch("urllib.request.urlopen")
    def test_task_model_parses_state_and_version(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({
            "id": "t1",
            "content": "Work",
            "session_state": "working",
            "accountable_agent_id": "a9",
            "context_version": 7,
        })
        task = self.client.tasks.get("t1")
        self.assertEqual(task.session_state, "working")
        self.assertEqual(task.accountable_agent_id, "a9")
        self.assertEqual(task.context_version, 7)


if __name__ == "__main__":
    unittest.main()
