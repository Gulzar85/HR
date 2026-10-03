from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.seed import seed_organization


class Command(BaseCommand):
    help = "Create the base organization hierarchy (idempotent). Development/testing helper."

    def add_arguments(self, parser):
        parser.add_argument("--company", default="McDonald's Pakistan")
        parser.add_argument(
            "--sample-operations",
            action="store_true",
            help="Also create example regions/areas/restaurants.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Required when DEBUG is off (production-like settings).",
        )

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["force"]:
            raise CommandError(
                "DEBUG is off. Re-run with --force if you really want to seed this database."
            )
        stats = seed_organization(opts["company"], sample_operations=opts["sample_operations"])
        self.stdout.write(
            self.style.SUCCESS(f"Organization seed complete: {stats['created']} unit(s) created.")
        )
