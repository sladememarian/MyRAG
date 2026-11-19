"""Deployment checks that Django's own `check --deploy` cannot make for us.

These run only with `python manage.py check --deploy`; normal development is
unaffected. Each error explains exactly which environment variable to set.
"""
from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security, deploy=True)
def production_settings(app_configs, **kwargs):
    """Fail loudly when production starts with development credentials."""
    issues = []

    if not settings.DEBUG and settings.SECRET_KEY_IS_INSECURE:
        issues.append(
            Error(
                "SECRET_KEY is missing or shorter than 50 characters.",
                hint=(
                    "Set SECRET_KEY to a random value of at least 50 characters. "
                    "Generate one with: python -c \"import secrets; "
                    "print(secrets.token_urlsafe(50))\""
                ),
                id="config.E001",
            )
        )

    database = settings.DATABASES["default"]
    password = ""
    if "postgresql" in database["ENGINE"]:
        password = database.get("PASSWORD") or ""
    # Placeholders shipped in .env.example are not secrets, and a very short
    # password is brute-forceable. Both are deployment errors, not warnings.
    placeholder = password.lower() in {
        "ragpass",
        "change-me-strong-password",
        "password",
        "postgres",
        "admin",
    }
    if not settings.DEBUG and password and (placeholder or len(password) < 12):
        issues.append(
            Error(
                "POSTGRES_PASSWORD is a placeholder or too short.",
                hint=(
                    "Set a unique POSTGRES_PASSWORD of at least 12 characters in "
                    "the environment. Generate one with: python -c "
                    "\"import secrets; print(secrets.token_urlsafe(24))\""
                ),
                id="config.E002",
            )
        )

    return issues
