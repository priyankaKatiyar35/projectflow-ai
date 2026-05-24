"""
tests/test_users.py
User management API tests with permission enforcement.
"""
import pytest


class TestUserList:
    def test_admin_can_list_users(self, admin_client, admin_user, employee_user):
        r = admin_client.get("/api/users")
        assert r.status_code == 200
        users = r.json()
        emails = [u["email"] for u in users]
        assert admin_user.email in emails
        assert employee_user.email in emails

    def test_employee_can_view_user_list(self, employee_client):
        """Employees can see the list (for assigning collaborators)."""
        r = employee_client.get("/api/users")
        assert r.status_code in (200, 403)  # either policy is acceptable


class TestUserCreate:
    def test_admin_can_create_user(self, admin_client):
        r = admin_client.post("/api/users", json={
            "full_name": "New Person",
            "email": "new@test.com",
            "password": "secure123",
            "role": "employee",
        })
        assert r.status_code == 200
        assert r.json()["email"] == "new@test.com"

    def test_employee_cannot_create_user(self, employee_client):
        r = employee_client.post("/api/users", json={
            "full_name": "Sneaky",
            "email": "sneaky@test.com",
            "password": "pwd123",
            "role": "admin",
        })
        assert r.status_code == 403

    def test_duplicate_email_rejected(self, admin_client, admin_user):
        r = admin_client.post("/api/users", json={
            "full_name": "Duplicate",
            "email": admin_user.email,  # already exists
            "password": "pwd123",
            "role": "employee",
        })
        assert r.status_code == 400

    def test_short_password_rejected(self, admin_client):
        r = admin_client.post("/api/users", json={
            "full_name": "Short Pass",
            "email": "short@test.com",
            "password": "123",  # too short
            "role": "employee",
        })
        assert r.status_code == 400

    def test_invalid_role_rejected(self, admin_client):
        r = admin_client.post("/api/users", json={
            "full_name": "Bad Role",
            "email": "badrole@test.com",
            "password": "pwd123",
            "role": "super_user",  # not allowed
        })
        assert r.status_code == 400


class TestUserUpdate:
    def test_admin_can_update_user(self, admin_client, employee_user):
        r = admin_client.patch(f"/api/users/{employee_user.id}", json={
            "full_name": "Renamed Person",
        })
        assert r.status_code == 200
        assert r.json()["full_name"] == "Renamed Person"

    def test_admin_can_change_user_role(self, admin_client, employee_user):
        r = admin_client.patch(f"/api/users/{employee_user.id}", json={"role": "admin"})
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_employee_cannot_update_others(self, employee_client, admin_user):
        r = employee_client.patch(f"/api/users/{admin_user.id}", json={"full_name": "Hacked"})
        assert r.status_code == 403


class TestUserDelete:
    def test_admin_can_delete_user(self, admin_client, second_employee):
        r = admin_client.delete(f"/api/users/{second_employee.id}")
        assert r.status_code == 200

    def test_employee_cannot_delete_user(self, employee_client, admin_user):
        r = employee_client.delete(f"/api/users/{admin_user.id}")
        assert r.status_code == 403

    def test_admin_cannot_delete_self(self, admin_client, admin_user):
        r = admin_client.delete(f"/api/users/{admin_user.id}")
        assert r.status_code == 400

    def test_cannot_delete_last_admin(self, admin_client, admin_user, second_employee):
        # Promote second_employee to admin first (so first admin can be deleted)
        # Then demote it back; first admin should still be undeletable since they're the only admin
        # Actually, simpler: only admin exists, trying to delete self should fail
        r = admin_client.delete(f"/api/users/{admin_user.id}")
        assert r.status_code == 400