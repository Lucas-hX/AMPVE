"""Companion assignment and short-lived device audio authorization."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .audio_auth import DeviceGrantThrottled, issue_device_grant
from .device_services import PROFILE, digest
from .device_views import bearer, context, device_api
from .models import CompanionInstallation, Device, ProviderConnection


@never_cache
@login_required
def companion(request, pk):
    device = get_object_or_404(Device, pk=pk, owner=request.user)
    installation = CompanionInstallation.objects.select_related('connection').filter(device=device).first()
    if request.method == 'POST':
        action = request.POST.get('action')
        with transaction.atomic():
            device = get_object_or_404(Device.objects.select_for_update(), pk=pk, owner=request.user)
            if device.revoked_at:
                messages.error(request, 'This device is revoked and cannot run Companion.')
            elif action == 'deactivate':
                current = CompanionInstallation.objects.select_for_update().filter(device=device).first()
                if current:
                    current.delete()
                    device.config_version += 1
                    device.save(update_fields=['config_version'])
                messages.success(request, 'Companion has been turned off. An active session will stop shortly.')
            elif action == 'activate':
                connection = ProviderConnection.objects.filter(pk=request.POST.get('connection'),
                    owner=request.user, validation='accepted').first()
                if not connection:
                    messages.error(request, 'Choose a tested AI connection before activating Companion.')
                else:
                    current, created = CompanionInstallation.objects.select_for_update().get_or_create(
                        device=device, defaults={'connection': connection, 'enabled': True})
                    changed = created or current.connection_id != connection.pk or not current.enabled
                    if changed:
                        current.connection = connection
                        current.enabled = True
                        current.save(update_fields=['connection', 'enabled', 'updated_at'])
                        device.config_version += 1
                        device.save(update_fields=['config_version'])
                    messages.success(request, 'Companion is ready. Start the conversation from the device screen.')
            else:
                messages.error(request, 'Choose a valid Companion action.')
        return redirect('device_companion', pk=device.pk)
    connections = ProviderConnection.objects.filter(owner=request.user).defer('encrypted_key')
    return render(request, 'workspace/companion.html', context(title='Meet Companion.', device=device,
        installation=installation,
        installation_ready=bool(installation and installation.enabled and installation.connection.validation == 'accepted'),
        connections=connections))


@device_api
def device_ticket(request, data, pk):
    if data != {'protocol': 1}:
        raise ValueError()
    token = bearer(request)
    device = Device.objects.select_related('owner').filter(pk=pk).first()
    if (not device or device.hardware_profile != PROFILE or device.revoked_at or
            not device.owner.is_active or not device.credential_hash or
            not constant_time_compare(device.credential_hash, digest(token))):
        return JsonResponse({'error': 'Device permission denied.'}, status=401)
    try:
        ticket = issue_device_grant(device.pk)
    except DeviceGrantThrottled as exc:
        return JsonResponse({'error': str(exc)}, status=429)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    return JsonResponse({'protocol': 1, 'ticket': ticket, 'path': '/audio/device/ws',
        'expires_in': 30, 'sample_rate': 24000, 'channels': 1,
        'frame_samples': 480, 'max_seconds': 300})
