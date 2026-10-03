# Session Management

* Django DB sessions (`SESSION_ENGINE = ...sessions.backends.db`, required for listing/revocation).
* On login a `UserSession` row (id, key, IP, user agent, created, revoked) is created. UI/API expose only the row **id**, never the key.
* **Self-service**: `/profile/sessions/` lists active sessions (non-expired, non-revoked) and revokes others; `DELETE /api/v1/sessions/<id>/`. Lookups are owner-bound (a user cannot revoke another user's session by guessing an id).
* **Administrators** (`accounts.manage_users`): "Revoke all sessions" on the user page.
* Automatic revocation: deactivate/suspend/lock, password change (other sessions), password reset, password set by admin. API refresh tokens are blacklisted at the same time.
* Even if a session row survives, an account that is not `active` is never authenticated (Django re-loads the user each request).
* Cookies: HttpOnly, SameSite=Lax, Secure in production; key cycled on login and password change (`UserSession` follows the new key).
* Not implemented: concurrent-session limits, geo/device anomaly detection.
