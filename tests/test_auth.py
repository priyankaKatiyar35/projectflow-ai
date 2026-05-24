"""
tests/test_auth.py
Authentication tests: login, logout, password verification, session handling.
"""
import pytest


class TestLogin:
    """Login functionality tests."""

    def test_login_with_valid_credentials_succeeds(self, client, admin_user):
        r = client.post("/login", data={
            "email": admin_user.email,
            "password": "adminpass123",
        }, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"

    def test_login_with_wrong_password_fails(self, client, admin_user):
        r = client.post("/login", data={
            "email": admin_user.email,
            "password": "wrongpass",
        }, follow_redirects=False)
        assert r.status_code == 303
        assert "error" in r.headers["location"].lower()

    def test_login_with_nonexistent_email_fails(self, client):
        r = client.post("/login", data={
            "email": "ghost@nowhere.com",
            "password": "anything",
        }, follow_redirects=False)
        assert r.status_code == 303
        assert "error" in r.headers["location"].lower()

    def test_login_page_renders(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert "password" in r.text.lower()


class TestLogout:
    """Logout flow tests."""

    def test_logout_clears_session(self, admin_client):
        # Confirm logged in
        r = admin_client.get("/", follow_redirects=False)
        assert r.status_code == 200

        # Logout
        r = admin_client.get("/logout", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

        # Now should be redirected when accessing protected page
        r = admin_client.get("/", follow_redirects=False)
        assert r.status_code == 303


class TestProtectedRoutes:
    """Routes that require authentication."""

    @pytest.mark.parametrize("path", ["/", "/projects", "/tasks", "/reports", "/okrs"])
    def test_unauthenticated_redirected_to_login(self, client, path):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers["location"]

    def test_admin_can_access_admin_pages(self, admin_client):
        for path in ["/admin/users", "/audit"]:
            r = admin_client.get(path, follow_redirects=False)
            assert r.status_code == 200, f"{path} returned {r.status_code}"


class TestPasswordSecurity:
    """Password hashing and verification."""

    def test_password_is_hashed_in_db(self, admin_user):
        """Stored password_hash must not equal plaintext."""
        assert admin_user.password_hash != "adminpass123"
        assert len(admin_user.password_hash) > 30  # bcrypt hashes are long

    def test_password_uses_bcrypt(self, admin_user):
        """Bcrypt hashes start with $2b$ or $2a$."""
        assert admin_user.password_hash.startswith("$2")