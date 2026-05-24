"""
tests/test_attachments.py
File attachments: upload, download, permissions, security, cascade delete.
"""
import io
import pytest


class TestUpload:
    def test_admin_can_upload(self, admin_client, sample_task):
        r = admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("test.txt", b"Hello world", "text/plain")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["original_name"] == "test.txt"
        assert data["size_bytes"] == 11
        assert "size_human" in data

    def test_assigned_employee_can_upload(self, employee_client, sample_task):
        r = employee_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("emp.txt", b"Employee upload", "text/plain")},
        )
        assert r.status_code == 200

    def test_unassigned_user_blocked(self, client, sample_task, second_employee):
        client.post("/login", data={"email": second_employee.email, "password": "emp2pass123"})
        r = client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("x.txt", b"x", "text/plain")},
        )
        assert r.status_code == 403

    def test_empty_file_rejected(self, admin_client, sample_task):
        r = admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert r.status_code == 400

    def test_dangerous_extension_blocked(self, admin_client, sample_task):
        r = admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("virus.exe", b"MZ", "application/x-msdownload")},
        )
        assert r.status_code == 400

    def test_oversized_file_rejected(self, admin_client, sample_task):
        # 11 MB file (limit is 10 MB)
        big_data = b"X" * (11 * 1024 * 1024)
        r = admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("big.bin", big_data, "application/octet-stream")},
        )
        assert r.status_code == 400


class TestList:
    def test_list_attachments(self, admin_client, sample_task):
        # Upload one
        admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("a.txt", b"first", "text/plain")},
        )
        r = admin_client.get(f"/api/tasks/{sample_task['id']}/attachments")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_unassigned_cannot_list(self, client, sample_task, second_employee):
        client.post("/login", data={"email": second_employee.email, "password": "emp2pass123"})
        r = client.get(f"/api/tasks/{sample_task['id']}/attachments")
        assert r.status_code == 403


class TestDownload:
    def test_download_returns_file(self, admin_client, sample_task):
        upload = admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("file.txt", b"download me", "text/plain")},
        ).json()

        r = admin_client.get(f"/api/attachments/{upload['id']}/download")
        assert r.status_code == 200
        assert r.content == b"download me"


class TestPreview:
    def test_image_preview_inline(self, admin_client, sample_task):
        upload = admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("photo.png", b"fake png data", "image/png")},
        ).json()
        assert upload["is_image"] is True
        assert upload["preview_url"] is not None

        r = admin_client.get(f"/api/attachments/{upload['id']}/preview")
        assert r.status_code == 200
        assert "inline" in r.headers.get("content-disposition", "")


class TestDelete:
    def test_uploader_can_delete_own(self, employee_client, sample_task):
        upload = employee_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("mine.txt", b"mine", "text/plain")},
        ).json()
        r = employee_client.delete(f"/api/attachments/{upload['id']}")
        assert r.status_code == 200

    def test_non_uploader_cannot_delete(self, admin_client, employee_client, sample_task):
        admin_upload = admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("admin.txt", b"admin", "text/plain")},
        ).json()
        r = employee_client.delete(f"/api/attachments/{admin_upload['id']}")
        assert r.status_code == 403

    def test_admin_can_delete_anything(self, admin_client, employee_client, sample_task):
        emp_upload = employee_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("emp.txt", b"emp", "text/plain")},
        ).json()
        r = admin_client.delete(f"/api/attachments/{emp_upload['id']}")
        assert r.status_code == 200


class TestCascadeDelete:
    def test_attachments_removed_when_task_deleted(self, admin_client, sample_task, db):
        from app.models import Attachment

        admin_client.post(
            f"/api/tasks/{sample_task['id']}/attachments",
            files={"file": ("a.txt", b"x", "text/plain")},
        )
        # Verify it exists
        assert db.query(Attachment).filter(Attachment.project_task_id == sample_task["id"]).count() == 1

        # Delete the task
        admin_client.delete(f"/api/projects/tasks/{sample_task['id']}")

        # Attachments should be gone
        db.expire_all()
        assert db.query(Attachment).filter(Attachment.project_task_id == sample_task["id"]).count() == 0