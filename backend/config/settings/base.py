"""Base settings shared by all environments. Secrets come from the environment (.env)."""

from pathlib import Path

import environ
from csp.constants import NONCE, NONE, SELF

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# --- Applications -----------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "django_htmx",
    "crispy_forms",
    "crispy_tailwind",
    "guardian",
    "import_export",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
]

# Dependency direction: common -> platform -> domain -> application -> web/api.
PLATFORM_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.theme",
    "apps.settings",
    "apps.feature_flags",
    "apps.audit",
    "apps.events",
    "apps.outbox",
    "apps.jobs",
]

DOMAIN_APPS = [
    "apps.organizations",
    "apps.employees",
    "apps.employment",
    "apps.positions",
    "apps.assignments",
    "apps.lifecycle",
    "apps.onboarding",
    "apps.offboarding",
    "apps.movements",
    "apps.documents",
    "apps.workflows",
    "apps.approvals",
    "apps.notifications",
    "apps.hr_cases",
    "apps.headcount",
    "apps.recruitment",
    "apps.reports",
    "apps.dashboards",
    "apps.search",
    "apps.imports",
    "apps.data_quality",
]

INTERFACE_APPS = [
    "apps.api",
    "apps.health",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + PLATFORM_APPS + DOMAIN_APPS + INTERFACE_APPS

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.common.middleware.DomainExceptionMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "csp.context_processors.nonce",
                "apps.theme.context_processors.theme",
            ],
        },
    },
]

# --- Database / cache -------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"].endswith("sqlite3") and DATABASES["default"]["NAME"] not in (
    "",
    ":memory:",
):
    DATABASES["default"]["NAME"] = str(BASE_DIR / DATABASES["default"]["NAME"])  # cwd-independent
DATABASES["default"]["ATOMIC_REQUESTS"] = False  # transactions are owned by services
DATABASES["default"]["CONN_MAX_AGE"] = 60
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}
}

# --- Auth -------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.IdentityBackend",  # email login; direct + group + role permissions
    "guardian.backends.ObjectPermissionBackend",  # object-level permissions
]
ANONYMOUS_USER_NAME = None  # guardian: no anonymous DB user
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "accounts:login"
PASSWORD_RESET_TIMEOUT = 60 * 60  # reset/activation links valid for 1 hour

# Identity & security policy (docs/security/authentication.md)
EMS_MAX_FAILED_LOGINS = env.int("EMS_MAX_FAILED_LOGINS", default=5)
EMS_LOCKOUT_MINUTES = env.int("EMS_LOCKOUT_MINUTES", default=15)
EMS_REMEMBER_ME_SECONDS = 60 * 60 * 24 * 7
EMS_ADMIN_PAGE_SIZE = env.int("EMS_ADMIN_PAGE_SIZE", default=25)
EMS_TRUSTED_PROXY_COUNT = env.int("EMS_TRUSTED_PROXY_COUNT", default=0)
EMS_SITE_URL = env("EMS_SITE_URL", default="")  # used in e-mails when no request is available

# --- I18N -------------------------------------------------------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Static / media / storage ----------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(exist_ok=True)  # silences WhiteNoise warning before collectstatic
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / env("MEDIA_ROOT", default="media")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# File upload validation foundation (see apps.common.validators)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
EMS_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
EMS_UPLOAD_ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"]

# --- Email ------------------------------------------------------------------
_email = env.email("EMAIL_URL", default="consolemail://")
_mail_options = {}
if _email.get("EMAIL_HOST"):
    _mail_options = {
        "host": _email["EMAIL_HOST"],
        "port": _email.get("EMAIL_PORT", 25),
        "username": _email.get("EMAIL_HOST_USER", ""),
        "password": _email.get("EMAIL_HOST_PASSWORD", ""),
        "use_tls": _email.get("EMAIL_USE_TLS", False),
    }
MAILERS = {"default": {"BACKEND": _email["EMAIL_BACKEND"], "OPTIONS": _mail_options}}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="ems@example.invalid")

# --- Security ---------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8  # idle timeout (sliding, see SAVE_EVERY_REQUEST)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_ENGINE = "django.contrib.sessions.backends.db"  # required: sessions are listed/revoked
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# django-csp 4.x. Alpine.js must use the CSP build (@alpinejs/csp) so no 'unsafe-eval' is needed.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "script-src": [SELF, NONCE],
        "style-src": [SELF, NONCE],
        "img-src": [SELF, "data:"],
        "font-src": [SELF],
        "connect-src": [SELF],
        "object-src": [NONE],
        "base-uri": [SELF],
        "form-action": [SELF],
        "frame-ancestors": [NONE],
    }
}

# --- Crispy -----------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# --- DRF --------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",  # Electron / mobile / integrations
        "rest_framework.authentication.SessionAuthentication",  # browser clients (CSRF enforced)
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "600/min", "auth": "10/min"},
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.api.exceptions.api_exception_handler",
}

# --- API tokens (JWT access + rotating, revocable refresh) -------------------
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# --- Celery (Redis) ---------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.outbox.*": {"queue": "outbox"},
}
CELERY_BEAT_SCHEDULE = {
    "outbox-dispatch": {"task": "apps.outbox.tasks.dispatch_outbox", "schedule": 10.0},
}

# --- Theme defaults (database-driven themes arrive in Phase 6) -------------
EMS_THEME_DEFAULTS = {
    "brand_name": "McDonald's Pakistan EMS",
    "tagline": "Employee Management System",
    "mode": "system",
    "tokens": {
        "color-primary": "#DA291C",
        "color-on-primary": "#FFFFFF",
        "color-secondary": "#FFC72C",
        "color-accent": "#27251F",
        "color-background": "#F7F7F5",
        "color-surface": "#FFFFFF",
        "color-text": "#1F1F1F",
        "color-muted": "#6B6B6B",
        "color-border": "#E3E3DF",
        "color-success": "#2E7D32",
        "color-warning": "#ED8B00",
        "color-danger": "#C62828",
        "color-info": "#1565C0",
        "radius": "0.5rem",
        "font-sans": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    },
    "dark_tokens": {
        "color-background": "#141414",
        "color-surface": "#1E1E1E",
        "color-text": "#F2F2F2",
        "color-muted": "#A0A0A0",
        "color-border": "#333333",
    },
}

# --- Logging ----------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
EMS_LOGGERS = ["ems.app", "ems.security", "ems.audit", "ems.celery", "ems.api"]


def build_logging(to_files: bool, level: str = "INFO") -> dict:
    """Separate application / security / audit / celery / api logs (JSON lines)."""
    handlers: dict = {"console": {"class": "logging.StreamHandler", "formatter": "json"}}
    loggers: dict = {}
    for name in EMS_LOGGERS:
        used = ["console"]
        if to_files:
            short = name.split(".")[1]
            handlers[f"file_{short}"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(LOG_DIR / f"{short}.log"),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 10,
                "formatter": "json",
                "encoding": "utf-8",
            }
            used.append(f"file_{short}")
        loggers[name] = {"handlers": used, "level": level, "propagate": False}
    loggers["django.security"] = {"handlers": ["console"], "level": "WARNING", "propagate": False}
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"json": {"()": "apps.common.logging.JsonFormatter"}},
        "handlers": handlers,
        "loggers": loggers,
        "root": {"handlers": ["console"], "level": "WARNING"},
    }


LOGGING = build_logging(False)

# --- Error handlers (class-based views) -------------------------------------
HANDLER400 = "apps.common.views.errors.bad_request"
HANDLER403 = "apps.common.views.errors.permission_denied"
HANDLER404 = "apps.common.views.errors.not_found"
HANDLER500 = "apps.common.views.errors.server_error"
