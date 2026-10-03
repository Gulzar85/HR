from .base import *  # noqa: F403
from .base import build_logging

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
LOGGING = build_logging(False, "DEBUG")
