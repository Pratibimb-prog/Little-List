"""Tests for priorities, deadlines, search, filters, sorting, stats, and legacy claiming."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.database import connect
from backend.main import create_app
from backend.migrate_legacy import migrate_legacy


class FeaturesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_features.sqlite3"
        self.app = create_app(self.db_path)
        self.client = TestClient(self.app)
        self.client.__enter__()

        # Register and log in test user
        self.client.post(
            "/api/auth/register",
            json={"username": "poweruser", "password": "password123"},
        )
        login = self.client.post(
            "/api/auth/login",
            json={"username": "poweruser", "password": "password123"},
        )
        self.token = login.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_priority_validation(self):
        # Valid priorities
        for p in ["low", "medium", "high"]:
            res = self.client.post(
                "/api/tasks",
                json={"text": f"Task {p}", "priority": p},
                headers=self.headers,
            )
            self.assertEqual(res.status_code, 201)
            self.assertEqual(res.json()["priority"], p)

        # Invalid priority
        bad = self.client.post(
            "/api/tasks",
            json={"text": "Task bad priority", "priority": "urgent"},
            headers=self.headers,
        )
        self.assertEqual(bad.status_code, 422)

    def test_due_date_validation_and_clearing(self):
        # Valid due date
        res = self.client.post(
            "/api/tasks",
            json={"text": "Task with deadline", "due_date": "2026-12-31"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["due_date"], "2026-12-31")
        task_id = res.json()["id"]

        # Clear due date by sending null
        clear_res = self.client.patch(
            f"/api/tasks/{task_id}",
            json={"due_date": None},
            headers=self.headers,
        )
        self.assertEqual(clear_res.status_code, 200)
        self.assertIsNone(clear_res.json()["due_date"])

        # Invalid date format
        bad_date = self.client.post(
            "/api/tasks",
            json={"text": "Task with bad date", "due_date": "31-12-2026"},
            headers=self.headers,
        )
        self.assertEqual(bad_date.status_code, 422)

    def test_filtering_and_search(self):
        self.client.post("/api/tasks", json={"text": "Apples buy", "priority": "low"}, headers=self.headers)
        self.client.post("/api/tasks", json={"text": "Bananas buy", "priority": "high"}, headers=self.headers)
        self.client.post("/api/tasks", json={"text": "Car repair", "priority": "high"}, headers=self.headers)

        # Search by text
        search_res = self.client.get("/api/tasks?search=buy", headers=self.headers).json()
        self.assertEqual(search_res["total"], 2)

        # Filter by priority
        p_res = self.client.get("/api/tasks?priority=high", headers=self.headers).json()
        self.assertEqual(p_res["total"], 2)

        # Combined filter and search
        comb = self.client.get("/api/tasks?priority=high&search=Bananas", headers=self.headers).json()
        self.assertEqual(comb["total"], 1)
        self.assertEqual(comb["tasks"][0]["text"], "Bananas buy")

    def test_sorting(self):
        self.client.post("/api/tasks", json={"text": "Task low", "priority": "low"}, headers=self.headers)
        self.client.post("/api/tasks", json={"text": "Task high", "priority": "high"}, headers=self.headers)
        self.client.post("/api/tasks", json={"text": "Task med", "priority": "medium"}, headers=self.headers)

        # Sort by priority (high -> medium -> low)
        sorted_res = self.client.get("/api/tasks?sort_by=priority", headers=self.headers).json()
        priorities = [t["priority"] for t in sorted_res["tasks"]]
        self.assertEqual(priorities, ["high", "medium", "low"])

    def test_pagination(self):
        for i in range(15):
            self.client.post("/api/tasks", json={"text": f"Item {i:02d}"}, headers=self.headers)

        page1 = self.client.get("/api/tasks?limit=5&offset=0", headers=self.headers).json()
        self.assertEqual(len(page1["tasks"]), 5)
        self.assertEqual(page1["total"], 15)

        page2 = self.client.get("/api/tasks?limit=5&offset=5", headers=self.headers).json()
        self.assertEqual(len(page2["tasks"]), 5)
        self.assertNotEqual(page1["tasks"][0]["id"], page2["tasks"][0]["id"])

    def test_statistics_endpoint(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

        # 1 overdue task
        self.client.post(
            "/api/tasks",
            json={"text": "Overdue task", "due_date": yesterday},
            headers=self.headers,
        )
        # 1 active task due tomorrow
        t2 = self.client.post(
            "/api/tasks",
            json={"text": "Upcoming task", "due_date": tomorrow},
            headers=self.headers,
        ).json()
        # 1 completed task
        t3 = self.client.post(
            "/api/tasks",
            json={"text": "Done task"},
            headers=self.headers,
        ).json()
        self.client.patch(f"/api/tasks/{t3['id']}", json={"completed": True}, headers=self.headers)

        stats = self.client.get("/api/stats", headers=self.headers).json()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["pending"], 2)
        self.assertEqual(stats["overdue"], 1)
        self.assertEqual(stats["completion_percentage"], 33)
        self.assertEqual(stats["completed_today"], 1)

    def test_trends_endpoint(self):
        # Create some tasks with priorities and deadlines
        self.client.post("/api/tasks", json={"text": "Task A", "priority": "high", "due_date": "2026-12-31"}, headers=self.headers)
        t_b = self.client.post("/api/tasks", json={"text": "Task B", "priority": "low"}, headers=self.headers).json()
        self.client.patch(f"/api/tasks/{t_b['id']}", json={"completed": True}, headers=self.headers)

        res = self.client.get("/api/stats/trends?months=6", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("monthly", data)
        self.assertIn("priority_breakdown", data)
        self.assertIn("status_breakdown", data)
        self.assertIn("delivery", data)

        self.assertGreaterEqual(len(data["monthly"]), 1)
        self.assertEqual(data["priority_breakdown"]["high"], 1)
        self.assertEqual(data["priority_breakdown"]["low"], 1)
        self.assertEqual(data["status_breakdown"]["done"], 1)

    def test_legacy_claiming_api_and_cli(self):
        # Insert 2 unowned legacy tasks directly into the database
        conn = connect(self.db_path)
        conn.execute(
            "INSERT INTO tasks (id, text, completed, created_at, user_id) "
            "VALUES ('leg-1', 'Legacy Item 1', 0, '2026-01-01T00:00:00Z', NULL)"
        )
        conn.execute(
            "INSERT INTO tasks (id, text, completed, created_at, user_id) "
            "VALUES ('leg-2', 'Legacy Item 2', 1, '2026-01-01T00:00:00Z', NULL)"
        )
        conn.commit()
        conn.close()

        # Check legacy count endpoint
        count_res = self.client.get("/api/tasks/legacy-count", headers=self.headers).json()
        self.assertEqual(count_res["unclaimed_count"], 2)

        # Claim via API
        claim_res = self.client.post("/api/tasks/claim-legacy", headers=self.headers).json()
        self.assertEqual(claim_res["claimed_count"], 2)

        # Check legacy count is now 0
        count_after = self.client.get("/api/tasks/legacy-count", headers=self.headers).json()
        self.assertEqual(count_after["unclaimed_count"], 0)

        # Verify tasks now appear in user's list
        user_tasks = self.client.get("/api/tasks", headers=self.headers).json()
        ids = [t["id"] for t in user_tasks["tasks"]]
        self.assertIn("leg-1", ids)
        self.assertIn("leg-2", ids)


if __name__ == "__main__":
    unittest.main()
