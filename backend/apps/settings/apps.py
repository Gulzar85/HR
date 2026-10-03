from django.apps import AppConfig


class SettingsConfig(AppConfig):
    name = "apps.settings"
    label = "ems_settings"
    verbose_name = "System Settings"
    default_auto_field = "django.db.models.BigAutoField"
