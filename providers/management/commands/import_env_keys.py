"""Copy provider keys from .env into the admin's encrypted key store.

The admin is the primary way to manage keys, but a fresh checkout already has
OPENROUTER_API_KEY / ITERACOMPUTE_API_KEY in .env. This command imports them
once so the Model Management page is not empty, and is a no-op when a provider
already has at least one stored key.
"""
from django.core.management.base import BaseCommand

from providers.models import APIKey, Provider


class Command(BaseCommand):
    help = (
        "Import *_API_KEY values from the environment into the admin's key store "
        "for providers that have no keys yet."
    )

    def handle(self, *args, **options):
        created = 0
        for provider in Provider.objects.order_by("id"):
            if provider.api_keys.exists():
                self.stdout.write(
                    f"{provider.name}: already has keys, left unchanged."
                )
                continue
            raw = provider.env_api_key
            if not raw:
                self.stdout.write(
                    f"{provider.name}: no environment key, skipped."
                )
                continue
            key = APIKey(provider=provider, label="from .env", priority=10)
            key.set_secret(raw)
            key.save()
            created += 1
            self.stdout.write(
                self.style.SUCCESS(f"{provider.name}: imported key {key.masked}.")
            )
        self.stdout.write(self.style.SUCCESS(f"Imported {created} key(s)."))
