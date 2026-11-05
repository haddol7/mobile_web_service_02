"""Create a local evidence author without exposing passwords on command lines."""
import json
import os
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create/update a local-only evidence author; use LOCAL_AUTHOR_PASSWORD environment variable."

    def add_arguments(self, parser):
        parser.add_argument("--credentials-file", help="Optional ignored evidence/private JSON for local browser verification.")
        parser.add_argument("--photo-fixture", help="Optional generated PNG path for browser multipart verification.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This command is for a DEBUG local database only.")
        username = os.environ.get("LOCAL_AUTHOR_USERNAME", settings.BLOG_OWNER_USERNAME)
        if username != settings.BLOG_OWNER_USERNAME:
            raise CommandError("Local author must match BLOG_OWNER_USERNAME.")
        password = os.environ.get("LOCAL_AUTHOR_PASSWORD")
        if not password:
            raise CommandError("Set LOCAL_AUTHOR_PASSWORD in the process environment; never pass it as an argument.")
        User = get_user_model()
        user, created = User.objects.get_or_create(username=username)
        try:
            validate_password(password, user)
        except ValidationError as error:
            if created:
                user.delete()
            raise CommandError("Local author password did not pass Django password validation.") from error
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        if options.get("credentials_file"):
            target = Path(options["credentials_file"]).resolve()
            evidence_private = (settings.BASE_DIR.parent / "evidence" / "private").resolve()
            if not target.is_relative_to(evidence_private):
                raise CommandError("Credentials may only be written under the ignored evidence/private directory.")
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump({"username": username, "password": password, "local_only": True}, output)
            os.chmod(target, 0o600)
        if options.get("photo_fixture"):
            from PIL import Image
            target = Path(options["photo_fixture"]).resolve()
            evidence_fixtures = (settings.BASE_DIR.parent / "evidence" / "test-runs").resolve()
            if not target.is_relative_to(evidence_fixtures):
                raise CommandError("Fixtures may only be written under ignored evidence/test-runs.")
            target.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGB", (900, 600), color=(138, 182, 142))
            # This is a synthetic original test image, not a submitted scene render.
            pixels = image.load()
            for y in range(image.height):
                for x in range(image.width):
                    pixels[x, y] = (112 + x * 45 // 900, 156 + y * 30 // 600, 122 + (x + y) * 30 // 1500)
            image.save(target, format="PNG")
            image.close()
        self.stdout.write(self.style.SUCCESS(f"Local evidence author ready: {username} (password not printed)."))
