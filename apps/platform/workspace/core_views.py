"""Owner-scoped Core administration and authenticated outbound device reports."""
import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST
from . import app_services, diagnostic_services
from .deployment_views import firmware_api
from .device_views import context
from .models import (AppPackage, Device, DeviceAdminCommand, DeviceAppAssignment,
                     DeviceCoreStatus, DeviceDiagnosticEvent)


@never_cache
@login_required
@require_GET
def core(request, pk):
    device = get_object_or_404(Device, pk=pk, owner=request.user)
    status = DeviceCoreStatus.objects.filter(device=device).first()
    assignment = DeviceAppAssignment.objects.select_related('package','previous_package').filter(device=device).first()
    packages = []
    if status and status.api_version == 1 and status.core_version.startswith('0.1.23'):
        for package in AppPackage.objects.filter(revoked_at=None).order_by('policy__name')[:20]:
            try:
                policy = app_services.verified(package)
            except app_services.AppError:
                continue
            if app_services.hardware_compatible(device, policy):
                packages.append(package)
    events = DeviceDiagnosticEvent.objects.filter(device=device).order_by('-created_at')[:40]
    commands = DeviceAdminCommand.objects.filter(device=device,owner=request.user)[:20]
    return render(request,'workspace/device_core.html',context(title='AMPVE Core',device=device,
        status=status,assignment=assignment,packages=packages,events=events,
        commands=commands,assign_key=uuid.uuid4(),kill_key=uuid.uuid4(),
        rollback_key=uuid.uuid4(),snapshot_key=uuid.uuid4()))


@never_cache
@login_required
@require_POST
def command(request,pk):
    get_object_or_404(Device,pk=pk,owner=request.user)
    try:
        key=uuid.UUID(request.POST.get('request_key',''))
        kind=request.POST.get('kind','')
        package_id=request.POST.get('package_id') or None
        job=app_services.request(request.user,pk,kind,key,package_id)
    except (ValueError,TypeError,AppPackage.DoesNotExist) as error:
        messages.error(request,str(error)[:160] or 'Core administration request was rejected.')
    else:
        messages.success(request,'Core command '+str(job.pk)+' queued for this device.')
    return redirect('device_core',pk=pk)


@never_cache
@login_required
@require_POST
def revoke_package(request,package_id):
    if not request.user.is_staff:
        raise Http404()
    if len(package_id)!=64 or any(c not in '0123456789abcdef' for c in package_id):
        raise Http404()
    try:
        app_services.revoke(package_id)
    except AppPackage.DoesNotExist:
        raise Http404() from None
    messages.success(request,'Package revoked. Assigned devices will disable it on their next authenticated check.')
    return redirect('apps')


@firmware_api
def diagnostic_upload(request,data,device):
    try:
        result=diagnostic_services.upload(device,data)
    except diagnostic_services.DiagnosticError as error:
        return JsonResponse({'error':str(error)},status=409)
    return JsonResponse(result)


@firmware_api
def app_sync(request,data,device):
    try:
        return JsonResponse(app_services.sync(device,data))
    except app_services.AppError as error:
        return JsonResponse({'error':str(error)},status=409)


@firmware_api
def app_package(request,data,device,package_id):
    if data != {'protocol':1} or len(package_id)!=64 or any(c not in '0123456789abcdef' for c in package_id):
        return JsonResponse({'error':'Invalid package request.'},status=400)
    try:
        envelope=app_services.package_for_device(device,package_id)
    except (app_services.AppError,AppPackage.DoesNotExist) as error:
        return JsonResponse({'error':str(error)},status=409)
    return JsonResponse(envelope)


@firmware_api
def command_ack(request,data,device,command_id):
    if set(data)!={'protocol','result'} or data['protocol']!=1:
        return JsonResponse({'error':'Invalid command report.'},status=400)
    try:
        job=app_services.acknowledge(device,command_id,data['result'])
    except (app_services.AppError,DeviceAdminCommand.DoesNotExist) as error:
        return JsonResponse({'error':str(error)},status=409)
    return JsonResponse({'id':str(job.pk),'state':job.state,'result':job.result_code})
