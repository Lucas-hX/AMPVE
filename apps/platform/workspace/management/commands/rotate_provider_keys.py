from django.core.management.base import BaseCommand
from django.db import transaction
from workspace.models import ProviderConnection
from workspace.credentials import cipher


class Command(BaseCommand):
    help = 'Re-encrypt saved keys with the first key in the external MultiFernet key ring.'

    def handle(self, *args, **options):
        ring = cipher()
        with transaction.atomic():
            count = 0
            for connection in ProviderConnection.objects.select_for_update().all():
                connection.encrypted_key = ring.rotate(connection.encrypted_key.encode()).decode()
                connection.save(update_fields=['encrypted_key'])
                count += 1
        self.stdout.write(f'Rotated {count} encrypted connections. No provider requests were made.')
