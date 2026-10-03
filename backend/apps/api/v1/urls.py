from django.urls import include, path

from apps.accounts.api import urls as accounts_api

from .views import ApiRootView

app_name = "v1"

urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path("auth/", include(accounts_api.auth_urlpatterns)),
    path("users/", include(accounts_api.user_urlpatterns)),
    path("roles/", include(accounts_api.role_urlpatterns)),
    path("permissions/", include(accounts_api.permission_urlpatterns)),
    path("sessions/", include(accounts_api.session_urlpatterns)),
    # Phase N: path("employees/", include("apps.employees.api.urls")), ...
]
