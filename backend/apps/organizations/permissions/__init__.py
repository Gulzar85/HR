"""Organization permission names. Convention: ``organizations.<action>_<model>``.

Model permissions (view/add/change) are per type, e.g. ``organizations.change_restaurant``.
Cross-type capabilities are declared on Company.Meta and listed here. *Where* they apply is
decided by organization scopes (docs/security/organization-scopes.md).
"""

CHANGE_STATUS = "organizations.change_organization_status"
MOVE = "organizations.move_organization"
VIEW_HISTORY = "organizations.view_organization_history"
VIEW_STRUCTURE = "organizations.view_organization_structure"
