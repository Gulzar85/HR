# Employees API (`/api/v1/employees/`)

Authentication uses a JWT bearer token. Responses use the standard envelope; lists use standard pagination (`page`, `page_size`). Out-of-scope records return **404**. Unmapped methods are denied.

| Method & path | Permission | Notes |
|---|---|---|
| `GET /` | `view_employee` | Minimal fields. Filters: `q`, `employee_status`, `has_user`, created range, `ordering`. `gender` and `verification_status` need the matching sensitive permission. |
| `POST /` | `add_employee` | Nested `person`, `contacts`, `addresses`, `emergency_contacts`, `identifiers`. Returns **409** `possible_duplicate` unless `confirm_duplicates: true`. |
| `GET /{id}/` | `view_employee` | Sections the caller may not see are omitted. |
| `PATCH /{id}/` | `change_person` | Person fields; sensitive fields need `view_sensitive_identity`. |
| `POST /{id}/status/` | change (archiving needs `archive_employee`) | `{employee_status, reason}` |
| `POST`/`DELETE /{id}/user-link/` | `link_user` | `{email}` |
| `GET`/`POST /{id}/contacts/`, `DELETE .../{item}/` | `view_employee` / `manage_contacts` | |
| `GET`/`POST /{id}/addresses/`, `DELETE .../{item}/` (closes the address) | `view_sensitive_contacts` / `manage_addresses` | |
| `GET`/`POST /{id}/emergency-contacts/`, `DELETE .../{item}/` | `view_emergency_contacts` / `manage_emergency_contacts` | |
| `GET`/`POST /{id}/identifiers/`, `DELETE .../{item}/` | `view_identifiers` / `manage_identifiers` | Values are masked. `?reveal=1` unmasks for users who also hold `view_sensitive_identity`, and the read is audited. |
| `POST /{id}/identifiers/{item}/verification/` | `manage_identifiers` | |
| `GET /{id}/timeline/` | `view_employee_timeline` | |
