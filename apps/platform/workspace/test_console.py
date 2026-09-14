"""Software-only visual console protocol tests; no physical device is contacted."""
import secrets
from datetime import timedelta
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from .device_services import PROFILE, digest
from .models import Device, DeviceConsoleCommand, DeviceConsoleSession, DeviceConsoleState, User


class DeviceConsoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('console-owner@example.com', 'Fixture-password-42')
        cls.other = User.objects.create_user('console-other@example.com', 'Fixture-password-43')

    def setUp(self):
        self.credential = secrets.token_urlsafe(32)
        self.device = Device.objects.create(owner=self.owner, name='Desk display', hardware_profile=PROFILE,
            credential_hash=digest(self.credential), firmware_version='fixture-console')
        self.client.force_login(self.owner)
        self.machine = Client()

    def start(self):
        response = self.client.post(reverse('device_console_start', args=[self.device.pk]),
            {'protocol': 1}, content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.session_id = response.json()['session_id']
        return response.json()

    def command(self, sequence=1, target='settings', source='mouse', **extra):
        payload = {'protocol': 1, 'client_sequence': sequence, 'kind': 'activate',
            'input_source': source, 'target': target, **extra}
        if source != 'keyboard':
            payload.setdefault('x', 512)
            payload.setdefault('y', 300)
        return self.client.post(reverse('device_console_command', args=[self.device.pk, self.session_id]),
            payload, content_type='application/json')

    def sync(self, **changes):
        payload = {'protocol': 1, 'state_revision': 1,
            'screen': {'page': 'home', 'display_mode': 'physical', 'remote_allowed': True}, **changes}
        return self.machine.post(f'/api/devices/v1/{self.device.pk}/console/sync/', payload,
            content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.credential)

    def test_console_is_private_and_sets_csrf_cookie(self):
        page = self.client.get(reverse('device_console', args=[self.device.pk]))
        self.assertContains(page, 'Reach it from here.')
        self.assertIn('csrftoken', page.cookies)
        anonymous = Client()
        self.assertEqual(anonymous.get(reverse('device_console', args=[self.device.pk])).status_code, 302)
        foreign = Client(); foreign.force_login(self.other)
        self.assertEqual(foreign.get(reverse('device_console', args=[self.device.pk])).status_code, 404)
        self.assertEqual(foreign.post(reverse('device_console_start', args=[self.device.pk]),
            {'protocol': 1}, content_type='application/json').status_code, 404)

    def test_console_mutations_require_csrf(self):
        checked = Client(enforce_csrf_checks=True); checked.force_login(self.owner)
        self.assertEqual(checked.post(reverse('device_console_start', args=[self.device.pk]),
            {'protocol': 1}, content_type='application/json').status_code, 403)

    def test_session_dispatches_once_and_records_device_acknowledgement(self):
        opened = self.start()
        self.assertEqual(opened['screen']['display_mode'], 'virtual')
        self.assertIsNone(self.sync().json()['command'])
        # A full HTTPS exchange on the physical P4 was measured near 2.5 seconds.
        DeviceConsoleSession.objects.filter(pk=self.session_id).update(
            device_seen_at=timezone.now()-timedelta(seconds=3))
        queued = self.command(target='settings', x=900, y=560)
        self.assertEqual(queued.status_code, 202)
        command_id = queued.json()['command_id']
        first = self.sync()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['command']['id'], command_id)
        self.assertEqual(DeviceConsoleCommand.objects.get().state, 'dispatched')
        second = self.sync(state_revision=2,
            screen={'page': 'settings', 'display_mode': 'physical', 'remote_allowed': True},
            acknowledgement={'id': command_id, 'result': 'applied'})
        self.assertIsNone(second.json()['command'])
        command = DeviceConsoleCommand.objects.get()
        self.assertEqual(command.state, 'acknowledged')
        state = DeviceConsoleState.objects.get(device=self.device)
        self.assertEqual((state.page, state.last_command_result), ('settings', 'applied'))

    def test_heartbeat_announces_an_active_console_session(self):
        response = self.machine.post(f'/api/devices/v1/{self.device.pk}/heartbeat/', {
            'protocol': 1, 'firmware_version': 'fixture-console', 'chip_revision': '1.3',
            'transport': 'wifi', 'acknowledged_version': 0,
        }, content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.credential)
        self.assertFalse(response.json()['console']['active'])
        self.start()
        Device.objects.filter(pk=self.device.pk).update(last_seen=timezone.now()-timedelta(seconds=31))
        response = self.machine.post(f'/api/devices/v1/{self.device.pk}/heartbeat/', {
            'protocol': 1, 'firmware_version': 'fixture-console', 'chip_revision': '1.3',
            'transport': 'wifi', 'acknowledged_version': 0,
        }, content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + self.credential)
        self.assertEqual(response.json()['console'], {'active': True, 'poll_interval_ms': 600})

    def test_stale_replayed_and_unbounded_input_is_rejected(self):
        self.start()
        self.sync()
        self.assertEqual(self.command(sequence=2, source='keyboard').status_code, 202)
        self.assertEqual(self.command(sequence=2, source='keyboard').status_code, 409)
        self.assertEqual(self.command(sequence=1, source='keyboard').status_code, 409)
        self.assertEqual(self.command(sequence=3, target='terminal', source='keyboard').status_code, 400)
        self.assertEqual(self.command(sequence=3, x=1024).status_code, 400)
        self.assertEqual(self.command(sequence=3, target=[], source='keyboard').status_code, 400)
        response = self.client.post(reverse('device_console_command', args=[self.device.pk, self.session_id]),
            'x' * 1000, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_local_stop_blocks_commands_without_ending_local_ui(self):
        self.start()
        response = self.sync(screen={'page': 'home', 'display_mode': 'physical', 'remote_allowed': False})
        self.assertTrue(response.json()['active'])
        self.assertEqual(self.command(source='keyboard').status_code, 423)
        state = self.client.get(reverse('device_console_state', args=[self.device.pk, self.session_id])).json()
        self.assertFalse(state['screen']['remote_allowed'])

    def test_input_waiting_before_join_and_across_reconnect_is_not_replayed(self):
        self.start()
        self.assertEqual(self.command(source='keyboard').status_code, 409)
        self.sync()
        queued = self.command(source='keyboard')
        self.assertEqual(queued.status_code, 202)
        DeviceConsoleSession.objects.filter(pk=self.session_id).update(
            device_seen_at=timezone.now()-timedelta(seconds=7))
        response = self.sync()
        self.assertIsNone(response.json()['command'])
        self.assertEqual(DeviceConsoleCommand.objects.get(pk=queued.json()['command_id']).state, 'expired')

    def test_expired_stopped_revoked_and_wrong_credentials_are_rejected(self):
        self.start()
        self.sync()
        DeviceConsoleSession.objects.filter(pk=self.session_id).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.command(source='keyboard').status_code, 410)
        self.start()
        stopped = self.client.post(reverse('device_console_stop', args=[self.device.pk, self.session_id]),
            {'protocol': 1}, content_type='application/json')
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(self.command(source='keyboard').status_code, 410)
        self.credential = secrets.token_urlsafe(32)
        self.assertEqual(self.sync().status_code, 401)
        Device.objects.filter(pk=self.device.pk).update(revoked_at=timezone.now())
        self.assertEqual(self.client.post(reverse('device_console_start', args=[self.device.pk]),
            {'protocol': 1}, content_type='application/json').status_code, 409)

    def test_device_schema_is_bounded_and_browser_session_does_not_authenticate_it(self):
        self.start()
        self.assertEqual(self.client.post(f'/api/devices/v1/{self.device.pk}/console/sync/',
            {'protocol': 1}, content_type='application/json').status_code, 400)
        for changes in [
            {'screen': {'page': 'terminal', 'display_mode': 'physical', 'remote_allowed': True}},
            {'screen': {'page': 'home', 'display_mode': 'stream', 'remote_allowed': True}},
            {'screen': {'page': 'home', 'display_mode': 'physical', 'remote_allowed': True, 'secret': 'x'}},
            {'screen': {'page': [], 'display_mode': 'physical', 'remote_allowed': True}},
            {'state_revision': True},
            {'protocol': True},
        ]:
            self.assertEqual(self.sync(**changes).status_code, 400)
        self.assertEqual(self.machine.post(f'/api/devices/v1/{self.device.pk}/console/sync/',
            'x' * 3000, content_type='application/json',
            HTTP_AUTHORIZATION='Bearer ' + self.credential).status_code, 413)
