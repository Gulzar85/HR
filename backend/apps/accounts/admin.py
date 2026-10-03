"""Django Admin = fallback tooling. Day-to-day administration uses the app UI at /admin/.

Security-relevant records (login/account events, sessions) are strictly read-only here.
"""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from .models import AccountEvent, GroupProfile, LoginEvent, Role, User, UserScope, UserSession


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "email",
        "username",
        "first_name",
        "last_name",
        "status",
        "is_staff",
        "last_login",
    )
    list_filter = ("status", "is_staff", "is_superuser")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = (
        "status",
        "status_changed_at",
        "failed_login_count",
        "locked_until",
        "last_login",
        "date_joined",
    )
    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Account status (change via the app: lifecycle actions are audited)", {
            "fields": ("status", "status_reason", "status_changed_at", "failed_login_count", "locked_until"),
        }),
        ("Access", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )  # fmt: skip
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "username", "password1", "password2")}),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "is_system")
    search_fields = ("name", "code")
    filter_horizontal = ("permissions",)
    readonly_fields = ("code",)


class GroupProfileInline(admin.StackedInline):
    model = GroupProfile
    can_delete = False


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    inlines = [GroupProfileInline]


@admin.register(UserScope)
class UserScopeAdmin(ReadOnlyAdmin):
    list_display = (
        "user",
        "scope_type",
        "scope_ref",
        "include_descendants",
        "granted_by",
        "granted_at",
    )


@admin.register(LoginEvent)
class LoginEventAdmin(ReadOnlyAdmin):
    list_display = (
        "timestamp",
        "event_type",
        "identifier",
        "success",
        "failure_reason",
        "channel",
        "ip_address",
    )
    list_filter = ("event_type", "success", "channel")
    search_fields = ("identifier",)


@admin.register(AccountEvent)
class AccountEventAdmin(ReadOnlyAdmin):
    list_display = ("timestamp", "event_type", "user", "actor")
    list_filter = ("event_type",)


@admin.register(UserSession)
class UserSessionAdmin(ReadOnlyAdmin):
    list_display = ("user", "created_at", "ip_address", "revoked_at")
    exclude = ("session_key",)
