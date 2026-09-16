"""Import a reviewed signed declarative package into the curated catalog."""
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from workspace.app_package_contract import MAX_ENVELOPE
from workspace.app_services import import_package
from workspace.release_contract import strict_json, read_bounded


class Command(BaseCommand):
    help = 'Register one bounded, signed AMPVE capability API v1 package.'

    def add_arguments(self, parser):
        parser.add_argument('envelope', type=Path)

    def handle(self, *args, **options):
        path = options['envelope'].resolve()
        if not path.is_file():
            raise CommandError('Package envelope file is missing.')
        try:
            envelope = strict_json(read_bounded(path, MAX_ENVELOPE))
            package = import_package(envelope)
        except (OSError, ValueError, TypeError) as error:
            raise CommandError('Package signature, size or policy was rejected.') from error
        self.stdout.write(self.style.SUCCESS(
            f'Registered {package.policy["name"]} {package.policy["version"]} '
            f'({package.pk}); no device assignment was changed.'))
