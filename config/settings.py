from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CANONICAL_HOST=(str, ""),
)

BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_htmx",
    "django_celery_beat",
    "django_celery_results",
    # Local
    "core",
    "users",
    "matches",
    "betting",
    "rewards",
    "challenges",
    "bots",
    "board",
    "discussions",
    "activity",
    "flags",
    "website",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "website.middleware.BotScannerBlockMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "website.middleware.CanonicalHostMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
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
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "website.context_processors.theme",
                "rewards.context_processors.unseen_rewards",
                "betting.context_processors.bankruptcy",
                "betting.context_processors.parlay_slip",
                "activity.context_processors.activity_toasts",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        **env.db(),
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": True,
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
CANONICAL_HOST = env("CANONICAL_HOST")
USE_X_FORWARDED_HOST = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# CORS
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}

# Auth
AUTH_USER_MODEL = "users.User"
LOGIN_URL = "website:login"
LOGIN_REDIRECT_URL = "matches:dashboard"
LOGOUT_REDIRECT_URL = "matches:dashboard"

# Redis
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = False
CELERY_RESULT_EXPIRES = timedelta(days=7)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "America/Los_Angeles"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CELERY_BEAT_SCHEDULE = {
    "fetch-teams-monthly": {
        "task": "matches.tasks.fetch_teams",
        "schedule": crontab(hour=3, minute=0, day_of_month=1),  # 1st of month
    },
    "fetch-fixtures-daily": {
        "task": "matches.tasks.fetch_fixtures",
        "schedule": crontab(hour=3, minute=0),  # 3 AM daily
    },
    "fetch-standings-daily-midweek": {
        "task": "matches.tasks.fetch_standings",
        "schedule": crontab(hour=3, minute=0, day_of_week="tue,wed,thu"),
    },
    "fetch-standings-3h-matchdays": {
        "task": "matches.tasks.fetch_standings",
        "schedule": crontab(hour="0,3,6,9,12,15,18,21", minute=0, day_of_week="fri,sat,sun,mon"),
    },
    "fetch-live-scores-15m-on-matchdays": {
        "task": "matches.tasks.fetch_live_scores",
        # Every 15 min on matchdays, only during match hours (11 AM – 11 PM UTC)
        "schedule": crontab(minute="0,15,30,45", hour="11-23", day_of_week="fri,sat,sun,mon"),
    },
    "generate-odds-10m": {
        "task": "betting.tasks.generate_odds",
        # Cheap local computation — runs every 10 minutes to keep odds and fetched_at fresh
        "schedule": timedelta(minutes=10),
    },
    "prefetch-hype-data-6h": {
        "task": "matches.tasks.prefetch_upcoming_hype_data",
        "schedule": timedelta(hours=6),
    },
    "rotate-daily-challenges": {
        "task": "challenges.tasks.rotate_daily_challenges",
        "schedule": crontab(hour=5, minute=0),
    },
    "rotate-weekly-challenges": {
        "task": "challenges.tasks.rotate_weekly_challenges",
        "schedule": crontab(hour=4, minute=0, day_of_week="friday"),
    },
    "expire-challenges-15m": {
        "task": "challenges.tasks.expire_challenges",
        "schedule": timedelta(minutes=15),
    },
    "run-bot-strategies-daily-thu-sat": {
        "task": "bots.tasks.run_bot_strategies",
        "schedule": crontab(hour=8, minute=0, day_of_week="thu,fri,sat"),
    },
    "generate-prematch-comments-2h-thu-sat": {
        "task": "bots.tasks.generate_prematch_comments",
        "schedule": crontab(hour="8,10,12,14,16,18,20,22", minute=0, day_of_week="thu,fri,sat"),
    },
    "generate-postmatch-comments-30m-matchdays": {
        "task": "bots.tasks.generate_postmatch_comments",
        "schedule": crontab(minute="0,30", hour="14-23", day_of_week="fri,sat,sun,mon"),
    },
    # Board bot posts
    "board-postgw-wrapup-sunday": {
        "task": "board.tasks.generate_postgw_board_post",
        "schedule": crontab(hour=21, minute=0, day_of_week="sun"),
    },
    "board-midweek-prediction-wednesday": {
        "task": "board.tasks.generate_midweek_prediction_post",
        "schedule": crontab(hour=10, minute=0, day_of_week="wed"),
    },
    "board-weekend-preview-friday": {
        "task": "board.tasks.generate_weekend_preview_post",
        "schedule": crontab(hour=9, minute=0, day_of_week="fri"),
    },
    "board-season-outlook-monthly": {
        "task": "board.tasks.generate_season_outlook_post",
        "schedule": crontab(hour=12, minute=0, day_of_month=1),
    },
    "board-feature-request-biweekly": {
        "task": "board.tasks.generate_bot_feature_request_post",
        "schedule": crontab(hour=14, minute=0, day_of_week="tue"),  # every other tue (stubbed)
    },
    # Activity feed
    "broadcast-activity-event-20s": {
        "task": "activity.tasks.broadcast_next_activity_event",
        "schedule": 20.0,
    },
    "cleanup-old-activity-events-daily": {
        "task": "activity.tasks.cleanup_old_activity_events",
        "schedule": crontab(hour=4, minute=30),
    },
}

# External APIs
FOOTBALL_DATA_API_KEY = env("FOOTBALL_DATA_API_KEY", default="")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
API_TIMEOUT = 30
CURRENT_SEASON = "2025"
