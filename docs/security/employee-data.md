# Employee data security

| Class | Fields | Permission |
|---|---|---|
| Basic | code, names, status, primary email and mobile | `view_employee` |
| Sensitive identity | date of birth, gender, nationality, photo | `view_sensitive_identity` |
| Identifiers | CNIC, passport, ... | `view_identifiers` (masked); unmasking also needs `view_sensitive_identity` |
| Sensitive contacts | addresses | `view_sensitive_contacts` |
| Emergency contacts | emergency contacts | `view_emergency_contacts` |

Changing a sensitive field also requires the matching view permission.

## Controls
- **Server-side only (ADR-021).** Templates, HTMX partials, serializers, filters, search and export each check permissions themselves.
- **Scope (ADR-022).** `visible_employees` filters every queryset. Out-of-scope or unknown IDs return 404. Child records are looked up through `employee.<relation>`, so they cannot be reached through another employee's URL (IDOR).
- **Masking (ADR-020).** Identifiers are masked in the UI, API, admin and export. Unmasking is an explicit POST in the web UI or `?reveal=1` in the API. Each reveal is audited and recorded on a sensitive timeline entry.
- **Search.** Users with `view_identifiers` can find employees by exact identifier match only.
- **Audit.** Audit rows record the names of changed fields, never sensitive values. A changed identifier is recorded as `[changed]`.
- **Export.** Requires `export_employee`. Basic fields only, scoped, row-capped, protected against formula injection and audited.
- **Photos.** JPEG, PNG or WebP only. Each file is verified with Pillow and checked against size and pixel limits; SVG, scripts and executables are rejected. Photos are served with `Cache-Control: private` only to users with `view_sensitive_identity`.
- **Admin.** Read-only, with sensitive fields excluded.
