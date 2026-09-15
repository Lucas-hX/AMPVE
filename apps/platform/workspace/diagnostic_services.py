"""Authenticated typed Core events with stable retry IDs and bounded retention."""
import re
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .device_services import allowed
from .models import DeviceDiagnosticEvent

KINDS = {'boot', 'operation', 'error', 'snapshot', 'app'}
OPERATIONS = {'idle', 'companion_start', 'companion_capture', 'companion_stop',
              'app_download', 'app_activate', 'app_rollback', 'core_ota'}
ERRORS = {'', 'ssl_stack_fault', 'audio_queue', 'audio_io', 'network', 'package_rejected',
          'package_interrupted', 'package_revoked', 'ota_journal', 'storage', 'unknown'}
RESETS = {'', 'power_on', 'software', 'panic', 'watchdog', 'brownout', 'unknown'}
FIELDS = {'boot_id', 'sequence', 'kind', 'operation', 'error_code', 'reset_reason',
          'core_version', 'app_version', 'heap_free_bytes', 'stack_min_bytes'}
MAX_EVENTS = 4
KEEP_EVENTS = 128
KEEP_DAYS = 30


class DiagnosticError(ValueError):
    pass


def validate(event):
    if not isinstance(event, dict) or set(event) != FIELDS or not isinstance(event['boot_id'], str) or not re.fullmatch('[a-f0-9]{16}', event['boot_id']) or type(event['sequence']) is not int or not 0 <= event['sequence'] <= 65535:
        raise DiagnosticError('Invalid Core boot/event identity.')
    if any(not isinstance(event[field],str) for field in ('kind','operation','error_code','reset_reason')) or event['kind'] not in KINDS or event['operation'] not in OPERATIONS or event['error_code'] not in ERRORS or event['reset_reason'] not in RESETS:
        raise DiagnosticError('Core event contains unsupported text.')
    for field in ('core_version', 'app_version'):
        if not isinstance(event[field], str) or len(event[field]) > 31 or (event[field] and not re.fullmatch('[A-Za-z0-9._+-]+', event[field])):
            raise DiagnosticError('Invalid bounded Core/app version.')
    for field, maximum in [('heap_free_bytes', 33554432), ('stack_min_bytes', 65536)]:
        if event[field] is not None and (type(event[field]) is not int or not 0 <= event[field] <= maximum):
            raise DiagnosticError('Invalid bounded health metric.')
    return event


def upload(device, payload):
    if not isinstance(payload, dict) or set(payload) != {'protocol', 'events'} or type(payload['protocol']) is not int or payload['protocol'] != 1 or not isinstance(payload['events'], list) or not 1 <= len(payload['events']) <= MAX_EVENTS:
        raise DiagnosticError('Diagnostic upload exceeds the event bound.')
    events = [validate(event) for event in payload['events']]
    identities = [(event['boot_id'], event['sequence']) for event in events]
    if len(set(identities)) != len(identities):
        raise DiagnosticError('An upload repeats an event identity.')
    with transaction.atomic():
        if not allowed('diagnostics:'+str(device.pk), 30, 60):
            raise DiagnosticError('Diagnostic upload rate exceeded.')
        for event in events:
            values = {key:value for key,value in event.items() if key not in ('boot_id','sequence')}
            row, created = DeviceDiagnosticEvent.objects.get_or_create(device=device,
                boot_id=event['boot_id'], sequence=event['sequence'], defaults=values)
            if not created and any(getattr(row,key) != value for key,value in values.items()):
                raise DiagnosticError('A retried event changed its signed-in content.')
        old = DeviceDiagnosticEvent.objects.filter(device=device)
        old.filter(created_at__lt=timezone.now()-timedelta(days=KEEP_DAYS)).delete()
        retained = list(old.order_by('-created_at','-pk').values_list('pk', flat=True)[KEEP_EVENTS:])
        if retained:
            old.filter(pk__in=retained).delete()
    return {'accepted':len(events), 'retained':DeviceDiagnosticEvent.objects.filter(device=device).count()}
