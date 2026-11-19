"""Admin site with a deliberate model order on the admin home page."""
from django.contrib.admin import AdminSite


class RAGAdminSite(AdminSite):
    """Stock admin site, except the QA history is listed first.

    Django sorts the models of an app alphabetically. Keeping question history
    on top matches how the project is used; model configuration lives in its
    own "Model Management" app, so the two concerns stay separate.
    """

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        for app in app_list:
            if app["app_label"] == "qa":
                app["models"].sort(
                    key=lambda model: (model["object_name"] != "Query", model["name"])
                )
        return app_list
