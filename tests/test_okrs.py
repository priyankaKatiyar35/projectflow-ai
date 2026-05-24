"""
tests/test_okrs.py
OKR (Objectives & Key Results) tests.
"""
import pytest


@pytest.fixture
def sample_objective(admin_client, admin_user):
    r = admin_client.post("/api/objectives", json={
        "title": "Become #1 PM tool",
        "category": "Product",
        "period_label": "2026-Q2",
        "owner_id": admin_user.id,
        "visibility": "company",
    })
    assert r.status_code == 200
    return r.json()


class TestObjectiveCRUD:
    def test_admin_can_create_objective(self, admin_client, admin_user):
        r = admin_client.post("/api/objectives", json={
            "title": "Test Objective",
            "category": "Product",
            "period_label": "2026-Q3",
            "owner_id": admin_user.id,
            "visibility": "company",
        })
        assert r.status_code == 200
        assert r.json()["title"] == "Test Objective"

    def test_get_single_objective(self, admin_client, sample_objective):
        r = admin_client.get(f"/api/objectives/{sample_objective['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == sample_objective["id"]

    def test_list_objectives(self, admin_client, sample_objective):
        r = admin_client.get("/api/objectives")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_update_objective(self, admin_client, sample_objective):
        r = admin_client.patch(f"/api/objectives/{sample_objective['id']}", json={
            "title": "Updated Title",
        })
        assert r.status_code == 200
        assert r.json()["title"] == "Updated Title"

    def test_delete_objective(self, admin_client, sample_objective):
        r = admin_client.delete(f"/api/objectives/{sample_objective['id']}")
        assert r.status_code == 200


class TestKeyResults:
    def test_add_numeric_kr(self, admin_client, sample_objective):
        r = admin_client.post(f"/api/objectives/{sample_objective['id']}/key-results", json={
            "title": "Acquire 50 customers",
            "kr_type": "numeric",
            "start_value": 0,
            "target_value": 50,
            "current_value": 10,
            "unit": "customers",
        })
        assert r.status_code == 200
        assert r.json()["progress_pct"] == 20.0  # (10/50)*100

    def test_percent_kr_progress(self, admin_client, sample_objective):
        r = admin_client.post(f"/api/objectives/{sample_objective['id']}/key-results", json={
            "title": "95% test coverage",
            "kr_type": "percent",
            "target_value": 95,
            "current_value": 72,
        })
        assert r.json()["progress_pct"] == round(72 / 95 * 100, 1)

    def test_boolean_kr(self, admin_client, sample_objective):
        # Not done
        r = admin_client.post(f"/api/objectives/{sample_objective['id']}/key-results", json={
            "title": "Launch product",
            "kr_type": "boolean",
            "target_value": 1,
            "current_value": 0,
        })
        assert r.json()["progress_pct"] == 0.0

        kr_id = r.json()["id"]
        # Mark done
        r = admin_client.patch(f"/api/key-results/{kr_id}", json={"current_value": 1})
        assert r.json()["progress_pct"] == 100.0


class TestVisibility:
    def test_employee_sees_company_objectives(self, admin_client, employee_client, admin_user):
        # Create a company-visible objective
        admin_client.post("/api/objectives", json={
            "title": "Public Goal",
            "period_label": "2026-Q2",
            "owner_id": admin_user.id,
            "visibility": "company",
        })
        r = employee_client.get("/api/objectives")
        titles = [o["title"] for o in r.json()]
        assert "Public Goal" in titles

    def test_employee_cannot_see_private_objectives(self, admin_client, employee_client, admin_user):
        admin_client.post("/api/objectives", json={
            "title": "Private CEO Goal",
            "period_label": "2026-Q2",
            "owner_id": admin_user.id,
            "visibility": "private",
        })
        r = employee_client.get("/api/objectives")
        titles = [o["title"] for o in r.json()]
        assert "Private CEO Goal" not in titles