# API Authentication (`/api/v1/`)

**Strategy:** JWT (djangorestframework-simplejwt): short-lived access token (15 min), rotating single-use refresh token (7 days) with a server-side blacklist (revocation). Browser clients may also use the session cookie (CSRF enforced). Independent of web sessions (ADR-011). Algorithm HS256 with `SECRET_KEY`.

## Endpoints
| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/auth/token/` | `{email, password}` → `{data: {access, refresh, token_type, expires_in}}`; throttled `10/min`; lockout & login events apply |
| POST | `/api/v1/auth/token/refresh/` | `{refresh}` → new pair; old refresh blacklisted; denied for non-active users |
| POST | `/api/v1/auth/logout/` | `{refresh}` → blacklists it |
| GET | `/api/v1/auth/me/` | profile + effective permissions + scopes |
| POST | `/api/v1/auth/password/change/` | `{old_password, new_password}`; all refresh tokens revoked |
| GET/POST | `/api/v1/users/` | list (filters `q,status,role,group,is_active,ordering`; paginated) / create |
| GET/PATCH | `/api/v1/users/<uuid>/` | |
| POST | `/api/v1/users/<uuid>/status/` | `{action: activate|deactivate|suspend|unlock, reason}` |
| GET/POST, GET/PATCH | `/api/v1/roles/`, `/api/v1/roles/<uuid>/` | permissions as `app.codename` strings |
| GET | `/api/v1/permissions/` | assignable permissions |
| GET | `/api/v1/sessions/`, DELETE `/<uuid>/` | caller's own web sessions |

Requests: `Authorization: Bearer <access>`. Responses: `{"data": ..., "meta": {}}`; lists use `{count,next,previous,results}`; errors `{"error": {"code","message","details"}}`. Invalid/expired/forged tokens → `401` with `WWW-Authenticate: Bearer`.

## Electron contract
```
Electron → HTTPS → /api/v1/auth/token/ → Identity services → User → roles/permissions/scopes
```
* Store the **refresh** token in the OS keychain (Electron `safeStorage`), the access token in memory; never store the password.
* Refresh before expiry; on `401` try one refresh, then sign the user out. Rotation means a refresh token can be used once; always replace both tokens.
* On logout call `/auth/logout/`.
* Authorization is decided by the server; use `/auth/me/` permissions only to adapt the UI.
* Electron must never reach PostgreSQL, the ORM, Redis or Celery.
