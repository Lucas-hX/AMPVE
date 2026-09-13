from django.core.management.base import BaseCommand, CommandError
from workspace.deployment_services import register_release


class Command(BaseCommand):
    help='Import a verified immutable signed release. Does not queue an update or authorize hardware writes.'

    def add_arguments(self,parser):
        parser.add_argument('--directory',required=True)

    def handle(self,*args,**options):
        try:
            release=register_release(options['directory'])
        except Exception as error:
            raise CommandError('Release import refused. Check the immutable package, independent trust registry and sequence uniqueness.') from error
        self.stdout.write('Registered release '+release.pk+'; no deployment created.')
