from django.apps import AppConfig


class DataQualityConfig(AppConfig):
    name = "apps.data_quality"
    label = "data_quality"
    verbose_name = "Data Quality"
    default_auto_field = "django.db.models.BigAutoField"
