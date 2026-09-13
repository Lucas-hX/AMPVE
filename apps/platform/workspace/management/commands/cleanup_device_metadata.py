from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from workspace.models import DeviceEnrollment, DeviceRateBucket


class Command(BaseCommand):
    help = 'Remove expired pairing secrets and old device rate-limit metadata.'

    def handle(self, *args, **options):
        DeviceEnrollment.objects.filter(expires_at__lt=timezone.now()).delete()
        DeviceRateBucket.objects.filter(started_at__lt=timezone.now()-timedelta(days=1)).delete()
        self.stdout.write('Expired device pairing and rate-limit metadata removed.')
