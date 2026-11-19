"""Add the Token Harbor and Orca Router providers."""
from django.db import migrations, models

NEW_PROVIDERS = [
    (
        "tokenharbor",
        "Token Harbor",
        "OpenAI-compatible gateway (tokenharbor.ai).",
    ),
    (
        "orcarouter",
        "Orca Router",
        "OpenAI-compatible router with a free tier (orcarouter/free).",
    ),
]


def add_providers(apps, schema_editor):
    Provider = apps.get_model("providers", "Provider")
    for slug, name, notes in NEW_PROVIDERS:
        Provider.objects.update_or_create(
            slug=slug, defaults={"name": name, "notes": notes}
        )


def remove_providers(apps, schema_editor):
    Provider = apps.get_model("providers", "Provider")
    Provider.objects.filter(slug__in=[slug for slug, _, _ in NEW_PROVIDERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("providers", "0002_seed_providers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="provider",
            name="slug",
            field=models.CharField(
                choices=[
                    ("openrouter", "OpenRouter"),
                    ("iteracompute", "Itera Compute"),
                    ("tokenharbor", "Token Harbor"),
                    ("orcarouter", "Orca Router"),
                ],
                max_length=40,
                unique=True,
            ),
        ),
        migrations.RunPython(add_providers, remove_providers),
    ]
