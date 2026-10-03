import ast
import inspect
import pathlib
from datetime import date

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from apps.common.exceptions import BusinessRuleException, DomainException, NotFoundException
from apps.common.services import generate_code, transactional
from apps.common.utils import date_ranges_overlap, unique_slug

ROOT = pathlib.Path(settings.BASE_DIR)
EXPECTED_APPS = [
    "common",
    "accounts",
    "theme",
    "settings",
    "feature_flags",
    "organizations",
    "employees",
    "employment",
    "positions",
    "assignments",
    "lifecycle",
    "onboarding",
    "offboarding",
    "movements",
    "documents",
    "workflows",
    "approvals",
    "notifications",
    "hr_cases",
    "headcount",
    "recruitment",
    "reports",
    "dashboards",
    "search",
    "imports",
    "data_quality",
    "audit",
    "events",
    "outbox",
    "jobs",
    "api",
    "health",
]


def test_settings_load():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.SECRET_KEY
    assert "guardian.backends.ObjectPermissionBackend" in settings.AUTHENTICATION_BACKENDS


def test_application_registry():
    names = {c.name for c in apps.get_app_configs()}
    for app in EXPECTED_APPS:
        assert f"apps.{app}" in names
    labels = [c.label for c in apps.get_app_configs()]
    assert len(labels) == len(set(labels))


@pytest.mark.django_db
def test_database_works():
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1


@pytest.mark.django_db
def test_custom_user_model():
    User = get_user_model()
    u = User.objects.create_user("alice", "Alice@Example.com", "s3cret-pass-123")
    assert u.pk.version == 4
    assert u.email == "alice@example.com"  # stored lower-case: email is the login identifier
    assert u.check_password("s3cret-pass-123")
    # User owns no employee/person column (Employee.user is an optional link *from* Employee).
    assert not any(f.name in ("employee", "person") for f in User._meta.concrete_fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("alice2", "alice@example.com", "s3cret-pass-123")
    assert User.objects.get_by_email("ALICE@example.com") == u


@pytest.mark.django_db
def test_generate_code_format_and_uniqueness():
    assert generate_code("EMP") == "EMP-000001"
    assert generate_code("EMP") == "EMP-000002"
    assert generate_code("RST", scope="LHR", width=3) == "RST-LHR-001"
    assert generate_code("TRF", year=2026) == "TRF-2026-000001"


@pytest.mark.django_db
def test_transactional_rolls_back():
    from apps.audit.models import AuditLog
    from apps.audit.services import record_audit

    @transactional
    def op():
        record_audit(action="x")
        raise BusinessRuleException("nope")

    with pytest.raises(BusinessRuleException):
        op()
    assert AuditLog.objects.count() == 0


@pytest.mark.django_db
def test_outbox_is_atomic_with_business_change():
    from apps.outbox.models import OutboxEvent
    from apps.outbox.services import enqueue_outbox_event

    with pytest.raises(RuntimeError), transaction.atomic():
        enqueue_outbox_event(event_type="employee.created", payload={"id": "1"})
        raise RuntimeError
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_outbox_dispatch_delivers_and_retries():
    from apps.events import event_bus
    from apps.outbox.models import OutboxEvent
    from apps.outbox.services import dispatch_pending, enqueue_outbox_event

    seen = []
    event_bus.subscribe("t.ok", seen.append)
    enqueue_outbox_event(event_type="t.ok", payload={"a": 1})
    assert dispatch_pending() == {"processed": 1, "failed": 0}
    assert seen == [{"a": 1}]

    def boom(_):
        raise ValueError("x")

    event_bus.subscribe("t.bad", boom)
    enqueue_outbox_event(event_type="t.bad")
    assert dispatch_pending()["failed"] == 1
    evt = OutboxEvent.objects.get(event_type="t.bad")
    assert evt.status == "pending" and evt.attempts == 1
    event_bus.clear()


def test_exception_hierarchy():
    assert issubclass(NotFoundException, DomainException)
    assert NotFoundException().http_status == 404


def test_date_and_slug_helpers():
    assert date_ranges_overlap(date(2026, 1, 1), None, date(2026, 5, 1), date(2026, 6, 1))
    assert not date_ranges_overlap(date(2026, 1, 1), date(2026, 2, 1), date(2026, 5, 1), None)


@pytest.mark.django_db
def test_unique_slug():
    from django.contrib.auth.models import Group

    Group.objects.create(name="hr-team")
    assert unique_slug(Group.objects.all(), "HR Team", field="name") == "hr-team-2"


def test_upload_validator_rejects_bad_content():
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.common.validators import validate_upload

    validate_upload(SimpleUploadedFile("a.pdf", b"%PDF-1.7 data"))
    with pytest.raises(ValidationError):
        validate_upload(SimpleUploadedFile("a.pdf", b"MZ not a pdf"))
    with pytest.raises(ValidationError):
        validate_upload(SimpleUploadedFile("a.exe", b"MZ"))


@pytest.mark.django_db
def test_celery_configuration_loads():
    from config.celery import app

    assert app.conf.task_serializer == "json"
    assert "apps.outbox.tasks.dispatch_outbox" in app.conf.beat_schedule["outbox-dispatch"]["task"]
    app.loader.import_default_modules()
    assert "apps.outbox.tasks.dispatch_outbox" in app.tasks


def test_theme_foundation():
    from apps.theme.services import ThemeService, render_css_variables

    css = render_css_variables(ThemeService.resolve())
    for token in ("--color-primary", "--color-surface", "--color-background", "--color-danger"):
        assert token in css


# --- Architecture rules ------------------------------------------------------
def _py_files(*parts):
    return [p for p in (ROOT.joinpath(*parts)).rglob("*.py") if "migrations" not in p.parts]


def test_cbv_only_views():
    offenders = []
    for path in _py_files("apps"):
        if path.parent.name != "views" and path.name != "views.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.name}:{n.name}"
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.args.args and n.args.args[0].arg == "request"
        ]
    assert not offenders, f"function-based views are forbidden: {offenders}"


def test_common_does_not_import_other_apps():
    for path in _py_files("apps", "common"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            mod = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
            elif isinstance(node, ast.Import):
                mod = node.names[0].name
            if mod.startswith("apps.") and not mod.startswith("apps.common"):
                pytest.fail(f"{path} imports {mod}")


def test_no_print_in_apps():
    for path in _py_files("apps"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
                pytest.fail(f"print() in {path}")


def test_error_handlers_are_callable_views():
    from apps.common.views import errors

    assert inspect.isfunction(errors.not_found)
