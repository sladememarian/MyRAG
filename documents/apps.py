from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "documents"
    verbose_name = "Documents"

    def ready(self):
        # Register the project-wide deployment checks once Django is loaded.
        from config import checks  # noqa: F401
