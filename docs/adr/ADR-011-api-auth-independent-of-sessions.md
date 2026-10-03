# ADR-011: API authentication is independent from Django web sessions

Status: Accepted (Phase 1)

## Decision
The API uses JWT access tokens (15 min) with rotating, blacklistable refresh tokens (simplejwt). Browser session auth remains available for the web UI only.

## Why
Electron/mobile/integrations cannot rely on cookies and CSRF. Short-lived signed tokens plus server-side refresh revocation give stateless verification with real revocation. A hand-rolled token system would be insecure.

## Consequences
New dependency `djangorestframework-simplejwt`; account deactivation, password change and logout blacklist refresh tokens; access tokens are bounded by the 15 minute lifetime and the active-user check on every request.
