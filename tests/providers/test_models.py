"""Provider, API key and model tests."""
import pytest
from django.db import IntegrityError, transaction

from providers import crypto
from providers.models import APIKey, LLMModel, Provider


@pytest.mark.django_db
def test_the_supported_providers_are_seeded():
    """Requirement: each supported provider has a section."""
    assert list(Provider.objects.values_list("slug", flat=True)) == [
        "openrouter",
        "iteracompute",
        "tokenharbor",
        "orcarouter",
    ]
    assert Provider.objects.get(slug="iteracompute").name == "Itera Compute"


def test_api_keys_are_encrypted_at_rest():
    """Requirement: stored API keys are not readable in the database."""
    token = crypto.encrypt("ick_live_super-secret")

    assert token.startswith("fernet:")
    assert "ick_live_super-secret" not in token
    assert crypto.decrypt(token) == "ick_live_super-secret"


def test_a_corrupted_key_is_reported_as_unreadable():
    """Requirement: a rotated SECRET_KEY never yields a corrupted key."""
    assert crypto.decrypt("fernet:not-a-real-token") == ""
    assert crypto.decrypt("plain-text-key") == ""


@pytest.mark.django_db
def test_api_key_never_exposes_its_secret_in_the_string():
    """Requirement: keys are masked wherever a model is printed."""
    provider = Provider.objects.get(slug="iteracompute")
    key = APIKey(provider=provider, label="primary")
    key.set_secret("ick_live_7458f9ab655049c8542968c481462af5")
    key.save()

    assert key.masked == "ick_li…2af5"
    assert "7458f9ab" not in str(key)
    assert str(key) == "Itera Compute: primary"


@pytest.mark.django_db
def test_api_key_without_a_label_prints_only_the_mask():
    """Requirement: a stored key stays identifiable without being revealed."""
    provider = Provider.objects.get(slug="openrouter")
    key = APIKey(provider=provider)
    key.set_secret("sk-or-v1-1234567890abcdef")
    key.save()

    assert "sk-or-…cdef" in str(key)
    assert "1234567890" not in str(key)


@pytest.mark.django_db
def test_activating_a_model_deactivates_the_previous_one():
    """Requirement: exactly one model answers questions at any time."""
    openrouter = Provider.objects.get(slug="openrouter")
    itera = Provider.objects.get(slug="iteracompute")
    current = LLMModel.objects.create(
        provider=openrouter, slug="provider/old:free", is_active=True
    )
    target = LLMModel.objects.create(provider=itera, slug="Auto")

    target.is_active = True
    target.save()

    current.refresh_from_db()
    target.refresh_from_db()
    assert target.is_active
    assert not current.is_active
    assert LLMModel.objects.filter(is_active=True).count() == 1


@pytest.mark.django_db
def test_the_database_refuses_a_second_active_model():
    """Requirement: even raw SQL cannot break the single-active rule."""
    openrouter = Provider.objects.get(slug="openrouter")
    first = LLMModel.objects.create(provider=openrouter, slug="one")
    second = LLMModel.objects.create(provider=openrouter, slug="two")
    LLMModel.objects.filter(pk=first.pk).update(is_active=True)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LLMModel.objects.filter(pk=second.pk).update(is_active=True)


@pytest.mark.django_db
def test_a_model_id_is_unique_per_provider():
    """Requirement: the same model id can exist at both providers."""
    openrouter = Provider.objects.get(slug="openrouter")
    itera = Provider.objects.get(slug="iteracompute")
    LLMModel.objects.create(provider=openrouter, slug="Auto")
    LLMModel.objects.create(provider=itera, slug="Auto")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LLMModel.objects.create(provider=itera, slug="Auto")


@pytest.mark.django_db
def test_provider_api_roots_are_fixed_but_env_overridable(settings):
    """Requirement: base URLs cannot be edited to an arbitrary host in admin."""
    openrouter = Provider.objects.get(slug="openrouter")
    itera = Provider.objects.get(slug="iteracompute")

    assert openrouter.base_url == "https://openrouter.ai/api/v1"
    assert itera.base_url == "https://api.iteracompute.com/v1"

    settings.ITERACOMPUTE_BASE_URL = "https://proxy.example/v1/"
    assert itera.base_url == "https://proxy.example/v1"


@pytest.mark.django_db
def test_disabled_providers_are_skipped(settings):
    """Requirement: disabling a provider takes it out of the answering path."""
    from rag.llm import candidate_targets

    openrouter = Provider.objects.get(slug="openrouter")
    LLMModel.objects.create(provider=openrouter, slug="picked", is_active=True)
    key = APIKey(provider=openrouter)
    key.set_secret("secret")
    key.save()
    openrouter.is_enabled = False
    openrouter.save()
    settings.OPENROUTER_API_KEY = "env-key"
    settings.OPENROUTER_MODEL = "env-model"

    # Falls back to the documented .env default instead of the disabled model.
    assert candidate_targets()[0].model == "env-model"
