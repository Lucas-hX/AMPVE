import json
import re
from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_POST
from .models import Device, DeviceEnrollment
from .forms import ClaimDeviceForm, DeviceSettingsForm
from .device_services import PROFILE, HARDWARE_NAME, allowed, begin_enrollment, claim, exchange, digest
from .security import client_ip
from .hardware_reports import validate_report, display_report
from .hardware_profiles import runtime_reasons, REASON_LABELS


def context(**extra):
    return {'section': 'devices', 'hardware_name': HARDWARE_NAME, **extra}


@never_cache
@login_required
def devices(request):
    return render(request, 'workspace/devices.html', context(title='Your devices. Your space.',
        devices=Device.objects.filter(owner=request.user)))


@never_cache
@login_required
@sensitive_post_parameters('code')
def onboarding(request):
    form = ClaimDeviceForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if not allowed(f'claim:{request.user.pk}', 6, 60):
            form.add_error(None, 'Too many pairing attempts. Wait a minute and try again.')
        elif form.is_valid():
            try:
                device = claim(request.user, form.cleaned_data['code'], form.cleaned_data['name'])
            except ValueError as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, 'Device claimed. Waiting for its authenticated connection.')
                return redirect('device_detail', pk=device.pk)
    return render(request, 'workspace/onboarding.html', context(title='Bring your device.', form=form))


@never_cache
@login_required
def detail(request, pk):
    device = get_object_or_404(Device, pk=pk, owner=request.user)
    form = DeviceSettingsForm(request.POST or None, initial={'name': device.name,
        'volume': device.volume, 'microphone_muted': device.microphone_muted})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            device = get_object_or_404(Device.objects.select_for_update(), pk=pk, owner=request.user)
            if device.revoked_at:
                form.add_error(None, 'This device is revoked. Settings cannot be changed.')
            else:
                for field, value in form.cleaned_data.items():
                    setattr(device, field, value)
                device.config_version += 1
                device.save()
                messages.success(request, 'Settings saved. They take effect only after device acknowledgement.')
                return redirect('device_detail', pk=pk)
    return render(request, 'workspace/device_detail.html', context(title=device.name, device=device, form=form,
        capabilities=display_report(device.hardware_report),
        compatibility_reasons=[REASON_LABELS[key] for key in runtime_reasons(device)]))


@never_cache
@login_required
@require_POST
def revoke(request, pk):
    with transaction.atomic():
        device = get_object_or_404(Device.objects.select_for_update(), pk=pk, owner=request.user)
        device.revoked_at = timezone.now()
        device.credential_hash = ''
        device.save(update_fields=['revoked_at', 'credential_hash'])
        from .deployment_services import device_revoked
        device_revoked(device)
    messages.success(request, 'Device access revoked. It can no longer authenticate to AMPVE.')
    return redirect('device_detail', pk=pk)


def device_api(view):
    @csrf_exempt
    @never_cache
    @require_POST
    @sensitive_variables()
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        # Device APIs never use a browser session as authentication.
        if int(request.META.get('CONTENT_LENGTH') or 0) > 2048 or len(request.body) > 2048:
            return JsonResponse({'error': 'Request too large.'}, status=413)
        try:
            if request.content_type != 'application/json':
                raise ValueError()
            payload = json.loads(request.body)
            if not isinstance(payload, dict):
                raise ValueError()
            return view(request, payload, *args, **kwargs)
        except (ValueError, TypeError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid request or device permission.'}, status=400)
    return wrapped


def bearer(request):
    value = request.headers.get('Authorization', '')
    if not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', value):
        raise ValueError()
    return value[7:]


@device_api
def enrollment_start(request, data):
    if data != {'protocol': 1, 'hardware_profile': PROFILE}:
        raise ValueError()
    # Global limit is checked first to bound database growth from arbitrary source IPs.
    if not allowed('enrollment-global', 60) or not allowed('enrollment-ip:' + str(client_ip(request)), 5):
        return JsonResponse({'error': 'Pairing is busy. Retry later.'}, status=429)
    row, code, proof = begin_enrollment()
    return JsonResponse({'enrollment_id': str(row.pk), 'code': code, 'bootstrap_proof': proof,
        'expires_in': 600, 'poll_interval': 5}, status=201)


@device_api
def enrollment_exchange(request, data, pk):
    proof = bearer(request)
    if set(data) != {'credential'} or not isinstance(data['credential'], str) or not re.fullmatch('[A-Za-z0-9_-]{43}', data['credential']):
        raise ValueError()
    row = DeviceEnrollment.objects.filter(pk=pk, expires_at__gt=timezone.now()).first()
    if not row or not constant_time_compare(row.proof_hash, digest(proof)):
        raise ValueError()
    if not allowed('exchange:' + str(pk), 150):
        return JsonResponse({'error': 'Retry later.'}, status=429)
    device = exchange(pk, proof, data['credential'])
    if not device:
        return JsonResponse({'status': 'pending'}, status=202)
    return JsonResponse({'status': 'claimed', 'device_id': str(device.pk), 'heartbeat_interval': 30})


@device_api
def heartbeat(request, data, pk):
    token = bearer(request)
    required = {'protocol', 'firmware_version', 'chip_revision', 'transport', 'acknowledged_version'}
    if not required <= set(data) or set(data) - required - {'hardware_report'} or type(data['protocol']) is not int or data['protocol'] != 1:
        raise ValueError()
    for field, length in [('firmware_version', 80), ('chip_revision', 20)]:
        if not isinstance(data[field], str) or not re.fullmatch(r'[A-Za-z0-9._+-]{1,' + str(length) + '}', data[field]):
            raise ValueError()
    if data['transport'] not in ['wifi', 'ethernet'] or type(data['acknowledged_version']) is not int:
        raise ValueError()
    report = validate_report(data['hardware_report']) if 'hardware_report' in data else None
    with transaction.atomic():
        device = Device.objects.select_for_update().select_related('owner').filter(pk=pk).first()
        if not device or device.revoked_at or not device.owner.is_active or not device.credential_hash or not constant_time_compare(device.credential_hash, digest(token)):
            return JsonResponse({'error': 'Device permission denied.'}, status=401)
        ack = data['acknowledged_version']
        if ack < device.acknowledged_version or ack > device.config_version:
            raise ValueError()
        if device.last_seen and (timezone.now() - device.last_seen).total_seconds() < 5:
            return JsonResponse({'error': 'Poll every 30 seconds.'}, status=429)
        device.last_seen = timezone.now()
        if report is not None:
            device.hardware_report = report
            device.hardware_reported_at = device.last_seen
        for field in ['firmware_version', 'chip_revision', 'transport', 'acknowledged_version']:
            setattr(device, field, data[field])
        device.save()
        from .models import CompanionInstallation, DeviceConsoleSession
        console_active = DeviceConsoleSession.objects.filter(device=device, ended_at=None,
            expires_at__gt=timezone.now()).exists()
        companion = CompanionInstallation.objects.select_related('connection').filter(
            device=device, enabled=True, connection__owner=device.owner,
            connection__validation='accepted').first()
        return JsonResponse({'protocol': 1, 'heartbeat_interval': 30,
            'configuration': {'version': device.config_version, 'name': device.name,
                'volume': device.volume, 'microphone_muted': device.microphone_muted,
                'companion': {'enabled': bool(companion),
                    'provider': companion.connection.provider if companion else ''}},
            'audio_available': bool(companion), 'ota_available': hasattr(device,'firmware_state'),
            'console': {'active': console_active, 'poll_interval_ms': 600 if console_active else 30000}})


@never_cache
@login_required
def interface_preview(request):
    return render(request, 'workspace/interface_preview.html', context(title='A little space for possibility.'))
