from django.urls import path

from apps.accounts.views import (
    AccountProfileView,
    AuthTokenRevokeView,
    AuthTokenView,
    CsrfTokenView,
    CurrentUserView,
    EmailVerificationConfirmView,
    EmailVerificationRequestView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)

urlpatterns = [
    path("csrf/", CsrfTokenView.as_view(), name="csrf"),
    path("register/", RegisterView.as_view(), name="register"),
    path(
        "email-verification/confirm/",
        EmailVerificationConfirmView.as_view(),
        name="email-verification-confirm",
    ),
    path(
        "email-verification/",
        EmailVerificationRequestView.as_view(),
        name="email-verification-request",
    ),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/", AuthTokenView.as_view(), name="token"),
    path("token/revoke/", AuthTokenRevokeView.as_view(), name="token-revoke"),
    path("me/", CurrentUserView.as_view(), name="me"),
    path("profile/", AccountProfileView.as_view(), name="profile"),
    path("password-reset/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
]
