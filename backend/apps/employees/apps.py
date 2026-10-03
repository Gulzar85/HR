from django.apps import AppConfig


class EmployeesConfig(AppConfig):
    name = "apps.employees"
    label = "employees"
    verbose_name = "Employees"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.common.navigation import register_nav_item, register_nav_section

        from . import data_quality  # noqa: F401  (registers checks)

        register_nav_section("people", "People", order=10)
        register_nav_item(
            "people", "Employees", "employees:list",
            icon="contact-round", permission="employees.view_employee", key="employees", order=0,
        )  # fmt: skip
        register_nav_item(
            "people", "New employee", "employees:create",
            icon="user-plus", permission="employees.add_employee", key="employee_create", order=10,
        )  # fmt: skip
