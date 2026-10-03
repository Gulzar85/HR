# Database Migration Policy

* All schema changes go through Django migrations. Never edit production tables by hand.
* Do not delete or squash migrations during active development without a recorded reason (ADR).
* Renames: add new field → data migration → switch code → remove old field in a later release.
* Every PR runs `python manage.py makemigrations --check --dry-run`.
* `AUTH_USER_MODEL` (`accounts.User`) is fixed from the first migration.
* Destructive migrations require a backup (`deployment/backup`) and a rollback note.
