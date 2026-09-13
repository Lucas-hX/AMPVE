"""Security tests use non-provider fixture keys and never call external APIs."""
import hashlib
from datetime import timedelta
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import User, ProviderConnection, AudioGrant
from .credentials import encrypt_key, decrypt_key
from .audio_auth import issue_grant, consume_grant, still_authorized, record_check

FIXTURE_KEY = 'TEST-FIXTURE-NOT-A-REAL-API-KEY-0123456789'


@override_settings(PROVIDER_ENCRYPTION_KEYS=[Fernet.generate_key().decode()])
class ConnectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner@example.com', 'Fixture-Password-42')
        self.other = User.objects.create_user('other@example.com', 'Fixture-Password-43')
        self.admin = User.objects.create_superuser('admin@example.com', 'Fixture-Password-44')
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')
        self.connection = ProviderConnection(owner=self.user, provider='openai', label='Fixture connection')
        self.connection.encrypted_key = encrypt_key(self.connection, FIXTURE_KEY)
        self.connection.save()

    def test_ciphertext_roundtrip_and_context_binding(self):
        self.assertNotIn(FIXTURE_KEY, self.connection.encrypted_key)
        self.assertEqual(decrypt_key(self.connection), FIXTURE_KEY)
        self.connection.owner = self.other
        with self.assertRaises(InvalidToken):
            decrypt_key(self.connection)

    def test_modified_ciphertext_and_wrong_master_key_rejected(self):
        original = self.connection.encrypted_key
        self.connection.encrypted_key = original[:-10] + 'AAAAAAAAAA'
        with self.assertRaises(InvalidToken):
            decrypt_key(self.connection)
        self.connection.encrypted_key = original
        with override_settings(PROVIDER_ENCRYPTION_KEYS=[Fernet.generate_key().decode()]):
            with self.assertRaises(InvalidToken):
                decrypt_key(self.connection)

    def test_create_and_responses_never_return_key(self):
        response = self.client.post(reverse('connections'), {'provider':'gemini', 'label':'Fixture Gemini', 'api_key':FIXTURE_KEY})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProviderConnection.objects.filter(owner=self.user).count(), 2)
        for route in [reverse('connections'), reverse('replace_key',args=[self.connection.pk])]:
            response = self.client.get(route)
            self.assertNotContains(response,FIXTURE_KEY)
            self.assertNotContains(response,self.connection.encrypted_key)
        response = self.client.post(reverse('connections'), {'provider':'invalid', 'label':'Fixture', 'api_key':FIXTURE_KEY})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response,FIXTURE_KEY)

    def test_cross_user_and_admin_cannot_use_owner_routes(self):
        for user in [self.other, self.admin]:
            self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')
            for name in ['replace_key','delete_connection','audio_ticket','voice_preview']:
                response = self.client.post(reverse(name,args=[self.connection.pk]), {'api_key':FIXTURE_KEY, 'mode':'check','consent':'yes'})
                self.assertEqual(response.status_code,404, name)
            self.assertNotContains(self.client.get(reverse('connections')), 'Fixture connection')
        self.assertEqual(ProviderConnection.objects.count(),1)

    def test_csrf_and_post_required(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.user,backend='django.contrib.auth.backends.ModelBackend')
        for name in ['delete_connection','audio_ticket','replace_key']:
            self.assertEqual(client.post(reverse(name,args=[self.connection.pk]),{}).status_code,403)
        self.assertEqual(self.client.get(reverse('delete_connection',args=[self.connection.pk])).status_code,405)
        self.assertEqual(self.client.get(reverse('audio_ticket',args=[self.connection.pk])).status_code,405)

    def test_replacement_resets_validation_and_stale_check_is_ignored(self):
        record_check(self.connection.pk,1,'accepted')
        self.client.post(reverse('replace_key',args=[self.connection.pk]),{'api_key':FIXTURE_KEY+'new'})
        record_check(self.connection.pk,1,'accepted')
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.revision,2)
        self.assertEqual(self.connection.validation,'untested')
        self.assertEqual(decrypt_key(self.connection),FIXTURE_KEY+'new')

    def issue(self):
        return issue_grant(self.user,self.connection.pk,self.client.session.session_key,'check')

    def test_ticket_requires_explicit_consent_and_is_not_key(self):
        url=reverse('audio_ticket',args=[self.connection.pk])
        self.assertEqual(self.client.post(url,{'mode':'check'}).status_code,400)
        response=self.client.post(url,{'mode':'check','consent':'yes'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn(FIXTURE_KEY,response.content.decode())
        token=response.json()['ticket']
        self.assertFalse(AudioGrant.objects.filter(token_hash=token).exists())
        self.assertTrue(AudioGrant.objects.filter(token_hash=hashlib.sha256(token.encode()).hexdigest()).exists())

    def test_ticket_is_single_use_and_expires(self):
        token=self.issue()
        self.assertIsNotNone(consume_grant(token))
        self.assertIsNone(consume_grant(token))
        token=self.issue()
        AudioGrant.objects.filter(used_at=None).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertIsNone(consume_grant(token))

    def test_logout_and_password_change_invalidate_grants(self):
        token=self.issue()
        self.client.post(reverse('logout'))
        self.assertIsNone(consume_grant(token))
        self.client.force_login(self.user,backend='django.contrib.auth.backends.ModelBackend')
        token=self.issue()
        self.user.set_password('New-Fixture-Password-52');self.user.save()
        self.assertIsNone(consume_grant(token))

    def test_delete_and_replace_revoke_active_authority(self):
        grant, connection, session=consume_grant(self.issue())
        self.assertTrue(still_authorized(grant,connection))
        self.client.post(reverse('replace_key',args=[connection.pk]),{'api_key':FIXTURE_KEY+'new'})
        self.assertFalse(still_authorized(grant,connection))
        grant, connection, session=consume_grant(self.issue())
        self.client.post(reverse('delete_connection',args=[connection.pk]))
        self.assertFalse(still_authorized(grant,connection))
        self.assertFalse(ProviderConnection.objects.filter(pk=connection.pk).exists())

    def test_connection_owner_not_taken_from_post(self):
        self.client.post(reverse('connections'),{'provider':'openai','label':'New fixture','api_key':FIXTURE_KEY,'owner':self.other.pk})
        self.assertEqual(ProviderConnection.objects.get(label='New fixture').owner,self.user)

    def test_grant_rate_limit(self):
        for _ in range(6):self.issue()
        with self.assertRaises(ValueError):self.issue()

    def test_rotation_keeps_existing_credentials_readable(self):
        from django.conf import settings
        from django.core.management import call_command
        old=settings.PROVIDER_ENCRYPTION_KEYS[0];new=Fernet.generate_key().decode()
        with override_settings(PROVIDER_ENCRYPTION_KEYS=[new,old]):
            call_command('rotate_provider_keys',verbosity=0)
        self.connection.refresh_from_db()
        with override_settings(PROVIDER_ENCRYPTION_KEYS=[new]):
            self.assertEqual(decrypt_key(self.connection),FIXTURE_KEY)
