# Employee creation

1. **People -> New employee** (requires `add_employee` and full scope).
2. Enter identity details (sensitive fields appear only if the user may set them), primary email and mobile, and optionally an address, an emergency contact and an identifier. An optional section is validated only when any of its fields is filled in.
3. **Duplicate check**: the system looks for a matching identifier, email or phone, or the same name with the same date of birth. If anything matches, the user sees the matching codes and must confirm before the record is created. Records are never merged automatically. The API returns 409.
4. `EmployeeService.create_employee` runs in one transaction: it creates the person, code, employee and child records, the audit rows, a timeline entry and an `EmployeeCreated` outbox event.
5. The user lands on the detail page. Later changes use the inline editors, and each change is audited and added to the timeline.

Leavers are archived, never deleted. Reactivation needs a reason. Linking a login account is a separate, audited step and does not change the account itself.
