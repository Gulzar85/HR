from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from apps.common.navigation import register_nav_item

        from . import signals  # noqa: F401

        register_nav_item(
            "administration", "Users", "accounts:user_list",
            icon="users", permission="accounts.view_user", key="users", order=10,
        )  # fmt: skip
        register_nav_item(
            "administration", "Roles", "accounts:role_list",
            icon="shield-check", permission="accounts.view_role", key="roles", order=20,
        )  # fmt: skip
        register_nav_item(
            "administration", "Groups", "accounts:group_list",
            icon="users-round", permission="accounts.view_role", key="groups", order=30,
        )  # fmt: skip
