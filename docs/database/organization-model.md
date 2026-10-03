# Organization data model

```
organizations_company            (id uuid PK, code UNIQUE, name, status, effective_from/to, legal …)
organizations_division           (… company_id FK PROTECT, structure_type)
organizations_corporatelocation  (… division_id FK PROTECT, city_code)
organizations_department         (… location_id FK PROTECT, short_code)
organizations_region             (… division_id FK PROTECT)
organizations_area               (… region_id FK PROTECT)
organizations_restaurant         (… area_id FK PROTECT, city_code, lat/long, opening/closing dates)
organizations_organizationrelationship (child_type, child_id, parent_type, parent_id, effective_from, effective_to, reason, created_by)
organizations_organizationhistory      (entity_type, entity_id, entity_code, event, effective_date, before, after, reason, actor, ip)
```

## Constraints (migration `organizations/0001_initial`)
* Every unit: `code` unique (global), `CHECK effective_to IS NULL OR effective_to >= effective_from`, `CHECK status IN (...)` per type.
* Division: unique `(company, code)`, unique `(company, lower(name))`, valid `structure_type`.
* CorporateLocation: unique `(division, lower(name))`.
* Department: unique `(location, short_code)` and `(location, lower(name))`.
* Region: unique `(division, lower(name))`. Area: unique `(region, lower(name))`.
* Restaurant: `closing_date >= opening_date`, latitude within ±90, longitude within ±180, index on `city_code`.
* Relationship: dates check, partial unique `(child_type, child_id) WHERE effective_to IS NULL` (one current parent), indexes on child and parent.
* History: index `(entity_type, entity_id, -timestamp)`.

Some rules depend on other rows (division structure type, parent status, same company), so the service layer enforces them. Data-quality checks detect violations caused by data loaded around the services.

## Historical queries
"Which region did restaurant X belong to on 2025-06-30?" means walking `organizationrelationship` upward with `effective_from <= d < coalesce(effective_to, ∞)` (`selectors.ancestor_of_type_on`). The current FKs answer "now" in one join.

## Future references (Phase 3+)
Assignments will reference a unit through typed FKs (for example `restaurant`, `department`) plus their own effective dates. Do not add region, area or restaurant fields to Employee.
