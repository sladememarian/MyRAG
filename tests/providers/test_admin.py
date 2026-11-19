"""Admin tests for the tabbed Model Management section."""
import pytest

from providers.models import APIKey, LLMModel, Provider


@pytest.fixture
def admin_client(client, django_user_model):
    user = django_user_model.objects.create_superuser(
        username="admin", email="admin@example.com", password="password123"
    )
    client.force_login(user)
    return client


def _change_url(provider):
    return f"/admin/providers/provider/{provider.pk}/change/"


def _management(prefix, total=0, initial=0):
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


@pytest.mark.django_db
def test_the_provider_list_opens_the_model_management_page(admin_client):
    """Requirement: Model Management opens on a provider tab, not a list."""
    response = admin_client.get("/admin/providers/provider/")

    assert response.status_code == 302
    assert "/admin/providers/provider/" in response["Location"]
    assert response["Location"].endswith("/change/")


@pytest.mark.django_db
def test_both_providers_are_tabs(admin_client):
    """Requirement: OpenRouter and Itera Compute each have their own tab."""
    openrouter = Provider.objects.get(slug="openrouter")
    itera = Provider.objects.get(slug="iteracompute")

    html = admin_client.get(_change_url(openrouter)).content.decode()

    assert "OpenRouter" in html
    assert "Itera Compute" in html
    assert _change_url(itera) in html
    assert "Answering with:" in html


@pytest.mark.django_db
def test_a_key_can_be_added_and_is_masked_afterwards(admin_client):
    """Requirement: several keys per provider are added without exposing them."""
    provider = Provider.objects.get(slug="iteracompute")

    response = admin_client.post(
        _change_url(provider),
        {
            "name": provider.name,
            "is_enabled": "on",
            "notes": "",
            **_management("api_keys", total=1),
            **_management("models"),
            "api_keys-0-label": "primary",
            "api_keys-0-api_key": "ick_live_abcdefghijklmnop",
            "api_keys-0-priority": "10",
            "api_keys-0-is_active": "on",
        },
    )

    assert response.status_code == 302
    key = APIKey.objects.get(provider=provider)
    assert key.label == "primary"
    assert key.secret.startswith("fernet:")
    assert "ick_live_abcdefghijklmnop" not in key.secret
    assert key.get_secret() == "ick_live_abcdefghijklmnop"

    html = admin_client.get(_change_url(provider)).content.decode()
    assert key.masked in html
    assert "ick_live_abcdefghijklmnop" not in html


@pytest.mark.django_db
def test_editing_a_key_without_typing_it_keeps_the_secret(admin_client):
    """Requirement: changing a label or priority never erases a stored key."""
    provider = Provider.objects.get(slug="openrouter")
    key = APIKey(provider=provider, label="old")
    key.set_secret("sk-or-v1-keep-me-please")
    key.save()

    response = admin_client.post(
        _change_url(provider),
        {
            "name": provider.name,
            "is_enabled": "on",
            "notes": "",
            **_management("api_keys", total=1, initial=1),
            **_management("models"),
            "api_keys-0-id": str(key.pk),
            "api_keys-0-provider": str(provider.pk),
            "api_keys-0-label": "renamed",
            "api_keys-0-api_key": "",
            "api_keys-0-priority": "20",
            "api_keys-0-is_active": "on",
        },
    )

    assert response.status_code == 302
    key.refresh_from_db()
    assert key.label == "renamed"
    assert key.priority == 20
    assert key.get_secret() == "sk-or-v1-keep-me-please"


@pytest.mark.django_db
def test_a_model_can_be_selected_for_the_active_provider(admin_client):
    """Requirement: the chosen model is stored and becomes the answering model."""
    provider = Provider.objects.get(slug="iteracompute")

    response = admin_client.post(
        _change_url(provider),
        {
            "name": provider.name,
            "is_enabled": "on",
            "notes": "",
            **_management("api_keys"),
            **_management("models", total=1),
            "models-0-slug": "Auto",
            "models-0-label": "Itera Auto",
            "models-0-is_active": "on",
        },
    )

    assert response.status_code == 302
    model = LLMModel.objects.get()
    assert model.provider == provider
    assert model.is_active
    assert model.qualified_slug == "iteracompute/Auto"


@pytest.mark.django_db
def test_test_connection_button_probes_every_key(admin_client, monkeypatch):
    """Requirement: one click checks the provider's keys from the admin."""
    provider = Provider.objects.get(slug="openrouter")
    calls = []

    def fake_probe(target):
        calls.append(target.slug)
        return [{"label": "primary", "ok": True, "error": "", "ms": 12}], ""

    monkeypatch.setattr("providers.admin.probe_provider", fake_probe)

    response = admin_client.post(f"/admin/providers/provider/{provider.pk}/test/")

    assert response.status_code == 302
    assert calls == ["openrouter"]


@pytest.mark.django_db
def test_providers_cannot_be_added_or_deleted(admin_client):
    """Requirement: the provider list is fixed to the two supported APIs."""
    provider = Provider.objects.get(slug="openrouter")

    assert admin_client.get("/admin/providers/provider/add/").status_code == 403
    response = admin_client.post(f"/admin/providers/provider/{provider.pk}/delete/")
    assert response.status_code == 403
    assert Provider.objects.filter(pk=provider.pk).exists()
