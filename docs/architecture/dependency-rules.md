# Dependency Rules

```
common  ←  platform  ←  domain  ←  application services  ←  web / api
```
* Lower layers never import higher ones. `common` imports no other `apps.*` (tested).
* Domain apps never import another app's **views**. Cross-domain collaboration goes through: services, selectors, domain events, or small interfaces/protocols.
* Avoid cycles such as `employees → recruitment → employees`: recruitment calls `HireService` (employees side exposes the service); employees never import recruitment — it reacts to events.
* Foreign keys across apps use string references (`"organizations.OrgUnit"`) and point from the dependent app to the foundational one.
