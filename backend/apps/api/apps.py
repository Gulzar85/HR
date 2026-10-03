from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "apps.api"
    label = "ems_api"
    verbose_name = "API"
    default_auto_field = "django.db.models.BigAutoField"
