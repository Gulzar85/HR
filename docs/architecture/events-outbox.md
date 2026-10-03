# Domain Events & Outbox

```
transaction.atomic
  └ business change
  └ enqueue_outbox_event(...)   ← same transaction
commit
Celery beat → dispatch_outbox (every 10s) → select_for_update(skip_locked)
  → EventBus.publish(event_type, payload) → handlers (notifications, integrations)
```
* At-least-once delivery → handlers must be idempotent.
* Failures retry with exponential backoff; after 5 attempts status = `failed` for operator review.
* Events are frozen dataclasses subclassing `apps.events.DomainEvent`, owned by the emitting domain app (EmployeeCreated, EmployeeTransferred, ApprovalApproved, …). Payloads carry IDs/codes only.
* Handlers register with `@subscribe("employee.transferred")` in the consuming app's `ready()`.
