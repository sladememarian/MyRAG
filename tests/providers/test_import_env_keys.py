"""Tests for the one-time .env key import command."""
from io import StringIO

import pytest
from django.core.management import call_command

from providers.models import APIKey, Provider


@pytest.mark.django_db
def test_env_keys_are_imported_into_the_encrypted_store(settings):
    """Requirement: a fresh checkout can import its existing .env keys."""
    settings.OPENROUTER_API_KEY = "sk-or-v1-from-env"
    settings.ITERACOMPUTE_API_KEY = "ick_live_from-env"
    settings.TOKENHARBOR_API_KEY = settings.ORCAROUTER_API_KEY = ""
    out = StringIO()

    call_command("import_env_keys", stdout=out)

    keys = APIKey.objects.order_by("provider_id")
    assert [key.provider.slug for key in keys] == ["openrouter", "iteracompute"]
    assert [key.get_secret() for key in keys] == [
        "sk-or-v1-from-env",
        "ick_live_from-env",
    ]
    assert all(key.secret.startswith("fernet:") for key in keys)
    assert "Imported 2 key(s)" in out.getvalue()


@pytest.mark.django_db
def test_import_never_overwrites_an_existing_key(settings):
    """Requirement: running the command twice leaves admin keys untouched."""
    provider = Provider.objects.get(slug="openrouter")
    key = APIKey(provider=provider, label="from admin")
    key.set_secret("sk-or-v1-admin-key")
    key.save()
    settings.OPENROUTER_API_KEY = "sk-or-v1-env-key"
    settings.ITERACOMPUTE_API_KEY = ""
    settings.TOKENHARBOR_API_KEY = settings.ORCAROUTER_API_KEY = ""

    call_command("import_env_keys", stdout=StringIO())

    assert provider.api_keys.count() == 1
    assert provider.api_keys.get().get_secret() == "sk-or-v1-admin-key"
