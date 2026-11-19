"""Model Management admin: providers, their API keys and their models.

The section is deliberately separate from Questions & Answers: it is
configuration, not history. Each provider is a tab, so switching between
OpenRouter and Itera Compute does not require searching a list.
"""
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from providers.models import APIKey, LLMModel, Provider
from rag.llm import active_model_label, fetch_free_models, probe_provider

STATUS_OK = '<span style="color:#1a7f37;font-weight:600">OK</span>'


class APIKeyForm(forms.ModelForm):
    """Model form whose `api_key` input is encrypted before it is stored.

    The database field (`secret`) holds ciphertext only, so the plain key is
    never rendered back into the HTML form. Leaving the box empty keeps the
    current key, which makes editing a label or priority safe.
    """

    api_key = forms.CharField(
        label="API key",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"size": 44}),
    )

    class Meta:
        model = APIKey
        fields = ("label", "api_key", "is_active", "priority")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["api_key"].help_text = (
            "Store the key once; it is encrypted and never shown again. "
            "Leave empty to keep the current key."
        )

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk is None and not (cleaned.get("api_key") or "").strip():
            self.add_error("api_key", "Paste the API key for this provider.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        raw = (self.cleaned_data.get("api_key") or "").strip()
        if raw:
            obj.set_secret(raw)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class APIKeyInline(admin.TabularInline):
    model = APIKey
    form = APIKeyForm
    extra = 1
    ordering = ("priority", "id")
    fields = (
        "label",
        "api_key",
        "key_mask",
        "is_active",
        "priority",
        "last_checked_at",
        "last_result",
    )
    readonly_fields = ("key_mask", "last_checked_at", "last_result")

    @admin.display(description="Stored key")
    def key_mask(self, obj):
        if obj is None or not obj.pk:
            return "—"
        return obj.masked

    @admin.display(description="Last test")
    def last_result(self, obj):
        if obj is None or obj.last_checked_at is None:
            return "not tested"
        if obj.last_ok:
            return format_html(STATUS_OK)
        return format_html(
            '<span style="color:#b42318;font-weight:600">Failed</span>'
            ' <span style="color:#666">{}</span>',
            (obj.last_error or "")[:120],
        )


class LLMModelInline(admin.TabularInline):
    model = LLMModel
    extra = 1
    fields = ("slug", "label", "is_active", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    """Tabbed provider configuration.

    Few providers exist, so the changelist redirects to the selected (or
    first) provider and the change form renders the others as tabs.
    """

    list_display = ("name", "slug", "is_enabled", "active_model_display", "keys_count")
    fields = ("name", "slug", "is_enabled", "notes")
    readonly_fields = ("slug",)
    inlines = (APIKeyInline, LLMModelInline)
    change_form_template = "admin/providers/provider/change_form.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Active model")
    def active_model_display(self, obj):
        active = LLMModel.objects.filter(is_active=True).select_related("provider").first()
        if active is None:
            return "— (using .env default)"
        return f"{active.provider.name}: {active}"

    @admin.display(description="API keys")
    def keys_count(self, obj):
        return obj.api_keys.count()

    def changelist_view(self, request, extra_context=None):
        active = LLMModel.objects.filter(is_active=True).values_list(
            "provider_id", flat=True
        ).first()
        provider = (
            Provider.objects.filter(pk=active).first()
            if active
            else Provider.objects.order_by("id").first()
        )
        if provider is None:
            return super().changelist_view(request, extra_context)
        return HttpResponseRedirect(
            reverse("admin:providers_provider_change", args=[provider.pk])
        )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["provider_tabs"] = [
            {
                "name": provider.name,
                "url": reverse("admin:providers_provider_change", args=[provider.pk]),
                "active": str(provider.pk) == str(object_id),
            }
            for provider in Provider.objects.order_by("id")
        ]
        extra_context["active_model_label"] = active_model_label()
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        custom = [
            path(
                "<path:object_id>/test/",
                self.admin_site.admin_view(require_POST(self.test_view)),
                name="providers_provider_test",
            ),
            path(
                "<path:object_id>/discover-free/",
                self.admin_site.admin_view(require_POST(self.discover_free_view)),
                name="providers_provider_discover_free",
            ),
        ]
        return custom + super().get_urls()

    def discover_free_view(self, request, object_id):
        """Add the provider's free models to its model list (inactive)."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        provider = get_object_or_404(Provider, pk=object_id)
        found, error = fetch_free_models(provider)
        if error:
            self.message_user(
                request, f"Could not list models: {error}", messages.ERROR
            )
        elif not found:
            self.message_user(
                request, f"{provider.name} lists no free models.", messages.WARNING
            )
        else:
            added = 0
            for item in found:
                _, created = LLMModel.objects.get_or_create(
                    provider=provider,
                    slug=item["slug"],
                    defaults={"label": item["label"]},
                )
                added += created
            self.message_user(
                request,
                f"{provider.name}: {len(found)} free model(s) found, {added} new. "
                "Tick 'Is active' on one, save, then use Test connection.",
                messages.SUCCESS,
            )
        return HttpResponseRedirect(
            reverse("admin:providers_provider_change", args=[provider.pk])
        )

    def test_view(self, request, object_id):
        if not self.has_change_permission(request):
            raise PermissionDenied
        provider = get_object_or_404(Provider, pk=object_id)
        results, error = probe_provider(provider)
        if error:
            self.message_user(request, error, messages.ERROR)
        for result in results:
            if result["ok"]:
                self.message_user(
                    request,
                    f"{result['label']}: connection OK in {result['ms']} ms.",
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    f"{result['label']}: {result['error']}",
                    messages.ERROR,
                )
        return HttpResponseRedirect(
            reverse("admin:providers_provider_change", args=[provider.pk])
        )
