from django.apps import AppConfig


class ThemeConfig(AppConfig):
    name = "apps.theme"
    label = "theme"
    verbose_name = "Theme"
    default_auto_field = "django.db.models.BigAutoField"
