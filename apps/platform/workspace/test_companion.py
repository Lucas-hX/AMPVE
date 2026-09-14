"""Companion assignment and device grant tests; no provider or hardware access."""
import hashlib
import secrets
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .audio_auth import consume_grant, still_authorized
from .device_services import PROFILE, digest
from .models import AudioGrant, CompanionInstallation, Device, ProviderConnection, User


class CompanionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('companion-owner@example.com', 'Fixture-password-42')
        self.other = User.objects.create_user('companion-other@example.com', 'Fixture-password-43')
        self.credential = secrets.token_urlsafe(32)
        self.device = Device.objects.create(owner=self.owner, name='Desk Companion',
            hardware_profile=PROFILE, credential_hash=digest(self.credential),
            firmware_version='fixture-companion')
        self.connection = ProviderConnection.objects.create(owner=self.owner, provider='openai',
            label='Fixture OpenAI', encrypted_key='fixture-ciphertext', validation='accepted')
        self.client.force_login(self.owner)
        self.machine = Client()

    def activate(self, connection=None):
        return self.client.post(reverse('device_companion', args=[self.device.pk]),
            {'action': 'activate', 'connection': connection or self.connection.pk})

    def ticket(self, credential=None, **payload):
        return self.machine.post(f'/api/devices/v1/{self.device.pk}/companion/session/',
            {'protocol': 1, **payload}, content_type='application/json',
            HTTP_AUTHORIZATION='Bearer ' + (credential or self.credential))

    def heartbeat(self):
        return self.machine.post(f'/api/devices/v1/{self.device.pk}/heartbeat/', {
            'protocol': 1, 'firmware_version': 'fixture-companion', 'chip_revision': '1.3',
            'transport': 'wifi', 'acknowledged_version': 0,
        }, content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.credential)

    def test_owner_activates_only_a_tested_owned_connection(self):
        self.assertEqual(Client().get(reverse('device_companion', args=[self.device.pk])).status_code, 302)
        foreign = Client(); foreign.force_login(self.other)
        self.assertEqual(foreign.get(reverse('device_companion', args=[self.device.pk])).status_code, 404)
        untested = ProviderConnection.objects.create(owner=self.owner, provider='gemini',
            label='Untested', encrypted_key='fixture', validation='untested')
        self.activate(untested.pk)
        self.assertFalse(CompanionInstallation.objects.exists())
        self.activate()
        installation = CompanionInstallation.objects.get(device=self.device)
        self.assertEqual(installation.connection, self.connection)
        self.device.refresh_from_db(); self.assertEqual(self.device.config_version, 2)
        page = self.client.get(reverse('device_companion', args=[self.device.pk]))
        self.assertContains(page, 'Fixture OpenAI')
        self.assertNotContains(page, 'fixture-ciphertext')

    def test_device_ticket_is_hashed_single_use_and_bound_to_device_mode(self):
        self.activate()
        response = self.ticket()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['frame_samples'], 480)
        token = response.json()['ticket']
        self.assertFalse(AudioGrant.objects.filter(token_hash=token).exists())
        self.assertTrue(AudioGrant.objects.filter(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), device=self.device).exists())
        self.assertIsNone(consume_grant(token, 'browser'))
        grant, connection, session = consume_grant(token, 'device')
        self.assertEqual((grant.mode, connection.pk, session.device_id),
            ('device', self.connection.pk, self.device.pk))
        self.assertIsNone(consume_grant(token, 'device'))

    def test_auth_activation_revocation_and_authority_are_enforced(self):
        self.assertEqual(self.ticket().status_code, 409)
        self.activate()
        self.assertEqual(self.ticket(credential=secrets.token_urlsafe(32)).status_code, 401)
        response = self.ticket(); grant, connection, _ = consume_grant(response.json()['ticket'], 'device')
        self.assertTrue(still_authorized(grant, connection))
        self.client.post(reverse('device_companion', args=[self.device.pk]), {'action': 'deactivate'})
        self.assertFalse(still_authorized(grant, connection))
        self.assertEqual(self.ticket().status_code, 409)
        self.activate(); Device.objects.filter(pk=self.device.pk).update(revoked_at=timezone.now())
        self.assertEqual(self.ticket().status_code, 401)

    def test_heartbeat_announces_assignment_without_starting_audio(self):
        response = self.heartbeat()
        self.assertFalse(response.json()['audio_available'])
        self.activate()
        Device.objects.filter(pk=self.device.pk).update(last_seen=timezone.now()-timedelta(seconds=31))
        response = self.heartbeat()
        self.assertTrue(response.json()['audio_available'])
        self.assertEqual(response.json()['configuration']['companion'],
            {'enabled': True, 'provider': 'openai'})
        self.assertFalse(AudioGrant.objects.exists())

    def test_active_connection_cannot_be_deleted_accidentally(self):
        self.activate()
        response = self.client.post(reverse('delete_connection', args=[self.connection.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProviderConnection.objects.filter(pk=self.connection.pk).exists())

    def test_device_endpoint_rejects_extra_and_oversized_input(self):
        self.activate()
        self.assertEqual(self.ticket(extra=True).status_code, 400)
        response = self.machine.post(f'/api/devices/v1/{self.device.pk}/companion/session/',
            'x' * 3000, content_type='application/json',
            HTTP_AUTHORIZATION='Bearer ' + self.credential)
        self.assertEqual(response.status_code, 413)

    def test_device_ticket_rate_limit_is_distinct_from_incomplete_setup(self):
        self.activate()
        for _ in range(6):
            self.assertEqual(self.ticket().status_code, 200)
        self.assertEqual(self.ticket().status_code, 429)

    def test_cross_owner_assignment_never_grants_or_advertises_audio(self):
        foreign = ProviderConnection.objects.create(owner=self.other, provider='openai',
            label='Foreign fixture', encrypted_key='fixture', validation='accepted')
        CompanionInstallation.objects.create(device=self.device, connection=foreign)
        self.assertEqual(self.ticket().status_code, 409)
        response = self.heartbeat()
        self.assertFalse(response.json()['audio_available'])
        self.assertEqual(response.json()['configuration']['companion'],
            {'enabled': False, 'provider': ''})
