import documents.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                (
                    "file",
                    models.FileField(
                        help_text="Only .docx files are accepted.",
                        upload_to="documents/%Y/%m/",
                        validators=[documents.validators.validate_docx_file],
                    ),
                ),
                ("full_text", models.TextField(blank=True, default="")),
                ("indexed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Document",
                "verbose_name_plural": "Documents",
                "ordering": ["-created_at"],
            },
        ),
    ]
