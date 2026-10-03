import importlib
import sys

import pytest


@pytest.mark.parametrize("mod", ["config.settings.development", "config.settings.production"])
def test_environment_settings_load(mod, monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "x" * 60)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///x.sqlite3")
    sys.modules.pop(mod, None)
    m = importlib.import_module(mod)
    if mod.endswith("production"):
        assert m.DEBUG is False
        assert m.SESSION_COOKIE_SECURE and m.CSRF_COOKIE_SECURE
        assert m.SECURE_HSTS_SECONDS > 0
        assert m.SECURE_SSL_REDIRECT is True
        assert m.X_FRAME_OPTIONS == "DENY"
    else:
        assert m.DEBUG is True
    sys.modules.pop(mod, None)


def test_no_secret_key_in_source():
    import pathlib

    from django.conf import settings

    text = (pathlib.Path(settings.BASE_DIR) / "config/settings/base.py").read_text()
    assert "django-insecure" not in text


def test_templates_have_no_inline_style_or_handlers():
    """The CSP forbids inline style attributes and event-handler attributes: keep templates clean."""
    import pathlib
    import re

    from django.conf import settings

    pattern = re.compile(r"""<[^<>]*\s(style|on[a-z]+)=["']""")
    offenders = [
        str(p)
        for p in (pathlib.Path(settings.BASE_DIR) / "templates").rglob("*.html")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders
