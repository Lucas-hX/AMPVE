"""One-use browser grants; never reuse browser cookies as device credentials."""
import hashlib
import secrets
from datetime import timedelta
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from .models import AudioGrant, AudioSession, ProviderConnection, User


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


def consume_grant(token):
    if not isinstance(token, str) or not 30 <= len(token) <= 100:
        return None
    with transaction.atomic():
        grant = AudioGrant.objects.select_for_update().filter(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), used_at=None,
            expires_at__gt=timezone.now()).first()
        if not grant:
            return None
        connection = ProviderConnection.objects.select_for_update().select_related('owner').filter(pk=grant.connection_id).first()
        if not connection or connection.revision != grant.revision or not browser_is_valid(grant.browser_session, connection.owner):
            return None
        grant.used_at = timezone.now()
        grant.save(update_fields=['used_at'])
        session = AudioSession.objects.create(owner=connection.owner, connection=connection,
            revision=connection.revision, provider=connection.provider, mode=grant.mode)
        return grant, connection, session


def still_authorized(grant, connection):
    current = ProviderConnection.objects.select_related('owner').filter(pk=connection.pk, revision=grant.revision).first()
    return bool(current and browser_is_valid(grant.browser_session, current.owner))


def finish_session(session_id, code):
    AudioSession.objects.filter(pk=session_id).update(status='ended', result_code=code, ended_at=timezone.now())


def record_check(connection_id, revision, code):
    ProviderConnection.objects.filter(pk=connection_id, revision=revision).update(
        validation='accepted' if code == 'accepted' else 'failed', result_code=code, checked_at=timezone.now())
