# =============================================================================
# Django Settings for the "Duplicate Account Merge Wizard" project.
# Minimal, single-file settings sufficient to run the wizard and its tests.
# =============================================================================
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# NOTE: In a real deployment, read SECRET_KEY from env/secret manager.
SECRET_KEY = "django-insecure-demo-key-do-not-use-in-prod"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local app that implements the merge wizard.
    "accounts",
]

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
        # The wizard ships its own templates under accounts/templates/.
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

# SQLite is enough for a demo/educational project and for running tests fast.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Use a custom user model so the merge wizard has natural "profile-like" fields
# (phone, address) without needing a separate Profile table. See accounts.models.
AUTH_USER_MODEL = "accounts.User"

# After login (not strictly required for the demo, but kept for completeness).
LOGIN_REDIRECT_URL = "/wizard/"
LOGIN_URL = "/admin/login/"
