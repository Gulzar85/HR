from django.apps import AppConfig


class EmployeesConfig(AppConfig):
    name = "apps.employees"
    label = "employees"
    verbose_name = "Employees"
    default_auto_field = "django.db.models.BigAutoField"
