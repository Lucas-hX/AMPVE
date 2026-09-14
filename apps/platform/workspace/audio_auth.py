"""One-use browser and device audio grants; provider keys remain server-side."""
import hashlib
import secrets
from datetime import timedelta
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from .models import AudioGrant, AudioSession, CompanionInstallation, Device, ProviderConnection, User


class DeviceGrantThrottled(ValueError):
    pass


def browser_is_valid(session_key, owner):
    session = Session.objects.filter(session_key=session_key, expire_date__gt=timezone.now()).first()
    if not session or not owner.is_active:
        return False
    data = session.get_decoded()
    return (str(data.get('_auth_user_id')) == str(owner.pk)
            and constant_time_compare(data.get('_auth_user_hash', ''), owner.get_session_auth_hash()))


def issue_grant(user, connection_id, session_key, mode):
    now = timezone.now()
    with transaction.atomic():
        # Serialize issuance per account, including simultaneous requests from tabs.
        User.objects.select_for_update().get(pk=user.pk)
        connection = ProviderConnection.objects.get(pk=connection_id, owner=user)
        if AudioGrant.objects.filter(owner=user, created_at__gt=now-timedelta(minutes=1)).count() >= 6:
            raise ValueError('Too many tests. Please wait a minute.')
        token = secrets.token_urlsafe(32)
        AudioGrant.objects.create(token_hash=hashlib.sha256(token.encode()).hexdigest(), owner=user,
            connection=connection, revision=connection.revision, browser_session=session_key,
            mode=mode, expires_at=now+timedelta(seconds=30))
    return token


def issue_device_grant(device_id):
    """Issue a short-lived grant only for an enabled, owned Companion installation."""
    now = timezone.now()
    with transaction.atomic():
        device = Device.objects.select_for_update().select_related('owner').filter(pk=device_id).first()
        installation = CompanionInstallation.objects.select_related('connection').filter(
            device=device, enabled=True).first()
        if (not device or device.revoked_at or not device.owner.is_active or not installation
                or installation.connection.owner_id != device.owner_id
                or installation.connection.validation != 'accepted'):
            raise ValueError('Companion is not ready for this device.')
        if AudioGrant.objects.filter(device=device, created_at__gt=now-timedelta(minutes=1)).count() >= 6:
            raise DeviceGrantThrottled('Too many Companion starts. Please wait a minute.')
        token = secrets.token_urlsafe(32)
        AudioGrant.objects.create(token_hash=hashlib.sha256(token.encode()).hexdigest(),
            owner=device.owner, connection=installation.connection,
            revision=installation.connection.revision, browser_session='', device=device,
            mode='device', expires_at=now+timedelta(seconds=30))
    return token


def consume_grant(token, expected_mode=None):
    if not isinstance(token, str) or not 30 <= len(token) <= 100:
        return None
    with transaction.atomic():
        grant = AudioGrant.objects.select_for_update().filter(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), used_at=None,
            expires_at__gt=timezone.now()).first()
        if not grant:
            return None
        connection = ProviderConnection.objects.select_for_update().select_related('owner').filter(pk=grant.connection_id).first()
        if expected_mode == 'browser' and grant.mode not in ('check', 'voice'):
            return None
        if expected_mode and expected_mode != 'browser' and grant.mode != expected_mode:
            return None
        if grant.mode == 'device':
            installation = CompanionInstallation.objects.filter(device_id=grant.device_id,
                connection_id=grant.connection_id, enabled=True).first()
            valid_authority = bool(grant.device_id and installation and connection and
                connection.owner_id == grant.owner_id and connection.owner.is_active and
                connection.revision == grant.revision and connection.validation == 'accepted' and
                not grant.device.revoked_at)
        else:
            valid_authority = bool(connection and connection.revision == grant.revision and
                browser_is_valid(grant.browser_session, connection.owner))
        if not valid_authority:
            return None
        grant.used_at = timezone.now()
        grant.save(update_fields=['used_at'])
        session = AudioSession.objects.create(owner=connection.owner, connection=connection,
            device_id=grant.device_id, revision=connection.revision,
            provider=connection.provider, mode=grant.mode)
        return grant, connection, session


def still_authorized(grant, connection):
    current = ProviderConnection.objects.select_related('owner').filter(pk=connection.pk, revision=grant.revision).first()
    if not current:
        return False
    if grant.mode == 'device':
        return bool(current.owner.is_active and current.validation == 'accepted' and
            CompanionInstallation.objects.filter(device_id=grant.device_id,
                connection=current, enabled=True, device__revoked_at=None).exists())
    return browser_is_valid(grant.browser_session, current.owner)


def finish_session(session_id, code):
    AudioSession.objects.filter(pk=session_id).update(status='ended', result_code=code, ended_at=timezone.now())


def record_check(connection_id, revision, code):
    ProviderConnection.objects.filter(pk=connection_id, revision=revision).update(
        validation='accepted' if code == 'accepted' else 'failed', result_code=code, checked_at=timezone.now())
