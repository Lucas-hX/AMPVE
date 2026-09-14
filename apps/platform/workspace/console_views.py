"""Authenticated semantic visual console for owners and outbound device clients."""
import json
import uuid
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .device_services import allowed, digest
from .device_views import bearer, context, device_api
from .models import Device, DeviceConsoleCommand, DeviceConsoleSession, DeviceConsoleState


PAGES = {'home', 'wifi', 'device', 'settings', 'companion'}
TARGETS = {
    'home', 'settings', 'wifi', 'device', 'companion', 'wifi_setup', 'pair',
    'speaker_test', 'cancel_update', 'mute',
}
INPUT_SOURCES = {'mouse', 'touch', 'keyboard'}
ACK_RESULTS = {'applied', 'ignored', 'blocked'}
SESSION_TTL = timedelta(minutes=10)
COMMAND_TTL = timedelta(seconds=8)


def _json(request, maximum=768):
    if (request.content_type != 'application/json' or int(request.META.get('CONTENT_LENGTH') or 0) > maximum
            or len(request.body) > maximum):
        raise ValueError()
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError()
    return data


def _session(user, device_id, session_id, lock=False):
    rows = DeviceConsoleSession.objects.select_related('device')
    if lock:
        rows = rows.select_for_update()
    return get_object_or_404(rows, pk=session_id,
        device_id=device_id, owner=user)


def _is_live(session, now=None):
    now = now or timezone.now()
    return session.ended_at is None and session.expires_at > now and session.device.revoked_at is None


def _initial_mode(device):
    display = device.hardware_report.get('capabilities', {}).get('display')
    return 'physical' if display in {'initialized', 'passed'} else 'virtual'


def _state_payload(device, state):
    return {
        'device': {'id': str(device.pk), 'name': device.name, 'connection': device.connection_state,
            'firmware_version': device.firmware_version or 'Unknown'},
        'screen': {'revision': state.revision, 'page': state.page, 'display_mode': state.display_mode,
            'remote_allowed': state.remote_allowed, 'updated_at': state.updated_at.isoformat()},
        'last_command': {'id': str(state.last_command_id) if state.last_command_id else None,
            'result': state.last_command_result or None},
    }


@never_cache
@ensure_csrf_cookie
@login_required
def console(request, pk):
    device = get_object_or_404(Device, pk=pk, owner=request.user)
    return render(request, 'workspace/device_console.html', context(
        title=f'{device.name} console', device=device))


@never_cache
@login_required
@require_POST
def start(request, pk):
    try:
        data = _json(request)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid console request.'}, status=400)
    if set(data) != {'protocol'} or type(data['protocol']) is not int or data['protocol'] != 1:
        return JsonResponse({'error': 'Invalid console request.'}, status=400)
    device = get_object_or_404(Device, pk=pk, owner=request.user)
    if not allowed(f'console-start:{request.user.pk}', 12, 60):
        return JsonResponse({'error': 'Too many console sessions. Wait a minute.'}, status=429)
    now = timezone.now()
    with transaction.atomic():
        device = get_object_or_404(Device.objects.select_for_update(), pk=pk, owner=request.user)
        if device.revoked_at:
            return JsonResponse({'error': 'This device is revoked.'}, status=409)
        previous = DeviceConsoleSession.objects.filter(device=device, owner=request.user, ended_at=None)
        DeviceConsoleCommand.objects.filter(session__in=previous, state='pending').update(state='expired')
        previous.update(ended_at=now)
        session = DeviceConsoleSession.objects.create(device=device, owner=request.user,
            expires_at=now + SESSION_TTL)
        state, _ = DeviceConsoleState.objects.get_or_create(device=device,
            defaults={'display_mode': _initial_mode(device)})
    payload = _state_payload(device, state)
    payload.update({'protocol': 1, 'session_id': str(session.pk),
        'expires_at': session.expires_at.isoformat(), 'poll_interval_ms': 800})
    return JsonResponse(payload, status=201)


@never_cache
@login_required
@require_GET
def state(request, pk, session_id):
    session = _session(request.user, pk, session_id)
    now = timezone.now()
    if not _is_live(session, now):
        return JsonResponse({'protocol': 1, 'active': False, 'reason': 'session_ended'}, status=410)
    state, _ = DeviceConsoleState.objects.get_or_create(device=session.device,
        defaults={'display_mode': _initial_mode(session.device)})
    payload = _state_payload(session.device, state)
    payload.update({'protocol': 1, 'active': True, 'expires_at': session.expires_at.isoformat(),
        'device_connected': bool(session.device_seen_at and session.device_seen_at > now - timedelta(seconds=2))})
    return JsonResponse(payload)


@never_cache
@login_required
@require_POST
def command(request, pk, session_id):
    try:
        data = _json(request)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid console command.'}, status=400)
    required = {'protocol', 'client_sequence', 'kind', 'input_source', 'target'}
    if (set(data) - required - {'x', 'y'} or not required <= set(data)
            or type(data['protocol']) is not int or data['protocol'] != 1):
        return JsonResponse({'error': 'Invalid console command.'}, status=400)
    if type(data['client_sequence']) is not int or not 1 <= data['client_sequence'] <= 1_000_000_000:
        return JsonResponse({'error': 'Invalid console command.'}, status=400)
    if (not all(isinstance(data[key], str) for key in ['kind', 'input_source', 'target'])
            or data['kind'] != 'activate' or data['input_source'] not in INPUT_SOURCES or data['target'] not in TARGETS):
        return JsonResponse({'error': 'Unsupported console command.'}, status=400)
    coordinates = {}
    for key, maximum in [('x', 1023), ('y', 599)]:
        value = data.get(key)
        if value is not None and (type(value) is not int or not 0 <= value <= maximum):
            return JsonResponse({'error': 'Invalid console coordinates.'}, status=400)
        coordinates[key] = value
    if data['input_source'] in {'mouse', 'touch'} and None in coordinates.values():
        return JsonResponse({'error': 'Pointer coordinates are required.'}, status=400)
    _session(request.user, pk, session_id)
    if not allowed(f'console-input:{session_id}', 180, 60):
        return JsonResponse({'error': 'Console input rate exceeded.'}, status=429)
    now = timezone.now()
    with transaction.atomic():
        session = _session(request.user, pk, session_id, lock=True)
        if not _is_live(session, now):
            return JsonResponse({'error': 'Console session expired.'}, status=410)
        if not session.device_seen_at or session.device_seen_at <= now - timedelta(seconds=2):
            return JsonResponse({'error': 'The device has not joined this console session.'}, status=409)
        state, _ = DeviceConsoleState.objects.get_or_create(device=session.device,
            defaults={'display_mode': _initial_mode(session.device)})
        if not state.remote_allowed:
            return JsonResponse({'error': 'Remote control was stopped on the device.'}, status=423)
        latest = session.commands.order_by('-client_sequence').values_list('client_sequence', flat=True).first() or 0
        if data['client_sequence'] <= latest:
            return JsonResponse({'error': 'Stale or replayed console command.'}, status=409)
        try:
            row = DeviceConsoleCommand.objects.create(session=session, device=session.device,
                client_sequence=data['client_sequence'], kind='activate', input_source=data['input_source'],
                target=data['target'], x=coordinates['x'], y=coordinates['y'], expires_at=now + COMMAND_TTL)
        except IntegrityError:
            return JsonResponse({'error': 'Stale or replayed console command.'}, status=409)
        session.last_activity_at = now
        session.save(update_fields=['last_activity_at'])
    return JsonResponse({'protocol': 1, 'command_id': str(row.pk), 'state': 'pending'}, status=202)


@never_cache
@login_required
@require_POST
def stop(request, pk, session_id):
    try:
        data = _json(request)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid console request.'}, status=400)
    if set(data) != {'protocol'} or type(data['protocol']) is not int or data['protocol'] != 1:
        return JsonResponse({'error': 'Invalid console request.'}, status=400)
    now = timezone.now()
    with transaction.atomic():
        session = _session(request.user, pk, session_id, lock=True)
        if session.ended_at is None:
            session.ended_at = now
            session.save(update_fields=['ended_at'])
        session.commands.filter(state='pending').update(state='expired')
    return JsonResponse({'protocol': 1, 'active': False})


@device_api
def sync(request, data, pk):
    token = bearer(request)
    required = {'protocol', 'state_revision', 'screen'}
    if (set(data) - required - {'acknowledgement'} or not required <= set(data)
            or type(data['protocol']) is not int or data['protocol'] != 1):
        raise ValueError()
    screen = data['screen']
    if not isinstance(screen, dict) or set(screen) != {'page', 'display_mode', 'remote_allowed'}:
        raise ValueError()
    if type(data['state_revision']) is not int or not 0 <= data['state_revision'] <= 1_000_000_000:
        raise ValueError()
    if (not isinstance(screen['page'], str) or not isinstance(screen['display_mode'], str)
            or screen['page'] not in PAGES or screen['display_mode'] not in {'physical', 'virtual'}
            or type(screen['remote_allowed']) is not bool):
        raise ValueError()
    acknowledgement = data.get('acknowledgement')
    if acknowledgement is not None:
        if (not isinstance(acknowledgement, dict) or set(acknowledgement) != {'id', 'result'}
                or not isinstance(acknowledgement['result'], str) or acknowledgement['result'] not in ACK_RESULTS):
            raise ValueError()
        try:
            acknowledgement['id'] = uuid.UUID(acknowledgement['id'])
        except (ValueError, TypeError, AttributeError):
            raise ValueError()
    candidate = Device.objects.select_related('owner').filter(pk=pk).first()
    if (not candidate or candidate.revoked_at or not candidate.owner.is_active or not candidate.credential_hash
            or not constant_time_compare(candidate.credential_hash, digest(token))):
        return JsonResponse({'error': 'Device permission denied.'}, status=401)
    if not allowed(f'console-device:{pk}', 180, 60):
        return JsonResponse({'error': 'Console poll rate exceeded.', 'poll_interval_ms': 1000}, status=429)
    now = timezone.now()
    with transaction.atomic():
        device = Device.objects.select_for_update().select_related('owner').filter(pk=pk).first()
        if not device or device.revoked_at or not device.owner.is_active or not device.credential_hash or not constant_time_compare(device.credential_hash, digest(token)):
            return JsonResponse({'error': 'Device permission denied.'}, status=401)
        state, _ = DeviceConsoleState.objects.select_for_update().get_or_create(device=device)
        state.revision = data['state_revision']
        state.page = screen['page']
        state.display_mode = screen['display_mode']
        state.remote_allowed = screen['remote_allowed']
        if acknowledgement:
            acknowledged = DeviceConsoleCommand.objects.select_for_update().filter(
                pk=acknowledgement['id'], device=device, state='dispatched').first()
            if acknowledged:
                acknowledged.state = 'acknowledged' if acknowledgement['result'] == 'applied' else acknowledgement['result']
                acknowledged.acknowledged_at = now
                acknowledged.save(update_fields=['state', 'acknowledged_at'])
                state.last_command_id = acknowledged.pk
                state.last_command_result = acknowledgement['result']
        state.save()
        expired = DeviceConsoleSession.objects.filter(device=device, ended_at=None, expires_at__lte=now)
        DeviceConsoleCommand.objects.filter(session__in=expired, state='pending').update(state='expired')
        expired.update(ended_at=now)
        session = DeviceConsoleSession.objects.select_for_update().filter(device=device, ended_at=None,
            expires_at__gt=now).order_by('-created_at').first()
        if not session:
            return JsonResponse({'protocol': 1, 'active': False, 'poll_interval_ms': 30000})
        previous_seen = session.device_seen_at
        session.device_seen_at = now
        session.save(update_fields=['device_seen_at'])
        session.commands.filter(state='pending', expires_at__lte=now).update(state='expired')
        if previous_seen and previous_seen <= now - timedelta(seconds=2):
            # Inputs queued before a connection gap never execute after the device returns.
            session.commands.filter(state='pending').update(state='expired')
        command_row = None
        if state.remote_allowed:
            command_row = session.commands.select_for_update().filter(state='pending', expires_at__gt=now).first()
            if command_row:
                # Dispatch once. A lost response drops one input event instead of replaying it after reconnect.
                command_row.state = 'dispatched'
                command_row.dispatched_at = now
                command_row.save(update_fields=['state', 'dispatched_at'])
    response = {'protocol': 1, 'active': True, 'session_id': str(session.pk),
        'poll_interval_ms': 600, 'expires_at': session.expires_at.isoformat(), 'command': None}
    if command_row:
        response['command'] = {'id': str(command_row.pk), 'sequence': command_row.client_sequence,
            'kind': command_row.kind, 'input_source': command_row.input_source, 'target': command_row.target,
            'x': command_row.x, 'y': command_row.y}
    return JsonResponse(response)
