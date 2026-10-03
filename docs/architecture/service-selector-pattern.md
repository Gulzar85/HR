# Service / Selector Pattern

| Component | Does | Must not |
|---|---|---|
| View (CBV) | HTTP, authn/authz, forms, response | contain business rules or queries beyond calling a selector |
| Service | business operations, transactions, workflows, emits events/audit | touch `HttpRequest`; return partially applied state |
| Selector | read queries, optimised querysets, reusable filters | write data |

```
EmployeeListView → EmployeeSelector → QuerySet

TransferEmployeeView → TransferService → validation → transaction.atomic
  → assignment update → lifecycle event → audit → outbox (notification)
```

Conventions (see `apps/common/services/base.py`):
```python
from apps.common.services import transactional, after_commit

@transactional
def transfer_employee(*, actor, employee, to_unit, effective_date): ...
```
* Services take keyword-only args, raise `DomainException` subclasses.
* Events are written with `enqueue_outbox_event` inside the transaction (see `events-outbox.md`).
* Scope filtering uses `apps.common.permissions.apply_scope`, never role checks inside views.
* Web views, API views, Celery tasks and the Electron app (via API) call the same service.
