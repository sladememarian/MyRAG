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
    if (
        not settings.DEBUG
        and "postgresql" in database["ENGINE"]
        and database.get("PASSWORD") == "ragpass"
    ):
        issues.append(
            Error(
                "POSTGRES_PASSWORD is still the default 'ragpass'.",
                hint="Set a strong POSTGRES_PASSWORD in the environment.",
                id="config.E002",
            )
        )

    return issues
