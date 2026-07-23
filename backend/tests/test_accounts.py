from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


def csrf_headers(client: Client) -> dict[str, str]:
    response = client.get("/api/v1/auth/csrf/")

    assert response.status_code == 200
    return {"X-CSRFToken": client.cookies["csrftoken"].value}


def test_register_creates_email_identity_and_session() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/register/",
        data={"email": "Owner@Example.test", "password": "strong password 123"},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == 201
    assert response.json()["email"] == "owner@example.test"
    user = get_user_model().objects.get(email="owner@example.test")
    assert user.username == "owner@example.test"
    assert client.get("/api/v1/auth/me/").json()["id"] == user.pk


def test_register_and_login_require_csrf_protection() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/register/",
        data={"email": "owner@example.test", "password": "strong password 123"},
        content_type="application/json",
    )

    assert response.status_code == 403


def test_login_logout_and_me_flow() -> None:
    user = get_user_model().objects.create_user(
        username="existing-user", email="existing@example.test", password="strong password 123"
    )
    client = Client(enforce_csrf_checks=True)

    login = client.post(
        "/api/v1/auth/login/",
        data={"identifier": "EXISTING@example.test", "password": "strong password 123"},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert login.status_code == 200
    assert login.json()["id"] == user.pk
    assert client.get("/api/v1/auth/me/").status_code == 200
    logout = client.post("/api/v1/auth/logout/", headers=csrf_headers(client))
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me/").status_code in {401, 403}


def test_login_does_not_disclose_account_existence() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/login/",
        data={"identifier": "missing@example.test", "password": "wrong-password"},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid email or password"


@override_settings(AUTH_REGISTRATION_ENABLED=False)
def test_registration_can_be_disabled() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/register/",
        data={"email": "owner@example.test", "password": "strong password 123"},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == 403


def test_password_reset_sends_generic_response_and_accepts_standard_token() -> None:
    user = get_user_model().objects.create_user(
        username="owner@example.test", email="owner@example.test", password="old password 123"
    )
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/password-reset/",
        data={"email": user.email},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == 204
    assert len(mail.outbox) == 1
    query = parse_qs(urlparse(mail.outbox[0].body.splitlines()[-1]).query)
    reset = client.post(
        "/api/v1/auth/password-reset/confirm/",
        data={
            "uid": query["reset_uid"][0],
            "token": query["reset_token"][0],
            "password": "new password 123",
        },
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert reset.status_code == 204
    user.refresh_from_db()
    assert user.check_password("new password 123")


def test_password_reset_does_not_disclose_unknown_email() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/password-reset/",
        data={"email": "missing@example.test"},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == 204
    assert len(mail.outbox) == 0
