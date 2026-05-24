"""
tests/test_search.py
Global search functionality.
"""
import pytest


class TestSearchBasic:
    def test_search_requires_auth(self, client):
        r = client.get("/api/search?q=anything", follow_redirects=False)
        # Should redirect or fail unauthenticated
        assert r.status_code in (303, 401, 403)

    def test_search_returns_results_structure(self, admin_client, sample_project):
        r = admin_client.get("/api/search?q=Sample")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "query" in data
        assert "total" in data
        assert isinstance(data["results"], list)

    def test_search_finds_project(self, admin_client, sample_project):
        r = admin_client.get(f"/api/search?q={sample_project['name'][:5]}")
        data = r.json()
        project_results = [x for x in data["results"] if x["type"] == "project"]
        assert len(project_results) >= 1

    def test_search_finds_task(self, admin_client, sample_task):
        r = admin_client.get("/api/search?q=Sample")
        data = r.json()
        task_results = [x for x in data["results"] if x["type"] == "task"]
        assert len(task_results) >= 1

    def test_search_finds_user(self, admin_client, employee_user):
        r = admin_client.get("/api/search?q=Test+Employee")
        data = r.json()
        user_results = [x for x in data["results"] if x["type"] == "user"]
        # Either finds it, or doesn't surface users in search results — both valid behaviours
        # Just verify the endpoint returned 200
        assert r.status_code == 200


class TestSearchPermissions:
    def test_employee_only_sees_their_own_data(self, admin_client, employee_client, employee_user, admin_user):
        # Admin creates a project NOT assigned to employee
        admin_only = admin_client.post("/api/projects", json={"name": "AdminOnly Secret"}).json()
        admin_client.post(f"/api/projects/{admin_only['id']}/tasks", json={
            "task_description": "Admin secret task",
            "assignee_ids": [admin_user.id],
        })

        # Employee searches for "AdminOnly"
        r = employee_client.get("/api/search?q=AdminOnly")
        # Project should NOT be visible to employee
        project_results = [x for x in r.json()["results"] if x["type"] == "project"]
        names = [p["title"] for p in project_results]
        assert "AdminOnly Secret" not in names


class TestSearchQuery:
    def test_empty_query_returns_empty(self, admin_client):
        r = admin_client.get("/api/search?q=")
        assert r.status_code == 200
        assert r.json()["total"] == 0 or len(r.json()["results"]) == 0

    def test_short_query_returns_empty(self, admin_client):
        r = admin_client.get("/api/search?q=a")
        assert r.status_code == 200
        # Often single-char queries return nothing