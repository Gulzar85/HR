from django.core.management.base import BaseCommand

from apps.organizations.selectors import get_organization_tree
from apps.organizations.selectors.organization_selectors import flatten_tree


class Command(BaseCommand):
    help = "Print the organization tree (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--active-only", action="store_true")

    def handle(self, *args, **opts):
        tree = get_organization_tree(include_inactive=not opts["active_only"])
        for depth, node in flatten_tree(tree):
            self.stdout.write(f"{'    ' * depth}{node['code']}  {node['name']}  [{node['status']}]")
