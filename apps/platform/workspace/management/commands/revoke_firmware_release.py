from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from workspace.models import FirmwareRelease


class Command(BaseCommand):
    help='Withdraw an imported release from new download/boot authorization; retain its audit history.'

    def add_arguments(self,parser):
        parser.add_argument('release_id')

    def handle(self,*args,**options):
        with transaction.atomic():
            release=FirmwareRelease.objects.select_for_update().filter(pk=options['release_id']).first()
            if not release:raise CommandError('Release not found.')
            if not release.revoked_at:
                release.revoked_at=timezone.now();release.save(update_fields=['revoked_at'])
        self.stdout.write('Release withdrawn. Existing physical outcomes still require a device report.')
