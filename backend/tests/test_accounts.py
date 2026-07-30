from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_throttle_cache() -> None:
    # AuthenticationThrottle counts per-IP in the cache; LocMemCache is shared
    # across tests, so clear it to isolate each test's rate-limit budget.
    cache.clear()


def csrf_headers(client: Client) -> dict[str, str]:
    response = client.get("/api/v1/auth/csrf/")

    assert response.status_code == 200
    return {"X-CSRFToken": client.cookies["csrftoken"].value}


def test_register_creates_inactive_account_and_sends_verification_email() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/register/",
        data={
            "email": "Owner@Example.test",
            "nickname": "Owner",
            "password": "strong password 123",
        },
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == 202
    user = get_user_model().objects.get(email="owner@example.test")
    assert user.username == "owner@example.test"
    assert user.first_name == "Owner"
    assert not user.is_active
    assert client.get("/api/v1/auth/me/").status_code in {401, 403}
    assert len(mail.outbox) == 1

    query = parse_qs(urlparse(mail.outbox[0].body.splitlines()[-1]).query)
    verified = client.post(
        "/api/v1/auth/email-verification/confirm/",
        data={"uid": query["verify_uid"][0], "token": query["verify_token"][0]},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert verified.status_code == 204
    user.refresh_from_db()
    assert user.is_active

    login = client.post(
        "/api/v1/auth/login/",
        data={"identifier": user.email, "password": "strong password 123"},
        content_type="application/json",
        headers=csrf_headers(client),
    )
    assert login.status_code == 200
    assert login.json()["display_name"] == "Owner"
    assert login.json()["is_email_verified"] is True


def test_register_and_login_require_csrf_protection() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/register/",
        data={
            "email": "owner@example.test",
            "nickname": "Owner",
            "password": "strong password 123",
        },
        content_type="application/json",
    )

    assert response.status_code == 403


@override_settings(CSRF_TRUSTED_ORIGINS=["https://localhost"])
def test_register_accepts_capacitor_https_localhost_origin_with_valid_csrf_token() -> None:
    client = Client(enforce_csrf_checks=True)
    headers = {**csrf_headers(client), "Origin": "https://localhost"}

    response = client.post(
        "/api/v1/auth/register/",
        data={
            "email": "native-owner@example.test",
            "nickname": "Native Owner",
            "password": "strong password 123",
        },
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 202


def test_native_register_does_not_require_a_csrf_cookie() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/native/register/",
        data={
            "email": "native-token-owner@example.test",
            "nickname": "Native Token Owner",
            "password": "strong password 123",
        },
        content_type="application/json",
        headers={"Origin": "https://localhost"},
    )

    assert response.status_code == 202


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


def test_unverified_account_cannot_login_or_receive_native_token() -> None:
    get_user_model().objects.create_user(
        username="pending@example.test",
        email="pending@example.test",
        password="strong password 123",
        is_active=False,
    )
    client = Client(enforce_csrf_checks=True)

    session_login = client.post(
        "/api/v1/auth/login/",
        data={"identifier": "pending@example.test", "password": "strong password 123"},
        content_type="application/json",
        headers=csrf_headers(client),
    )
    token_login = client.post(
        "/api/v1/auth/token/",
        data={"identifier": "pending@example.test", "password": "strong password 123"},
        content_type="application/json",
    )

    assert session_login.status_code == token_login.status_code == 400
    assert session_login.json()["detail"] == "Invalid email or password"


def test_email_verification_resend_is_generic_and_only_sends_for_pending_account() -> None:
    pending = get_user_model().objects.create_user(
        username="pending@example.test",
        email="pending@example.test",
        password="strong password 123",
        is_active=False,
    )
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/email-verification/",
        data={"email": pending.email},
        content_type="application/json",
        headers=csrf_headers(client),
    )
    unknown = client.post(
        "/api/v1/auth/email-verification/",
        data={"email": "missing@example.test"},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == unknown.status_code == 204
    assert len(mail.outbox) == 1


def test_authenticated_user_can_update_nickname() -> None:
    user = get_user_model().objects.create_user(
        username="owner@example.test", email="owner@example.test", password="strong password 123"
    )
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    response = client.patch(
        "/api/v1/auth/profile/",
        data={"nickname": "小林"},
        content_type="application/json",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "小林"
    user.refresh_from_db()
    assert user.first_name == "小林"


@override_settings(AUTH_REGISTRATION_ENABLED=False)
def test_registration_can_be_disabled() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        "/api/v1/auth/register/",
        data={
            "email": "owner@example.test",
            "nickname": "Owner",
            "password": "strong password 123",
        },
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


def test_token_login_needs_no_csrf_and_authenticates_protected_endpoint() -> None:
    user = get_user_model().objects.create_user(
        username="mobile@example.test", email="mobile@example.test", password="strong password 123"
    )
    # enforce_csrf_checks=True proves the native token flow needs no CSRF cookie.
    client = Client(enforce_csrf_checks=True)

    token_response = client.post(
        "/api/v1/auth/token/",
        data={"identifier": "MOBILE@example.test", "password": "strong password 123"},
        content_type="application/json",
    )

    assert token_response.status_code == 200
    body = token_response.json()
    token = body["token"]
    assert token
    assert body["user"]["id"] == user.pk

    # A fresh client with no session cookie, authenticating purely by header.
    bare = Client()
    me = bare.get("/api/v1/auth/me/", headers={"Authorization": f"Token {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == user.pk


def test_token_login_rotates_previous_token() -> None:
    get_user_model().objects.create_user(
        username="mobile@example.test", email="mobile@example.test", password="strong password 123"
    )
    client = Client()
    credentials = {"identifier": "mobile@example.test", "password": "strong password 123"}

    first = client.post("/api/v1/auth/token/", data=credentials, content_type="application/json")
    second = client.post("/api/v1/auth/token/", data=credentials, content_type="application/json")

    assert first.status_code == second.status_code == 200
    assert first.json()["token"] != second.json()["token"]
    old_auth = {"Authorization": f"Token {first.json()['token']}"}
    new_auth = {"Authorization": f"Token {second.json()['token']}"}
    assert client.get("/api/v1/auth/me/", headers=old_auth).status_code in {401, 403}
    assert client.get("/api/v1/auth/me/", headers=new_auth).status_code == 200


def test_token_login_rejects_bad_credentials() -> None:
    get_user_model().objects.create_user(
        username="mobile@example.test", email="mobile@example.test", password="strong password 123"
    )
    client = Client()

    response = client.post(
        "/api/v1/auth/token/",
        data={"identifier": "mobile@example.test", "password": "wrong-password"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid email or password"


def test_token_revoke_invalidates_token() -> None:
    get_user_model().objects.create_user(
        username="mobile@example.test", email="mobile@example.test", password="strong password 123"
    )
    client = Client()
    token = client.post(
        "/api/v1/auth/token/",
        data={"identifier": "mobile@example.test", "password": "strong password 123"},
        content_type="application/json",
    ).json()["token"]
    auth = {"Authorization": f"Token {token}"}

    assert client.get("/api/v1/auth/me/", headers=auth).status_code == 200
    revoke = client.post("/api/v1/auth/token/revoke/", headers=auth)
    assert revoke.status_code == 204
    assert client.get("/api/v1/auth/me/", headers=auth).status_code in {401, 403}
