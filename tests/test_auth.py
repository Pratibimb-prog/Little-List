"""Tests for authentication and authorization."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend.auth import create_access_token
from backend.main import create_app


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_auth.sqlite3"
        self.app = create_app(self.db_path)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_successful_registration_and_login(self):
        reg = self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "securepassword123"},
        )
        self.assertEqual(reg.status_code, 201)
        data = reg.json()
        self.assertEqual(data["username"], "alice")
        self.assertIn("id", data)
        self.assertNotIn("password", data)
        self.assertNotIn("password_hash", data)

        login = self.client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "securepassword123"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access_token", login.json())
        self.assertEqual(login.json()["token_type"], "bearer")

    def test_invalid_credentials_rejected(self):
        self.client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "password123"},
        )
        bad_pw = self.client.post(
            "/api/auth/login",
            json={"username": "bob", "password": "wrongpassword"},
        )
        self.assertEqual(bad_pw.status_code, 401)

        bad_user = self.client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "password123"},
        )
        self.assertEqual(bad_user.status_code, 401)

    def test_duplicate_registration_rejected(self):
        r1 = self.client.post(
            "/api/auth/register",
            json={"username": "charlie", "password": "password123"},
        )
        self.assertEqual(r1.status_code, 201)

        r2 = self.client.post(
            "/api/auth/register",
            json={"username": "charlie", "password": "different_pw"},
        )
        self.assertEqual(r2.status_code, 409)

    def test_auth_me_returns_current_user(self):
        reg = self.client.post(
            "/api/auth/register",
            json={"username": "diana", "password": "password123"},
        )
        token = self.client.post(
            "/api/auth/login",
            json={"username": "diana", "password": "password123"},
        ).json()["access_token"]

        me = self.client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "diana")
        self.assertEqual(me.json()["id"], reg.json()["id"])
        self.assertNotIn("password_hash", me.json())

    def test_user_task_isolation(self):
        # User 1
        self.client.post(
            "/api/auth/register",
            json={"username": "user1", "password": "password123"},
        )
        t1 = self.client.post(
            "/api/auth/login",
            json={"username": "user1", "password": "password123"},
        ).json()["access_token"]
        h1 = {"Authorization": f"Bearer {t1}"}

        # User 2
        self.client.post(
            "/api/auth/register",
            json={"username": "user2", "password": "password123"},
        )
        t2 = self.client.post(
            "/api/auth/login",
            json={"username": "user2", "password": "password123"},
        ).json()["access_token"]
        h2 = {"Authorization": f"Bearer {t2}"}

        # User 1 creates task
        created = self.client.post("/api/tasks", json={"text": "User 1 secret"}, headers=h1)
        task_id = created.json()["id"]

        # User 1 sees task
        u1_tasks = self.client.get("/api/tasks", headers=h1).json()
        self.assertEqual(len(u1_tasks["tasks"]), 1)

        # User 2 cannot see User 1's task
        u2_tasks = self.client.get("/api/tasks", headers=h2).json()
        self.assertEqual(len(u2_tasks["tasks"]), 0)

        # User 2 cannot modify User 1's task
        patch_attempt = self.client.patch(
            f"/api/tasks/{task_id}", json={"text": "Hijacked"}, headers=h2
        )
        self.assertEqual(patch_attempt.status_code, 404)

        # User 2 cannot delete User 1's task
        del_attempt = self.client.delete(f"/api/tasks/{task_id}", headers=h2)
        self.assertEqual(del_attempt.status_code, 404)

        # Task is still intact for User 1
        u1_verify = self.client.get("/api/tasks", headers=h1).json()
        self.assertEqual(u1_verify["tasks"][0]["text"], "User 1 secret")

    def test_expired_token_rejected(self):
        self.client.post(
            "/api/auth/register",
            json={"username": "edward", "password": "password123"},
        )
        user_id = self.client.post(
            "/api/auth/login",
            json={"username": "edward", "password": "password123"},
        ).json()["access_token"]

        # Create expired token (-1 minute)
        expired_token = create_access_token(
            "edward-id", expires_delta=timedelta(minutes=-1)
        )
        res = self.client.get(
            "/api/tasks", headers={"Authorization": f"Bearer {expired_token}"}
        )
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
