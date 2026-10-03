# Organizations API (`/api/v1/organizations/`)

Authentication: `Authorization: Bearer <access token>` (see `authentication.md`). Responses use the standard envelopes. Every list and lookup is scope-filtered, and out-of-scope ids return `404`.

| Slug | Type | Parent (`parent_id` on create) |
|---|---|---|
| `companies` | company | none |
| `divisions` | division | company |
| `corporate-locations` | corporate_location | division (CORPORATE) |
| `departments` | department | corporate_location |
| `regions` | region | division (OPERATIONS) |
| `areas` | area | region |
| `restaurants` | restaurant | area |

Endpoints per slug:

| Method | Path | Permission |
|---|---|---|
| GET | `/{slug}/` (filters: `q`, `status`, `ordering`, parent filters such as `region`, `area`, `corporate_location`, `division`, `company`; `page`, `page_size`) | `organizations.view_<model>` |
| POST | `/{slug}/` with `parent_id`, fields, optional `status` (`planned` or `active`) | `organizations.add_<model>` + scope on the parent |
| GET | `/{slug}/{uuid}/` | view |
| PATCH | `/{slug}/{uuid}/` (editable fields only; `code`, `status` and parent are ignored) | `organizations.change_<model>` |
| POST | `/{slug}/{uuid}/status/` `{action, reason, effective_date?}` | `organizations.change_organization_status` |
| POST | `/{slug}/{uuid}/move/` `{parent_id, reason, effective_date?}` | `organizations.move_organization` + scope on both sides |
| GET | `/{slug}/{uuid}/history/` | `organizations.view_organization_history` |
| GET | `/tree/?include_inactive=0` | `organizations.view_organization_structure` |

Aliases for the Electron examples, with the same views and rules: `/api/v1/regions/`, `/api/v1/areas/`, `/api/v1/restaurants/`.

Unit representation:
```json
{"id": "…", "code": "RST-LHR-001", "name": "…", "status": "active", "type": "restaurant",
 "effective_from": "2026-10-03", "effective_to": null,
 "parent": {"type": "area", "id": "…", "code": "AREA-001", "name": "Lahore Central"}, "city_code": "LHR", …}
```
Tree nodes: `{type, type_label, id, code, name, status, context, counts: {area: n, restaurant: n}, children: [...]}`.

Errors:
* `400 validation_error`
* `403 permission_denied` (missing permission)
* `404` (missing or out of scope)
* `409 conflict` (duplicate name, code or short code)
* `422 invalid_hierarchy`, `invalid_status_transition`, `active_children`, `inactive_parent`

There is no DELETE: organization units are deactivated, closed or archived, never removed.
