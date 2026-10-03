from django.apps import AppConfig


class FeatureFlagsConfig(AppConfig):
    name = "apps.feature_flags"
    label = "feature_flags"
    verbose_name = "Feature Flags"
    default_auto_field = "django.db.models.BigAutoField"
