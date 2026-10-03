from django.core.management.base import BaseCommand, CommandError

from apps.data_quality.registry import ERROR, run_checks


class Command(BaseCommand):
    help = "Run organization data-quality checks (read-only). Exit code 1 if errors are found."

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-warning", action="store_true")

    def handle(self, *args, **opts):
        issues = run_checks("organizations")
        for i in issues:
            self.stdout.write(f"[{i.severity.upper()}] {i.check}: {i.message}")
        errors = [i for i in issues if i.severity == ERROR]
        if errors or (opts["fail_on_warning"] and issues):
            raise CommandError(f"{len(errors)} error(s), {len(issues) - len(errors)} warning(s).")
        self.stdout.write(self.style.SUCCESS(f"Organization data OK ({len(issues)} warning(s))."))
