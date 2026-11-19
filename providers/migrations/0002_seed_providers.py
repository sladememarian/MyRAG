"""Create the two supported providers and keep any model already selected.

Before this app existed, the admin stored model ids in `qa.LLMModel` without a
provider. Those rows are copied to OpenRouter so an existing selection keeps
answering after the upgrade; the old table is dropped by qa.0004, which runs
after this migration.
"""
from django.db import migrations

PROVIDERS = [
    (
        "openrouter",
        "OpenRouter",
        "OpenAI-compatible router with free and paid models.",
    ),
    (
        "iteracompute",
        "Itera Compute",
        "OpenAI-compatible API whose Auto model routes the request.",
    ),
]


def seed_providers(apps, schema_editor):
    Provider = apps.get_model("providers", "Provider")
    Model = apps.get_model("providers", "LLMModel")
    OldModel = apps.get_model("qa", "LLMModel")

    for slug, name, notes in PROVIDERS:
        Provider.objects.update_or_create(
            slug=slug, defaults={"name": name, "notes": notes}
        )

    openrouter = Provider.objects.get(slug="openrouter")
    for old in OldModel.objects.all():
        Model.objects.update_or_create(
            provider=openrouter,
            slug=old.slug,
            defaults={"label": old.label, "is_active": old.is_active},
        )


def remove_providers(apps, schema_editor):
    Provider = apps.get_model("providers", "Provider")
    Provider.objects.filter(slug__in=[slug for slug, _, _ in PROVIDERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("providers", "0001_initial"),
        ("qa", "0003_llmmodel_alter_query_options"),
    ]

    operations = [
        migrations.RunPython(seed_providers, remove_providers),
    ]
