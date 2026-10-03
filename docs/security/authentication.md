# Authentication

## Login identifier policy
* **Email** is the only login identifier: unique, stored lower-case, matched case-insensitively.
* `username` is retained (Django compatibility, service accounts), unique, generated from the email if omitted; it cannot be used to sign in.
* Employee code will belong to the Employee domain and is never a login identifier.

## Web flow
`/accounts/login/` → `LoginForm` (email + password) → Django `authenticate()` → `IdentityBackend` → session cookie.
* Only `ACTIVE` accounts authenticate; every failure shows one generic message (no account/status disclosure).
* **Lockout**: `EMS_MAX_FAILED_LOGINS` (default 5) consecutive failures on an active account → status `locked` for `EMS_LOCKOUT_MINUTES` (default 15); expiry unlocks automatically; admins can unlock earlier. Success resets the counter. (Trade-off: an attacker can lock a known email for 15 minutes; mitigated by short, automatic lock and audit trail.)
* Remember-me: unchecked → browser-session cookie; checked → `EMS_REMEMBER_ME_SECONDS` (7 days). Idle timeout 8 h sliding (`SESSION_COOKIE_AGE`, `SESSION_SAVE_EVERY_REQUEST`).
* Logout is POST-only (CSRF protected).
* Password change (`/accounts/password/change/`) requires the current password, runs the validators (min 10 chars, common/numeric/similarity), ends all *other* sessions and API refresh tokens.
* Password reset (`/accounts/password/reset/`): identical response for known/unknown emails; link valid 1 h, single-use (Django token generator bound to the password hash and `last_login`); inactive/pending accounts get no self-service reset; completing a reset ends all sessions and activates a `pending` invitation.
* Passwords are hashed by Django (PBKDF2 by default). Nothing in this codebase hashes, stores or logs a plaintext password, reset token or session key.

## Account lifecycle
```
pending --activate--> active --suspend--> suspended --activate--> active
active --lock(system)--> locked --unlock--> active
pending|active|suspended|locked --deactivate--> inactive --activate--> active
```
Only `UserService` changes status. Each transition is validated, atomic, audited (`AccountEvent` + `AuditLog` + `LoginEvent` for lock/unlock/activate/deactivate), emits an outbox event (`accounts.user_activated`, `accounts.user_deactivated`, `accounts.user_created`, `accounts.password_changed`) and ends sessions/API tokens when the account can no longer sign in.

## Events
`LoginEvent` types: login_success, login_failed, logout, password_changed, password_reset_requested/completed, account_locked/unlocked/activated/deactivated. Fields: user, attempted email, success, failure reason, channel (web/api/admin), IP, user agent, truncated session-key hash. No credentials or tokens.

## E-mail
Templates: `templates/emails/{password_reset,account_activation,account_deactivation}.{txt,html}`. Delivery uses `MAILERS` built from `EMAIL_URL` (Django 6.1) after the transaction commits; failures are logged, never raised. Set `EMS_SITE_URL` for links created outside a request.

## Hardening checklist
CSRF on all POSTs · HttpOnly/SameSite cookies, `Secure` + HSTS in production · CSP with nonces (inline style *attributes* and handlers are forbidden; a test enforces it) · `X-Frame-Options: DENY` · throttled token endpoints (`10/min`) · request IP only trusts `X-Forwarded-For` when `EMS_TRUSTED_PROXY_COUNT > 0`.

## Not implemented (deferred)
Multi-factor authentication, per-IP login throttling on the web form, breached-password checks, reset-request throttling, profile images.
