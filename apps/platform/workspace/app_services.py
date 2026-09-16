"""One-device declarative app rollout and bounded Core administration."""
import uuid
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .app_package_contract import verify, MAX_ENVELOPE
from .hardware_profiles import PROFILE
from .models import (AppPackage, Device, DeviceAdminCommand, DeviceAppAssignment,
                     DeviceCoreStatus)
from .release_contract import canonical, strict_json, read_bounded

KINDS = {'assign_app', 'kill_app', 'rollback_app', 'snapshot'}


class AppError(ValueError):
    pass


def trust():
    return strict_json(read_bounded(Path(settings.FIRMWARE_PUBLISHER_TRUST), 32768))


def verified(package):
    if package.revoked_at:
        raise AppError('This app package has been revoked.')
    try:
        policy, identity = verify(package.envelope, trust())
    except Exception as error:
        raise AppError('The signed app package is no longer valid.') from error
    if identity != package.pk or policy != package.policy:
        raise AppError('An imported package changed after review.')
    return policy


def import_package(envelope):
    policy, identity = verify(envelope, trust())
    with transaction.atomic():
        package, created = AppPackage.objects.get_or_create(pk=identity,
            defaults={'policy': policy, 'envelope': envelope})
        if not created and (package.policy != policy or package.envelope != envelope):
            raise AppError('A package identity is immutable.')
    return package


def hardware_compatible(device, policy):
    report = device.hardware_report
    return (device.hardware_profile == policy['profile_id'] and device.chip_revision == '1.3'
            and device.transport == 'wifi' and report.get('flash_bytes') == policy['flash_bytes']
            and type(report.get('psram_bytes')) is int
            and report['psram_bytes'] >= policy['minimum_psram_bytes']
            and report.get('compatibility', {}).get('layout_id') == policy['layout_id'])


def request(owner, device_id, kind, key, package_id=None):
    if kind not in KINDS or not isinstance(key, uuid.UUID):
        raise AppError('Unsupported or non-idempotent administration request.')
    with transaction.atomic():
        device = Device.objects.select_for_update().select_related('owner').get(pk=device_id, owner=owner)
        if device.revoked_at or not device.credential_hash or not owner.is_active:
            raise AppError('This owner cannot administer the device.')
        previous = DeviceAdminCommand.objects.filter(device=device, idempotency_key=key).first()
        if previous:
            if previous.kind != kind or (str(previous.package_id or '') != str(package_id or '')):
                raise AppError('This request key already identifies another command.')
            return previous
        package = None
        if kind == 'assign_app':
            status = DeviceCoreStatus.objects.filter(device=device, api_version=1).first()
            if not status or not status.core_version.startswith('0.1.23'):
                raise AppError('Core capability API v1 must be reported before assigning apps.')
            package = AppPackage.objects.select_for_update().get(pk=package_id)
            if not hardware_compatible(device, verified(package)):
                raise AppError('Package hardware is incompatible with this device.')
        elif package_id:
            raise AppError('This command has no package argument.')
        assignment, _ = DeviceAppAssignment.objects.select_for_update().get_or_create(device=device)
        if kind == 'assign_app':
            if assignment.package_id != package.pk:
                assignment.previous_package = assignment.package
            assignment.package = package
            assignment.disabled = False
        elif kind == 'kill_app':
            assignment.disabled = True
        elif kind == 'rollback_app':
            if not assignment.previous_package_id:
                raise AppError('No previous app package is available for rollback.')
            verified(assignment.previous_package)
            assignment.package, assignment.previous_package = assignment.previous_package, assignment.package
            assignment.disabled = False
        if kind != 'snapshot':
            assignment.save()
        return DeviceAdminCommand.objects.create(device=device, owner=owner,
            idempotency_key=key, kind=kind, package=package,
            expires_at=timezone.now() + timedelta(minutes=10))


def sync(device, data):
    if set(data) != {'protocol', 'api_version', 'core_version', 'active_id', 'app_version',
                     'heap_free_bytes', 'stack_min_bytes'} or type(data['protocol']) is not int or data['protocol'] != 1 or type(data['api_version']) is not int or data['api_version'] != 1:
        raise AppError('Unsupported Core status protocol.')
    if not isinstance(data['core_version'], str) or not data['core_version'].startswith('0.1.23') or len(data['core_version']) > 31 or not isinstance(data['app_version'], str) or len(data['app_version']) > 31 or not isinstance(data['active_id'], str) or (data['active_id'] and (len(data['active_id']) != 64 or any(c not in '0123456789abcdef' for c in data['active_id']))):
        raise AppError('Core or app identity exceeds the reported capability API.')
    for name, maximum in [('heap_free_bytes', 33554432), ('stack_min_bytes', 65536)]:
        if type(data[name]) is not int or not 0 <= data[name] <= maximum:
            raise AppError('Core health metric exceeds its bound.')
    with transaction.atomic():
        DeviceCoreStatus.objects.update_or_create(device=device, defaults={
            'core_version':data['core_version'], 'api_version':1, 'app_id':data['active_id'],
            'app_version':data['app_version'], 'heap_free_bytes':data['heap_free_bytes'],
            'stack_min_bytes':data['stack_min_bytes']})
        assignment = DeviceAppAssignment.objects.select_related('package', 'previous_package').filter(device=device).first()
        desired = assignment.package if assignment and not assignment.disabled else None
        if desired:
            try:
                policy = verified(desired)
                if not hardware_compatible(device, policy):
                    desired = None
            except AppError:
                desired = None
        revoked_active = bool(data['active_id'] and AppPackage.objects.filter(pk=data['active_id'], revoked_at__isnull=False).exists())
        revoked_ids = list(AppPackage.objects.filter(pk__in=[data['active_id'],
            assignment.previous_package_id if assignment else ''],revoked_at__isnull=False)
            .values_list('pk',flat=True)[:2])
        command = DeviceAdminCommand.objects.filter(device=device, state='queued',
            expires_at__gt=timezone.now()).order_by('created_at').first()
        return {'protocol':1, 'api_version':1,
                'desired_id':desired.pk if desired else '',
                'disabled':bool(assignment and assignment.disabled),
                'disabled_kind':assignment.package.policy['kind'] if assignment and assignment.disabled and assignment.package else '',
                'revoked_active':revoked_active,
                'revoked_ids':revoked_ids,
                'command':{'id':str(command.pk), 'kind':command.kind,
                           'package_id':command.package_id or ''} if command else None}


def package_for_device(device, identity):
    assignment = DeviceAppAssignment.objects.filter(device=device).first()
    if not assignment or assignment.disabled or identity not in {assignment.package_id, assignment.previous_package_id}:
        raise AppError('This signed package is not assigned to the device.')
    package = AppPackage.objects.get(pk=identity)
    if not hardware_compatible(device, verified(package)):
        raise AppError('Assigned package is incompatible with the device.')
    if len(canonical(package.envelope)) > MAX_ENVELOPE:
        raise AppError('Assigned package exceeds the RAM download bound.')
    return package.envelope


def acknowledge(device, command_id, result):
    if result not in {'applied', 'blocked', 'failed'}:
        raise AppError('Unsupported command result.')
    with transaction.atomic():
        command = DeviceAdminCommand.objects.select_for_update().get(pk=command_id, device=device)
        if command.state == 'acknowledged':
            if command.result_code != result:
                raise AppError('Command acknowledgement changed on retry.')
            return command
        if command.expires_at <= timezone.now():
            raise AppError('Administration command expired.')
        command.state = 'acknowledged'; command.result_code = result
        command.acknowledged_at = timezone.now(); command.save()
        return command


def revoke(package_id):
    with transaction.atomic():
        package = AppPackage.objects.select_for_update().get(pk=package_id)
        if not package.revoked_at:
            package.revoked_at = timezone.now(); package.save(update_fields=['revoked_at'])
            for assignment in DeviceAppAssignment.objects.select_for_update().filter(package=package):
                replacement=assignment.previous_package
                if replacement:
                    try:
                        verified(replacement)
                    except AppError:
                        replacement=None
                assignment.package=replacement;assignment.previous_package=package
                assignment.disabled=not bool(replacement);assignment.save()
        return package
