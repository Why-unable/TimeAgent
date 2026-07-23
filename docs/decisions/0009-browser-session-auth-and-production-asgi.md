# 0009: Browser Session Authentication and Production ASGI

## Status

Accepted

## Context

Time Agent business APIs are user-scoped, but previously relied on a Django
admin session. That is not an application login experience and cannot support
installed PWA users. The Docker Compose service also used Django's development
server, which is not appropriate for an Internet-facing deployment.

## Decision

- Use the existing Django `User` model and an email-as-username convention for
  newly registered accounts. This avoids a late `AUTH_USER_MODEL` migration
  after business models already reference users.
- Expose same-origin, cookie-based APIs under `/api/v1/auth/`: CSRF bootstrap,
  registration, login, logout, current user, and password reset.
- Protect state-changing anonymous endpoints with Django CSRF protection and
  apply an anonymous authentication throttle. Password-reset requests always
  return the same response to avoid account enumeration.
- Provide a dedicated React `/login` page. All business routes are protected;
  the account settings page exposes the current session and logout action.
- Run the Django ASGI application under Uvicorn in containers. Production
  settings set secure, HTTP-only, same-site session cookies. The production
  Compose overlay binds Nginx to loopback for Cloudflare Tunnel or another
  trusted public TLS proxy.

## Consequences

- Browsers must obtain a CSRF cookie before state-changing authentication
  requests; the frontend does this through the dedicated endpoint.
- Public registration is configurable through `AUTH_REGISTRATION_ENABLED` and
  should be disabled for invitation-only deployments.
- Password reset depends on a functioning email provider and a correct public
  origin/proxy-header configuration.
- An existing administrator can still sign in using the previous username;
  newly created accounts use normalized email addresses as their usernames.
