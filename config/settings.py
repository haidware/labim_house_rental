import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

IS_RENDER = bool(os.getenv("RENDER"))
IS_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))
IS_PRODUCTION = IS_RENDER or IS_RAILWAY
DEBUG = (
    os.getenv("DJANGO_DEBUG", "false" if IS_PRODUCTION else "true").lower()
    == "true"
)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = (
        secrets.token_urlsafe(64)
        if IS_PRODUCTION
        else "local-only-insecure-secret"
    )
    if IS_PRODUCTION:
        import logging

        logging.getLogger("django.security").warning(
            "DJANGO_SECRET_KEY is unset; using an ephemeral key. "
            "Set a persistent secret in the production environment."
        )
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]
render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if not render_hostname:
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    render_hostname = urlsplit(render_url).hostname if render_url else ""
railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
railway_hostname = (
    urlsplit(
        railway_public_domain
        if "://" in railway_public_domain
        else f"//{railway_public_domain}"
    ).hostname
    if railway_public_domain
    else ""
)
for platform_hostname in (render_hostname, railway_hostname):
    if platform_hostname and platform_hostname not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(platform_hostname)
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
for platform_hostname in (render_hostname, railway_hostname):
    if platform_hostname:
        platform_origin = f"https://{platform_hostname}"
        if platform_origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(platform_origin)

if not DEBUG and not ALLOWED_HOSTS:
    raise RuntimeError("Set DJANGO_ALLOWED_HOSTS before running in production.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rentals.apps.RentalsConfig",
]

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = (
    os.getenv("SUPABASE_ANON_KEY", "")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
)
SUPABASE_SERVICE_ROLE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.getenv("SUPABASE_SECRET_KEY", "")
)
SUPABASE_STORAGE_BUCKET = "rental-listing-photos"
RENTAL_INSPECTION_WHATSAPP_NUMBER = os.getenv(
    "RENTAL_INSPECTION_WHATSAPP_NUMBER",
    "+2348127499576",
)
supabase_api_values = (
    SUPABASE_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
)
if any(supabase_api_values) and not all(supabase_api_values):
    raise RuntimeError(
        "Set SUPABASE_URL, SUPABASE_ANON_KEY (or SUPABASE_PUBLISHABLE_KEY), "
        "and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) together."
    )
SUPABASE_API_ENABLED = bool(
    all(supabase_api_values)
)
RENTAL_STAFF_USERNAME = os.getenv("RENTAL_STAFF_USERNAME", "")
RENTAL_STAFF_PASSWORD = os.getenv("RENTAL_STAFF_PASSWORD", "")
if SUPABASE_API_ENABLED and not (
    RENTAL_STAFF_USERNAME and RENTAL_STAFF_PASSWORD
):
    raise RuntimeError(
        "Configure RENTAL_STAFF_USERNAME and RENTAL_STAFF_PASSWORD when using Supabase REST mode."
    )
if IS_PRODUCTION:
    missing_supabase_settings = [
        name
        for name, value in (
            ("SUPABASE_URL", SUPABASE_URL),
            ("SUPABASE_ANON_KEY or SUPABASE_PUBLISHABLE_KEY", SUPABASE_ANON_KEY),
            (
                "SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY",
                SUPABASE_SERVICE_ROLE_KEY,
            ),
            ("RENTAL_STAFF_USERNAME", RENTAL_STAFF_USERNAME),
            ("RENTAL_STAFF_PASSWORD", RENTAL_STAFF_PASSWORD),
        )
        if not value
    ]
    if missing_supabase_settings:
        raise RuntimeError(
            "Configure these private production environment variables: "
            + ", ".join(missing_supabase_settings)
        )

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FLUTTER_WEB_BUILD_DIRECTORY = BASE_DIR / "flutter_app" / "build" / "web"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
