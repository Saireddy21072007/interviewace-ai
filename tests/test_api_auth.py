"""Authentication and access control on the API."""

from __future__ import annotations


def test_register_returns_a_token_and_the_user(client):
    response = client.post("/register", json={
        "email": "newgrad@example.com", "password": "GoodPass123", "full_name": "New Grad"})
    assert response.status_code == 201

    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == "newgrad@example.com"
    assert "password" not in str(body).lower() or "password_hash" not in str(body)


def test_password_hash_never_leaves_the_server(client, auth):
    headers, _ = auth
    body = client.get("/me", headers=headers).json()
    assert "password_hash" not in body


def test_duplicate_email_is_rejected_with_a_useful_message(client):
    payload = {"email": "dupe@example.com", "password": "GoodPass123"}
    assert client.post("/register", json=payload).status_code == 201
    response = client.post("/register", json=payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_weak_passwords_are_rejected(client):
    response = client.post("/register", json={"email": "weak@example.com", "password": "abcdefgh"})
    assert response.status_code == 422
    assert "number" in response.json()["detail"]


def test_login_works_and_is_case_insensitive_on_email(client):
    client.post("/register", json={"email": "case@example.com", "password": "GoodPass123"})
    response = client.post("/login", json={"email": "CASE@example.com", "password": "GoodPass123"})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_wrong_password_gives_the_same_message_as_unknown_email(client):
    client.post("/register", json={"email": "real@example.com", "password": "GoodPass123"})
    wrong_password = client.post("/login", json={"email": "real@example.com", "password": "Nope12345"})
    unknown_email = client.post("/login", json={"email": "ghost@example.com", "password": "Nope12345"})

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


def test_protected_endpoints_reject_anonymous_requests(client):
    for path in ("/me", "/dashboard", "/resumes", "/interviews", "/report", "/roadmap"):
        assert client.get(path).status_code == 401, path


def test_a_tampered_token_is_rejected(client, auth):
    headers, _ = auth
    bad = {"Authorization": headers["Authorization"][:-3] + "xyz"}
    assert client.get("/me", headers=bad).status_code == 401


def test_users_cannot_read_each_other_data(client):
    first = client.post("/register", json={"email": "a1@example.com", "password": "GoodPass123"}).json()
    second = client.post("/register", json={"email": "b1@example.com", "password": "GoodPass123"}).json()

    headers_a = {"Authorization": f"Bearer {first['access_token']}"}
    headers_b = {"Authorization": f"Bearer {second['access_token']}"}

    upload = client.post("/upload-resume", headers=headers_a,
                         files={"file": ("cv.txt", b"SKILLS\nPython\n", "text/plain")})
    resume_id = upload.json()["resume"]["id"]

    assert client.get(f"/resumes/{resume_id}", headers=headers_a).status_code == 200
    assert client.get(f"/resumes/{resume_id}", headers=headers_b).status_code == 404


def test_profile_can_be_updated(client, auth):
    headers, _ = auth
    response = client.patch("/me", headers=headers,
                            json={"target_role": "ml-engineer", "experience_level": "junior"})
    assert response.status_code == 200
    assert response.json()["target_role"] == "ml-engineer"


def test_password_change_requires_the_current_password(client, auth):
    headers, user = auth
    bad = client.post("/me/password", headers=headers,
                      json={"current_password": "WrongPass123", "new_password": "NewPass12345"})
    assert bad.status_code == 403

    good = client.post("/me/password", headers=headers,
                       json={"current_password": "TestPass123", "new_password": "NewPass12345"})
    assert good.status_code == 204
    assert client.post("/login", json={"email": user["email"],
                                       "password": "NewPass12345"}).status_code == 200


def test_admin_endpoints_are_closed_to_normal_users(client, auth):
    headers, _ = auth
    assert client.get("/admin/stats", headers=headers).status_code == 403
    assert client.get("/admin/users", headers=headers).status_code == 403


def test_the_configured_admin_email_gets_admin_rights(client):
    response = client.post("/register", json={
        "email": "admin@interviewace.ai", "password": "AdminPass123"})
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "admin"

    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    stats = client.get("/admin/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["users"] >= 1


def test_deleting_an_account_removes_its_data(client, auth):
    headers, _ = auth
    client.post("/upload-resume", headers=headers,
                files={"file": ("cv.txt", b"SKILLS\nPython\n", "text/plain")})

    assert client.delete("/me", headers=headers).status_code == 204
    assert client.get("/me", headers=headers).status_code == 401
