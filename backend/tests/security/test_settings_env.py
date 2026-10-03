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
