"""
tests/test_projects.py
Project and ProjectTask CRUD with permission tests.
"""
import pytest


class TestProjectCRUD:
    def test_admin_can_create_project(self, admin_client):
        r = admin_client.post("/api/projects", json={
            "name": "New Project",
            "description": "Testing project creation",
        })
        assert r.status_code == 200
        assert r.json()["name"] == "New Project"

    def test_employee_cannot_create_project(self, employee_client):
        r = employee_client.post("/api/projects", json={"name": "Sneaky"})
        assert r.status_code == 403

    def test_admin_can_list_projects(self, admin_client, sample_project):
        r = admin_client.get("/api/projects")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()]
        assert sample_project["name"] in names

    def test_admin_can_get_project_detail(self, admin_client, sample_project):
        r = admin_client.get(f"/api/projects/{sample_project['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == sample_project["id"]

    def test_admin_can_update_project(self, admin_client, sample_project):
        r = admin_client.patch(f"/api/projects/{sample_project['id']}", json={
            "name": "Renamed Project",
        })
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed Project"

    def test_admin_can_delete_project(self, admin_client, sample_project):
        r = admin_client.delete(f"/api/projects/{sample_project['id']}")
        assert r.status_code == 200

    def test_get_nonexistent_project_returns_404(self, admin_client):
        r = admin_client.get("/api/projects/9999")
        assert r.status_code == 404


class TestProjectTaskCreate:
    def test_admin_creates_task_with_all_fields(self, admin_client, sample_project, employee_user):
        r = admin_client.post(f"/api/projects/{sample_project['id']}/tasks", json={
            "task_description": "Build login screen",
            "category": "Frontend",
            "milestone_phase": "Sprint 1",
            "planned_effort": 8.0,
            "status": "not_started",
            "assignee_ids": [employee_user.id],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["task_description"] == "Build login screen"
        assert data["category"] == "Frontend"
        assert data["planned_effort"] == 8.0
        assert len(data["assignees"]) == 1

    def test_employee_cannot_create_task(self, employee_client, sample_project):
        r = employee_client.post(f"/api/projects/{sample_project['id']}/tasks", json={
            "task_description": "Sneaky task",
        })
        assert r.status_code == 403


class TestProjectTaskUpdate:
    def test_admin_can_update_any_field(self, admin_client, sample_task):
        r = admin_client.patch(f"/api/projects/tasks/{sample_task['id']}", json={
            "task_description": "Updated description",
            "category": "Updated category",
            "status": "completed",
            "planned_effort": 99.0,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["task_description"] == "Updated description"
        assert data["status"] == "completed"

    def test_employee_can_update_only_their_actuals(self, employee_client, sample_task):
        """Employee can update status, actual_effort, actual dates, remarks."""
        r = employee_client.patch(f"/api/projects/tasks/{sample_task['id']}", json={
            "status": "completed",
            "actual_effort": 4.5,
            "remarks": "Finished it",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "completed"
        assert data["actual_effort"] == 4.5

    def test_employee_cannot_edit_task_description(self, employee_client, sample_task):
        """Employees cannot change task description (admin-only field)."""
        r = employee_client.patch(f"/api/projects/tasks/{sample_task['id']}", json={
            "task_description": "Sneaky change",
        })
        # Either explicitly 403, or the field is silently ignored
        if r.status_code == 200:
            # Verify the description was NOT changed
            assert r.json()["task_description"] != "Sneaky change"

    def test_non_assigned_employee_cannot_update(self, client, sample_task, second_employee):
        """An employee not on a task cannot update it."""
        # Login as second_employee
        client.post("/login", data={"email": second_employee.email, "password": "emp2pass123"})
        r = client.patch(f"/api/projects/tasks/{sample_task['id']}", json={"status": "completed"})
        assert r.status_code == 403


class TestProjectTaskDelete:
    def test_admin_can_delete_task(self, admin_client, sample_task):
        r = admin_client.delete(f"/api/projects/tasks/{sample_task['id']}")
        assert r.status_code == 200

    def test_employee_cannot_delete_task(self, employee_client, sample_task):
        r = employee_client.delete(f"/api/projects/tasks/{sample_task['id']}")
        assert r.status_code == 403


class TestProjectScopeForEmployees:
    """Employees should only see projects they're assigned to."""

    def test_employee_sees_assigned_project_only(self, admin_client, employee_client, employee_user, admin_user):
        # Create two projects, only assign employee to one
        p1 = admin_client.post("/api/projects", json={"name": "Assigned Project"}).json()
        admin_client.post(f"/api/projects/{p1['id']}/tasks", json={
            "task_description": "Task for employee",
            "assignee_ids": [employee_user.id],
        })

        # Create a second project assigned ONLY to admin
        p2 = admin_client.post("/api/projects", json={"name": "Admin-only Project"}).json()
        admin_client.post(f"/api/projects/{p2['id']}/tasks", json={
            "task_description": "Admin task",
            "assignee_ids": [admin_user.id],
        })

        # Employee should see only their project
        r = employee_client.get("/api/projects")
        names = [p["name"] for p in r.json()]
        assert "Assigned Project" in names
        assert "Admin-only Project" not in names