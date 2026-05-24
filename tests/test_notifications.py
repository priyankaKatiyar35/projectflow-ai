"""
tests/test_notifications.py
Notification system: creation, read state, admin notifications on employee actions.
"""
import pytest


class TestNotificationCreate:
    def test_assignee_gets_notification_on_task_creation(self, admin_client, employee_client, sample_project, employee_user):
        admin_client.post(f"/api/projects/{sample_project['id']}/tasks", json={
            "task_description": "Notify me",
            "assignee_ids": [employee_user.id],
        })

        r = employee_client.get("/api/notifications")
        assert r.status_code == 200
        notifs = r.json()
        assert any("Notify me" in n["title"] or "Notify me" in (n.get("body") or "") for n in notifs)


class TestNotificationRead:
    def test_unread_count_starts_at_zero(self, admin_client):
        r = admin_client.get("/api/notifications/unread_count")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_unread_count_increases_with_new_notification(self, admin_client, employee_client, sample_task):
        # Employee changes status -> admin gets notification
        employee_client.patch(f"/api/projects/tasks/{sample_task['id']}", json={"status": "completed"})

        r = admin_client.get("/api/notifications/unread_count")
        assert r.json()["count"] >= 1

    def test_mark_notification_read(self, admin_client, employee_client, sample_task):
        # Trigger a notification
        employee_client.patch(f"/api/projects/tasks/{sample_task['id']}", json={"status": "completed"})

        notifs = admin_client.get("/api/notifications").json()
        assert len(notifs) >= 1
        nid = notifs[0]["id"]

        # Mark as read
        r = admin_client.post(f"/api/notifications/{nid}/read")
        assert r.status_code == 200

        # Unread count should decrease
        count_after = admin_client.get("/api/notifications/unread_count").json()["count"]
        assert count_after == 0

    def test_mark_all_read(self, admin_client, employee_client, sample_project, employee_user):
        # Create several tasks to trigger several notifs
        for i in range(3):
            admin_client.post(f"/api/projects/{sample_project['id']}/tasks", json={
                "task_description": f"Task {i}",
                "assignee_ids": [employee_user.id],
            })

        # Employee should have unread notifs
        count = employee_client.get("/api/notifications/unread_count").json()["count"]
        assert count >= 3

        # Mark all read
        r = employee_client.post("/api/notifications/read_all")
        assert r.status_code == 200

        count_after = employee_client.get("/api/notifications/unread_count").json()["count"]
        assert count_after == 0


class TestAdminNotificationOnEmployeeAction:
    """Critical: admins must be notified when employees act on tasks."""

    def test_admin_notified_when_employee_changes_status(self, admin_client, employee_client, sample_task):
        before = admin_client.get("/api/notifications").json()
        before_ids = {n["id"] for n in before}

        employee_client.patch(f"/api/projects/tasks/{sample_task['id']}", json={"status": "completed"})

        after = admin_client.get("/api/notifications").json()
        new_notifs = [n for n in after if n["id"] not in before_ids]
        assert len(new_notifs) >= 1, "Admin did not get notification when employee changed status"

        # The notification should mention the employee or the task
        latest = new_notifs[0]
        text = (latest["title"] + " " + (latest.get("body") or "")).lower()
        assert any(kw in text for kw in ["bob", "employee", "test", "completed", "task"])


class TestNotificationClear:
    def test_clear_read_notifications(self, admin_client, employee_client, sample_task):
        # Trigger notification
        employee_client.patch(f"/api/projects/tasks/{sample_task['id']}", json={"status": "completed"})

        # Mark all read
        admin_client.post("/api/notifications/read_all")

        # Clear read
        r = admin_client.delete("/api/notifications")
        assert r.status_code == 200

        remaining = admin_client.get("/api/notifications").json()
        assert all(n["is_read"] is False for n in remaining)