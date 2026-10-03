from django.apps import AppConfig


class HealthConfig(AppConfig):
    name = "apps.health"
    label = "health"
    verbose_name = "Health"
    default_auto_field = "django.db.models.BigAutoField"
