from django.urls import include, path

from apps.accounts.api import urls as accounts_api
from apps.organizations.api import urls as org_api

from .views import ApiRootView

app_name = "v1"

urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path("auth/", include(accounts_api.auth_urlpatterns)),
    path("users/", include(accounts_api.user_urlpatterns)),
    path("roles/", include(accounts_api.role_urlpatterns)),
    path("permissions/", include(accounts_api.permission_urlpatterns)),
    path("sessions/", include(accounts_api.session_urlpatterns)),
    path("organizations/", include(org_api.organization_urlpatterns)),
    # aliases (same views, same scope rules) for the Electron examples
    path("regions/", include((org_api.alias_urlpatterns["region"], "regions"))),
    path("areas/", include((org_api.alias_urlpatterns["area"], "areas"))),
    path("restaurants/", include((org_api.alias_urlpatterns["restaurant"], "restaurants"))),
    # Phase N: path("employees/", include("apps.employees.api.urls")), ...
]
