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
    Delega,
    DelegaAPIError,
    DelegaAuthError,
    DelegaError,
    DelegaNotFoundError,
    DelegaRateLimitError,
    Project,
    Task,
)


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
    def test_usage(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"requests": 42})
        result = self.client.usage()
        self.assertEqual(result["requests"], 42)


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


if __name__ == "__main__":
    unittest.main()
