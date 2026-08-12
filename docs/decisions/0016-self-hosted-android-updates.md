# 0016: Self-hosted Android updates

## Status

Accepted

## Context

Time Agent is currently distributed as a side-loaded Capacitor APK rather than through Google Play. Google Play's in-app update API therefore cannot manage these installations. Android also does not permit an ordinary application to silently replace itself.

## Decision

- The authenticated backend exposes a release manifest at `/api/v1/app-updates/android/latest/`.
- The Android client downloads only an absolute HTTPS URL and enforces a 250 MiB upper bound.
- Before opening the system installer, native code verifies the configured byte size, SHA-256 digest, application ID, monotonically increasing `versionCode`, and the installed app's signing certificate.
- Android's package installer remains the authority. The user must grant “install unknown apps” permission and explicitly confirm each update.
- All production releases use one protected, backed-up signing key. Losing or rotating that key without Android-supported key rotation makes existing installations impossible to update.
- Release APKs are served by object/static storage or a CDN. Django serves only metadata, not large APK bodies.

## Consequences

The current installed APK must be replaced once with a build containing the updater. Subsequent compatible releases can be installed from inside the app. A store-distributed build should use Play In-App Updates instead of requesting side-load permission.
