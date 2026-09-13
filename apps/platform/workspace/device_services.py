"""Device ownership and management; reported hardware is not attestation."""
import hashlib
import secrets
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from .models import Device, DeviceEnrollment, DeviceRateBucket, User
from .hardware_profiles import PROFILE as HARDWARE_PROFILE

PROFILE = HARDWARE_PROFILE['id']
HARDWARE_NAME = HARDWARE_PROFILE['name']


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def allowed(bucket, limit, seconds=600):
    # Durable fixed-window limits work across Gunicorn workers without a broker.
    now = timezone.now()
    with transaction.atomic():
        row, _ = DeviceRateBucket.objects.get_or_create(key=digest(bucket), defaults={'started_at': now})
        row = DeviceRateBucket.objects.select_for_update().get(pk=row.pk)
        if row.started_at <= now - timedelta(seconds=seconds):
            row.started_at, row.count = now, 0
        if row.count >= limit:
            return False
        row.count += 1
        row.save()
    return True


def begin_enrollment():
    code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
    proof = secrets.token_urlsafe(32)
    row = DeviceEnrollment.objects.create(code_hash=digest(code), proof_hash=digest(proof),
        hardware_profile=PROFILE, expires_at=timezone.now() + timedelta(minutes=10))
    return row, code, proof


def claim(user, code, name):
    with transaction.atomic():
        User.objects.select_for_update().get(pk=user.pk)
        row = DeviceEnrollment.objects.select_for_update().filter(code_hash=digest(code),
            expires_at__gt=timezone.now(), device=None).first()
        if not row:
            raise ValueError('This pairing code is invalid, expired, or already used.')
        if Device.objects.filter(owner=user).count() >= 20:
            raise ValueError('This private instance allows 20 device records per account.')
        device = Device.objects.create(owner=user, name=name, hardware_profile=row.hardware_profile)
        row.device = device
        row.save(update_fields=['device'])
    return device


def exchange(enrollment_id, proof, credential):
    # Firmware generates and persists its 256-bit credential before exchanging.
    # Retrying a lost response works only with the exact same proof/credential.
    with transaction.atomic():
        row = DeviceEnrollment.objects.select_for_update().filter(pk=enrollment_id,
            expires_at__gt=timezone.now()).first()
        if not row or not constant_time_compare(row.proof_hash, digest(proof)):
            raise ValueError('Invalid enrollment proof.')
        if not row.device_id:
            return None
        device = Device.objects.select_for_update().select_related('owner').get(pk=row.device_id)
        if device.revoked_at or not device.owner.is_active:
            raise ValueError('Device access is revoked.')
        hashed = digest(credential)
        if device.credential_hash and not constant_time_compare(device.credential_hash, hashed):
            raise ValueError('Credential was already issued.')
        device.credential_hash = hashed
        device.save(update_fields=['credential_hash'])
        return device
