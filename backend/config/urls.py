from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.common.views.home import HomeView

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("django-admin/", admin.site.urls),  # fallback UI; business admin lives at /admin/
    path("", include("apps.accounts.urls")),
    path("health/", include("apps.health.urls")),
    path("api/", include("apps.api.urls")),
]

handler400 = settings.HANDLER400
handler403 = settings.HANDLER403
handler404 = settings.HANDLER404
handler500 = settings.HANDLER500
