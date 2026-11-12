"""Secure-by-default settings for the FootballStudio M1 foundation.

DATABASE_URL is required by default. An explicit SQLite fallback is allowed
only for local/unit tests; the Docker Compose stack always uses PostgreSQL.
"""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]
DEBUG = os.environ.get("DJANGO_DEBUG", "0").lower() in ("1", "true", "yes")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG and os.environ.get("DJANGO_ALLOW_SQLITE") == "1":
        SECRET_KEY = "local-tests-only-not-for-deployment"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set outside local tests.")

ALLOWED_HOSTS = [
    entry.strip()
    for entry in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if entry.strip()
]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS cannot be empty.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "axes",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "app.studio",
    "app.accounts",
    "app.clubs",
    "app.production",
]
MIDDLEWARE = [
    "app.config.observability.SafeRequestLoggingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
# Database-based lockouts work across Gunicorn workers.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_USE_ATTEMPT_EXPIRATION = True
AXES_LOCKOUT_PARAMETERS = ["ip_address", ["username", "ip_address"]]
AXES_USERNAME_FORM_FIELD = "username"
AXES_HTTP_RESPONSE_CODE = 429
AXES_ENABLE_RETRY_AFTER_HEADER = True
AXES_VERBOSE = False
ROOT_URLCONF = "app.config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "app" / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]
WSGI_APPLICATION = "app.config.wsgi.application"
ASGI_APPLICATION = "app.config.asgi.application"

database_url = os.environ.get("DATABASE_URL")
if database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            database_url, conn_max_age=60, conn_health_checks=True
        )
    }
elif os.environ.get("DJANGO_ALLOW_SQLITE") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    raise ImproperlyConfigured(
        "DATABASE_URL is required. Use DJANGO_ALLOW_SQLITE=1 only for local tests."
    )

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# FS-015a: independent kill switch. No approved title LLM provider exists.\n# Future activation requires a separately reviewed provider integration.\nTITLE_LLM_ENABLED = False\n\n# FS-004c: all paid services OFF by default. Provider credentials, approved
# price tables and USD ceiling must be explicitly configured by an operator.
# Never commit provider secrets or infer permission from a provider URL.
PAID_API_CALLS_ENABLED = os.environ.get("PAID_API_CALLS_ENABLED") == "1"
API_MONTHLY_BUDGET_USD = os.environ.get("API_MONTHLY_BUDGET_USD", "")
# Configured trusted pricing schedule, NOT user/request input. Loaded only
# as JSON, without credentials. The guard checks the credential environment
# variable named by each tariff without logging its value.
import json
try:
    PAID_API_RATE_CARDS = json.loads(os.environ.get("PAID_API_RATE_CARDS_JSON") or "{}")
except (ValueError, TypeError) as exc:
    raise ImproperlyConfigured("Invalid PAID_API_RATE_CARDS_JSON.") from exc
if not isinstance(PAID_API_RATE_CARDS, dict):
    raise ImproperlyConfigured("PAID_API_RATE_CARDS_JSON must be an object.")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
local_http = os.environ.get("DJANGO_LOCAL_HTTP", "0") == "1"
if local_http and (
    set(ALLOWED_HOSTS) - {"localhost", "127.0.0.1", "testserver"}
    or os.environ.get("DJANGO_TRUST_PROXY") == "1"
):
    raise ImproperlyConfigured(
        "DJANGO_LOCAL_HTTP is allowed only with loopback hosts and no trusted proxy."
    )
SESSION_COOKIE_SECURE = not DEBUG and not local_http
CSRF_COOKIE_SECURE = not DEBUG and not local_http
# Trust X-Forwarded-Proto ONLY when the web service has no published host ports
# and the sole ingress is the configured Cloudflare Tunnel connector.
trust_proxy = os.environ.get("DJANGO_TRUST_PROXY") == "1"
force_https = os.environ.get("DJANGO_FORCE_HTTPS", "0") == "1"
if force_https and (DEBUG or local_http or not trust_proxy):
    raise ImproperlyConfigured(
        "DJANGO_FORCE_HTTPS requires DEBUG=0, LOCAL_HTTP=0 and trusted tunnel proxy."
    )
if trust_proxy:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if force_https and not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "DJANGO_CSRF_TRUSTED_ORIGINS is required for HTTPS deployment."
    )
SECURE_SSL_REDIRECT = force_https
# Cloudflared passes HTTPS to the private HTTP origin. Internal Compose health
# checks use http://127.0.0.1:8000 and must stay healthy without a TLS redirect.
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"] if force_https else []
try:
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "0"))
except ValueError as exc:
    raise ImproperlyConfigured("DJANGO_HSTS_SECONDS must be an integer.") from exc
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured("DJANGO_HSTS_SECONDS must be nonnegative.")
if SECURE_HSTS_SECONDS and not force_https:
    raise ImproperlyConfigured("Enable HTTPS before enabling HSTS.")

# Structured, data-minimized error logs on stderr. This handles both our own
# HTTP status events and Django framework/security error records, including
# those containing an exception or untrusted Host. The formatter MUST NOT
# interpolate the original message or exception.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "safe_json": {"()": "app.config.safe_logging.SafeJsonFormatter"},
    },
    "handlers": {
        "safe_stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "safe_json",
        },
    },
    "loggers": {
        "footballstudio.http": {
            "handlers": ["safe_stderr"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["safe_stderr"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["safe_stderr"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
