from django.test import TestCase, Client
from django.urls import reverse
from django.db import IntegrityError, transaction
from .models import User, Application
from .security import client_ip
from django.test import RequestFactory


class PlatformTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lucas = User.objects.create_user('lucas@example.com', 'Testing-Secure-Password-42', first_name='Lucas')
        cls.other = User.objects.create_user('other@example.com', 'Testing-Other-Password-42', first_name='Other')
        cls.admin = User.objects.create_superuser('admin@example.com', 'Testing-Admin-Password-42')

    def sign_in(self, client=None):
        return (client or self.client).post(reverse('login'), {'username': 'LUCAS@example.com', 'password': 'Testing-Secure-Password-42'})

    def test_private_routes_require_login(self):
        for url in ['home', 'devices', 'onboarding', 'apps', 'connections', 'settings', 'password_change']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(reverse(url)).status_code, 302)
        self.assertEqual(self.client.get('/accounts/signup/').status_code, 404)

    def test_login_cookie_logout_and_invalid_password(self):
        response = self.sign_in()
        self.assertRedirects(response, reverse('home'))
        self.assertTrue(response.cookies['sessionid']['secure'])
        self.assertTrue(response.cookies['sessionid']['httponly'])
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), '/')
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(reverse('login'), {'username': self.lucas.email, 'password': 'wrong'})
        self.assertContains(response, 'Please enter a correct')

    def test_user_cannot_access_admin(self):
        self.sign_in()
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        self.assertEqual(self.client.post('/admin/workspace/user/add/', {'email': 'attacker@example.com', 'is_superuser': True}).status_code, 302)
        self.assertFalse(User.objects.filter(email='attacker@example.com').exists())

    def test_admin_can_access_accounts(self):
        self.client.force_login(self.admin, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(self.client.get('/admin/workspace/user/').status_code, 200)
        self.assertEqual(self.client.get('/admin/workspace/user/add/').status_code, 200)

    def test_profile_isolation_and_mass_assignment(self):
        self.sign_in()
        self.client.post(reverse('settings'), {'first_name': 'Updated', 'last_name': 'Name',
            'id': self.other.pk, 'email': self.other.email, 'is_staff': True, 'is_superuser': True})
        self.lucas.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual(self.lucas.first_name, 'Updated')
        self.assertEqual(self.lucas.email, 'lucas@example.com')
        self.assertFalse(self.lucas.is_staff or self.lucas.is_superuser)
        self.assertEqual(self.other.first_name, 'Other')
        self.assertNotContains(self.client.get(reverse('settings')), self.other.email)

    def test_csrf_blocks_login_and_profile_mutations(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.sign_in(client).status_code, 403)
        client.force_login(self.lucas, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(client.post(reverse('settings'), {'first_name': 'Forged'}).status_code, 403)

    def test_password_change_checks_old_password_and_invalidates_other_session(self):
        self.sign_in()
        second = Client(); self.sign_in(second)
        data = {'old_password': 'wrong', 'new_password1': 'Changed-Secure-Password-52', 'new_password2': 'Changed-Secure-Password-52'}
        self.assertEqual(self.client.post(reverse('password_change'), data).status_code, 200)
        data['old_password'] = 'Testing-Secure-Password-42'
        self.assertEqual(self.client.post(reverse('password_change'), data).status_code, 302)
        self.lucas.refresh_from_db()
        self.assertTrue(self.lucas.check_password(data['new_password1']))
        self.assertEqual(second.get(reverse('home')).status_code, 302)
        self.assertEqual(self.client.get(reverse('home')).status_code, 200)

    def test_no_open_redirect(self):
        response = self.client.post(reverse('login'), {'username': self.lucas.email,
            'password': 'Testing-Secure-Password-42', 'next': 'https://untrusted.example/'})
        self.assertEqual(response.url, '/home/')

    def test_lockout_is_shared_and_blocks_correct_password(self):
        for _ in range(5):
            self.client.post(reverse('login'), {'username': self.lucas.email, 'password': 'wrong'})
        self.assertEqual(self.sign_in(Client()).status_code, 429)

    def test_inactive_user_cannot_login(self):
        self.lucas.is_active = False; self.lucas.save()
        self.sign_in()
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_email_uniqueness(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user('LUCAS@example.com', 'unused')

    def test_catalog_and_truthful_states(self):
        self.sign_in()
        self.assertEqual(Application.objects.get(slug='companion').status, 'preview')
        for page in ['home', 'devices', 'onboarding', 'apps', 'connections', 'settings']:
            self.assertEqual(self.client.get(reverse(page)).status_code, 200)
        self.assertContains(self.client.get(reverse('devices')), 'No devices have been added')
        self.assertContains(self.client.get(reverse('connections')), 'Saving does not contact the provider')
        self.assertContains(self.client.get(reverse('apps')), 'In development')

    def test_workspace_navigation_uses_the_ampve_icon_sprite(self):
        self.sign_in()
        response = self.client.get(reverse('home'))
        for name in ['home', 'devices', 'apps', 'connections', 'settings']:
            with self.subTest(name=name):
                self.assertContains(response, f'ampve-icons-v1.svg#icon-{name}')
        navigation = response.content.decode().split('<nav aria-label="Workspace">', 1)[1].split('</nav>', 1)[0]
        self.assertEqual(navigation.count('class="ampve-icon"'), 5)
        self.assertEqual(navigation.count('aria-hidden="true"'), 5)
        for legacy_glyph in ['⌂', '▯', '⊞', '↗', '⚙']:
            self.assertNotIn(legacy_glyph, navigation)

    def test_public_landing_uses_optimized_versioned_hero_exports(self):
        response = self.client.get(reverse('landing'))
        self.assertContains(response, 'hero/exports/landing-devices-wide-v1.webp')
        self.assertContains(response, 'hero/exports/landing-devices-mobile-v1.webp')
        self.assertContains(response, 'fetchpriority="high"')
        self.assertNotContains(response, 'hero/source/')

    def test_onboarding_and_empty_state_use_truthful_microillustrations(self):
        self.sign_in()
        empty = self.client.get(reverse('devices'))
        self.assertContains(empty, 'microillustrations/no-devices-v1.svg')
        onboarding = self.client.get(reverse('onboarding'))
        for asset in ['usb-connect-v1.svg', 'device-ready-v1.svg', 'recovery-available-v1.svg']:
            with self.subTest(asset=asset):
                self.assertContains(onboarding, f'microillustrations/{asset}')
        self.assertContains(onboarding, 'id="setup-visual-label"')
        self.assertContains(onboarding, 'Duration appears after measurable progress begins.')

    def test_proxy_ip_only_trusted_locally(self):
        factory = RequestFactory()
        self.assertEqual(client_ip(factory.get('/', REMOTE_ADDR='127.0.0.1', HTTP_CF_CONNECTING_IP='192.0.2.7')), '192.0.2.7')
        self.assertEqual(client_ip(factory.get('/', REMOTE_ADDR='192.0.2.8', HTTP_CF_CONNECTING_IP='192.0.2.7')), '192.0.2.8')
