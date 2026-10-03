# Employee data model

All tables use UUID primary keys and `created_*`/`updated_*` audit columns.

- `employees_person`: names; `date_of_birth`, `gender` and `nationality` (sensitive); `profile_photo` (served only through an authorised view).
- `employees_employee`: `person` (unique one-to-one), `code` (unique, immutable), `employee_status`, `user` (unique, nullable, `SET_NULL`), `archived_at`. **No organization, position, manager or salary columns.**
- `employees_employeeidentifier`: type, value, `normalized_value`, issuing country, issue and expiry dates, `verification_status` and `is_primary`. Unique on (type, normalized value); one primary per (employee, type).
- `employees_contact`: type, value, `normalized_value` (indexed for search and duplicate checks), label and `is_primary`. One primary per (employee, type).
- `employees_address`: type, address lines, city, province, postal code, country, `effective_from`/`effective_to` and `is_primary`. Adding a new address closes the previous one.
- `employees_emergencycontact`, `employees_personrelationship`, `employees_employeenote`, `employees_timelineentry` (indexed by employee and `occurred_at`).

Employees are never deleted. Archiving sets the status and `archived_at`; reactivating clears both.

The list was tested with 10,000 employees: search by code and pagination stay within a fixed query budget (`tests/test_quality_performance.py`).
