from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from workspace.models import AudioGrant, AudioSession


class Command(BaseCommand):
    help = 'Remove expired grants and audio metadata older than 30 days.'

    def handle(self, *args, **options):
        now = timezone.now()
        AudioGrant.objects.filter(expires_at__lt=now-timedelta(days=1)).delete()
        AudioSession.objects.filter(started_at__lt=now-timedelta(days=30)).delete()
        self.stdout.write('Expired audio metadata removed.')
