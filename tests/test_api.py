"""Comprehensive API tests for Little List covering CRUD, auth, and task management."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app


class BaseApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "test.sqlite3"
        self.app = create_app(self.database_path)
        self.client = TestClient(self.app)
        self.client.__enter__()

        # Register and log in a default test user
        reg_resp = self.client.post(
            "/api/auth/register",
            json={"username": "testuser", "password": "password123"},
        )
        self.assertEqual(reg_resp.status_code, 201)
        self.user = reg_resp.json()

        login_resp = self.client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "password123"},
        )
        self.assertEqual(login_resp.status_code, 200)
        self.token = login_resp.json()["access_token"]
        self.auth_headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temporary_directory.cleanup()


class TaskApiTests(BaseApiTestCase):
    def test_create_list_update_and_delete_task(self):
        # Create
        created = self.client.post(
            "/api/tasks",
            json={"text": "  Sample task  ", "priority": "high"},
            headers=self.auth_headers,
        )
        self.assertEqual(created.status_code, 201)
        task = created.json()
        self.assertEqual(task["text"], "Sample task")
        self.assertEqual(task["priority"], "high")
        self.assertFalse(task["completed"])
        self.assertEqual(task["status"], "todo")
        self.assertIn("created_at", task)

        # List
        list_resp = self.client.get("/api/tasks", headers=self.auth_headers)
        self.assertEqual(list_resp.status_code, 200)
        data = list_resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["tasks"], [task])

        # Update completed
        updated = self.client.patch(
            f"/api/tasks/{task['id']}",
            json={"completed": True},
            headers=self.auth_headers,
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["completed"])
        self.assertEqual(updated.json()["status"], "done")

        # Update text & priority
        updated_text = self.client.patch(
            f"/api/tasks/{task['id']}",
            json={"text": "Updated task", "priority": "low"},
            headers=self.auth_headers,
        )
        self.assertEqual(updated_text.status_code, 200)
        self.assertEqual(updated_text.json()["text"], "Updated task")
        self.assertEqual(updated_text.json()["priority"], "low")

        # Delete
        deleted = self.client.delete(
            f"/api/tasks/{task['id']}",
            headers=self.auth_headers,
        )
        self.assertEqual(deleted.status_code, 204)
        list_after_delete = self.client.get("/api/tasks", headers=self.auth_headers).json()
        self.assertEqual(list_after_delete["tasks"], [])
        self.assertEqual(list_after_delete["total"], 0)

    def test_rejects_blank_task_text(self):
        response = self.client.post(
            "/api/tasks",
            json={"text": "   "},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_task_text_exceeding_160_chars(self):
        long_text = "a" * 161
        response = self.client.post(
            "/api/tasks",
            json={"text": long_text},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_empty_or_null_patch_values(self):
        created = self.client.post(
            "/api/tasks",
            json={"text": "Sample task"},
            headers=self.auth_headers,
        )
        task_id = created.json()["id"]

        empty_patch = self.client.patch(
            f"/api/tasks/{task_id}", json={}, headers=self.auth_headers
        )
        null_patch = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"completed": None},
            headers=self.auth_headers,
        )
        null_text_patch = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"text": None},
            headers=self.auth_headers,
        )
        blank_text_patch = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"text": "   "},
            headers=self.auth_headers,
        )

        self.assertEqual(empty_patch.status_code, 422)
        self.assertEqual(null_patch.status_code, 422)
        self.assertEqual(null_text_patch.status_code, 422)
        self.assertEqual(blank_text_patch.status_code, 422)

    def test_unknown_task_returns_not_found(self):
        response = self.client.patch(
            "/api/tasks/not-a-task",
            json={"completed": True},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

        del_response = self.client.delete(
            "/api/tasks/not-a-task",
            headers=self.auth_headers,
        )
        self.assertEqual(del_response.status_code, 404)

    def test_unauthenticated_requests_rejected(self):
        # CRUD operations require auth
        res1 = self.client.get("/api/tasks")
        self.assertEqual(res1.status_code, 401)

        res2 = self.client.post("/api/tasks", json={"text": "No auth"})
        self.assertEqual(res2.status_code, 401)

        res3 = self.client.get("/api/stats")
        self.assertEqual(res3.status_code, 401)

    def test_invalid_token_rejected(self):
        res = self.client.get(
            "/api/tasks",
            headers={"Authorization": "Bearer completely-invalid-token"},
        )
        self.assertEqual(res.status_code, 401)

    def test_health_check(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "healthy"})


if __name__ == "__main__":
    unittest.main()
