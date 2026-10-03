from django.core.management.base import BaseCommand

from apps.accounts.seed import seed_roles


class Command(BaseCommand):
    help = "Create the default roles (idempotent). Run after migrate."

    def handle(self, *args, **options):
        result = seed_roles()
        self.stdout.write(
            f"Roles created: {result['created']}; unknown permissions skipped: {result['missing_permissions']}"
        )
