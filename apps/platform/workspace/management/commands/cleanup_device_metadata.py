from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from workspace.models import DeviceConsoleSession, DeviceEnrollment, DeviceRateBucket


class Command(BaseCommand):
    help = 'Remove expired pairing secrets and old device/console metadata.'

    def handle(self, *args, **options):
        DeviceEnrollment.objects.filter(expires_at__lt=timezone.now()).delete()
        DeviceRateBucket.objects.filter(started_at__lt=timezone.now()-timedelta(days=1)).delete()
        DeviceConsoleSession.objects.filter(expires_at__lt=timezone.now()-timedelta(days=30)).delete()
        self.stdout.write('Expired device pairing, console and rate-limit metadata removed.')
