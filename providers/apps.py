"""App config for the model-management section of the admin."""
from django.apps import AppConfig


class ProvidersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "providers"
    verbose_name = "Model Management"
