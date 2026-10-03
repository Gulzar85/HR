# Electron EMS (placeholder)

Not built in Phase 0 (planned Phase 24).

```
Electron
   ↓  HTTPS
Django REST API (/api/v1/)
   ↓
Application Services
   ↓
Domain
```

**Architectural rule:** Electron must NEVER access PostgreSQL, the Django ORM, Redis or Celery directly. It talks only to the versioned REST API using token authentication (selected in Phase 1).
