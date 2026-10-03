from .base import *  # noqa: F403
from .base import BASE_DIR

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
MEDIA_ROOT = BASE_DIR / "media" / "_test"
ALLOWED_HOSTS = ["testserver", "localhost"]
