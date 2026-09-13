import uuid
from functools import wraps
from io import BytesIO
from pathlib import Path
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import constant_time_compare
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from . import deployment_services as service
from .device_services import digest as credential_digest, allowed
from .device_views import bearer, device_api, context
from .models import Device, DeviceFirmware, FirmwareRelease, FirmwareDeployment
from .release_contract import digest, read_bounded, sha256


def firmware_api(view):
    @device_api
    @wraps(view)
    def wrapped(request, data, pk, **kwargs):
        token=bearer(request)
        try:
            with transaction.atomic():
                device=Device.objects.select_for_update().select_related('owner').filter(pk=pk).first()
                if not device or device.revoked_at or not device.owner.is_active or not device.credential_hash or not constant_time_compare(device.credential_hash,credential_digest(token)):
                    return JsonResponse({'error':'Device permission denied.'},status=401)
                if not allowed('firmware-api:'+str(pk),180):
                    return JsonResponse({'error':'Retry later.'},status=429)
                response=view(request,data,device,**kwargs)
                if response.status_code<400:
                    from django.utils import timezone
                    device.last_seen=timezone.now();device.save(update_fields=['last_seen'])
                return response
        except service.DeploymentError as error:
            return JsonResponse({'error':str(error)},status=409)
        except (FirmwareDeployment.DoesNotExist,FirmwareRelease.DoesNotExist):
            return JsonResponse({'error':'Deployment not found.'},status=404)
    return wrapped


def running_image(data):
    if set(data)!={'protocol','app_sha256','boot_confirmed'} or type(data['protocol']) is not int or data['protocol']!=1 or data['boot_confirmed'] is not True or not digest(data['app_sha256']):
        raise ValueError()
    return data['app_sha256']


@firmware_api
def identity(request,data,device):
    current=service.confirm_initial(device,running_image(data))
    return JsonResponse({'release_id':current.release_id,'confirmed_sequence':current.confirmed_sequence,
                         'app_sha256':current.app_sha256})


@firmware_api
def poll(request,data,device):
    return JsonResponse(service.poll_update(device,running_image(data)))


@firmware_api
def report(request,data,device,job_id):
    return JsonResponse(service.job_data(service.report_update(device,job_id,data)))


@firmware_api
def artifact(request,data,device,job_id):
    if set(data)!={'release_id'} or not digest(data['release_id']):
        raise ValueError()
    job=FirmwareDeployment.objects.select_related('release').get(pk=job_id,device=device)
    if job.release_id!=data['release_id'] or job.state!='downloading':
        raise service.DeploymentError('Claim this deployment before downloading its app.')
    policy,_,_,_=service.verified_release(job.release,'ota')
    from django.utils import timezone
    if job.expires_at<=timezone.now() or not service.compatible(device):
        raise service.DeploymentError('Update approval or hardware compatibility is no longer valid.')
    app=read_bounded(Path(job.release.directory)/'xiaozhi.bin',policy['app']['size'])
    if sha256(app)!=policy['app']['sha256']:
        raise service.DeploymentError('The approved artifact changed.')
    response=FileResponse(BytesIO(app),content_type='application/octet-stream',as_attachment=True,filename='ampve-'+job.release_id[:12]+'.bin')
    response['X-Content-Type-Options']='nosniff'
    response['X-AMPVE-Release-ID']=job.release_id
    return response


@never_cache
@login_required
def updates(request,pk):
    device=get_object_or_404(Device,pk=pk,owner=request.user)
    if request.method=='POST':
        if not allowed('firmware-owner:'+str(request.user.pk),30,86400):
            messages.error(request,'Too many update requests. Retry later.')
        else:
            try:
                key=uuid.UUID(request.POST.get('request_key',''))
                release_id=request.POST.get('release_id','')
                if not digest(release_id):raise ValueError()
                job=service.request_update(request.user,pk,release_id,key)
            except (ValueError,FirmwareRelease.DoesNotExist):
                messages.error(request,'This update cannot be queued. Refresh and check the device and release status.')
            else:
                messages.success(request,'Update request recorded. Completion requires a confirmed report from the device.')
            return redirect('device_updates',pk=pk)
    return render(request,'workspace/device_updates.html',context(title='Firmware updates',device=device,
        releases=service.eligible_releases(device),request_key=uuid.uuid4(),
        pending=device.firmware_deployments.filter(state__in=FirmwareDeployment.ACTIVE).exists(),
        confirmed=DeviceFirmware.objects.filter(device=device).first(),
        deployments=device.firmware_deployments.select_related('release').all()[:20]))


@never_cache
@login_required
@require_POST
def cancel(request,pk,job_id):
    get_object_or_404(Device,pk=pk,owner=request.user)
    try:
        service.cancel_update(request.user,pk,job_id)
    except FirmwareDeployment.DoesNotExist:
        raise Http404() from None
    except service.DeploymentError as error:
        messages.error(request,str(error))
    else:
        messages.success(request,'The queued update was cancelled before device download.')
    return redirect('device_updates',pk=pk)
