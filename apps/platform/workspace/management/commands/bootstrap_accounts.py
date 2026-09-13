import json
import os
import secrets
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from workspace.models import User


class Command(BaseCommand):
    help = 'Create initial accounts once, writing credentials to a private JSON outside the repository.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='/home/ampve/.config/ampve/demo-credentials.json')

    def handle(self, *args, **options):
        from django.conf import settings
        path = Path(options['output']).expanduser().resolve()
        if path.is_relative_to(settings.REPO_DIR):
            raise CommandError('Credentials must be outside the repository.')
        if path.exists() or User.objects.filter(email__in=['lucas@ampve.com', 'admin@ampve.com']).exists():
            raise CommandError('Bootstrap already exists. Use account administration; passwords were not changed.')
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        accounts = []
        # Write recovery credentials before database mutations, never to console or logs.
        for email, name, admin in [('lucas@ampve.com', 'Lucas', False), ('admin@ampve.com', 'Administrator', True)]:
            accounts.append({'email': email, 'name': name, 'password': secrets.token_urlsafe(24), 'role': 'administrator' if admin else 'user'})
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump({'url': 'https://ampve.com/accounts/login/', 'accounts': accounts,
                       'note': 'Private initial credentials. Change passwords in Settings after first sign-in; this file is not updated automatically.'}, out, indent=2)
        from django.db import transaction
        with transaction.atomic():
            for account in accounts:
                User.objects.create_user(account['email'], account['password'], first_name=account['name'],
                    is_staff=account['role'] == 'administrator', is_superuser=account['role'] == 'administrator')
        self.stdout.write(self.style.SUCCESS(f'Created separate demo and administrator accounts. Private credentials: {path}'))
