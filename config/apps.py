"""App config that installs the project's own admin site."""
from django.contrib.admin.apps import AdminConfig


class RAGAdminConfig(AdminConfig):
    """Use config.admin_site.RAGAdminSite instead of the stock admin site."""

    default_site = "config.admin_site.RAGAdminSite"
