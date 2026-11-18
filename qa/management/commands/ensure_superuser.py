"""Create the admin user from environment variables if it does not exist."""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError


class Command(BaseCommand):
    help = "Create a superuser from DJANGO_SUPERUSER_* env vars when missing."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_* not set; skipping superuser creation.")
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Superuser '{username}' already exists.")
            return

        try:
            User.objects.create_superuser(username=username, email=email, password=password)
        except IntegrityError as exc:  # pragma: no cover - race between containers
            self.stderr.write(f"Could not create superuser: {exc}")
            return

        self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))
