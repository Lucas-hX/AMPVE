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


UPDATE_ERRORS={
    'network':'The network connection was interrupted.',
    'hash_mismatch':'The image did not match the approved release hash.',
    'image_rejected':'The device rejected the application image.',
    'storage':'The device could not confirm an update storage operation.',
    'approval_unavailable':'Release approval is no longer available.',
    'boot_failed':'Startup or boot selection was not confirmed.',
    'local_cancelled':'The update was cancelled using the board control.',
    'local_recovery':'A later signed image was confirmed after local recovery; this update is superseded.',
}


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
def status(request,data,device,job_id):
    if set(data)!={'release_id'} or not digest(data['release_id']):
        raise ValueError()
    job=FirmwareDeployment.objects.select_related('release','device__owner').get(pk=job_id,device=device)
    if job.release_id!=data['release_id']:
        raise service.DeploymentError('The request identifies another release.')
    service.expire_queued(job)
    return JsonResponse(service.job_data(job))


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
    confirmed=DeviceFirmware.objects.filter(device=device).select_related('release').first()
    pending=device.firmware_deployments.filter(state__in=FirmwareDeployment.ACTIVE).exists()
    releases=service.eligible_releases(device)
    if device.revoked_at:
        availability='This device has been revoked. Use the reviewed local pairing and recovery process to reconnect it.'
    elif not device.credential_hash:
        availability='This device has no active pairing credential. Complete local pairing before requesting updates.'
    elif not service.compatible(device):
        availability='The reported hardware or Wi-Fi connection does not match this update profile. Check the device compatibility details before proceeding.'
    elif not confirmed:
        availability='Wait for the board to identify a trusted AMPVE image and confirm startup. A reported version name alone cannot enable updates.'
    elif pending:
        availability='An update is already pending. Follow its progress below before requesting another.'
    elif not releases:
        availability='No newer verified release is eligible for this confirmed image. Releases can expire, be withdrawn or require a different starting version.'
    else:
        availability='Choose a verified release and review its size and recovery requirements before queuing the update.'
    deployments=list(device.firmware_deployments.select_related('release').all()[:20])
    for job in deployments:
        job.failure_message=UPDATE_ERRORS.get(job.error_code,'The device reported an update error. Inspect it locally.') if job.error_code else ''
    return render(request,'workspace/device_updates.html',context(title='Firmware updates',device=device,
        releases=releases,request_key=uuid.uuid4(),availability=availability,
        pending=pending,confirmed=confirmed,
        deployments=deployments))


@never_cache
@login_required
def recovery_artifact(request,pk,job_id):
    """Return the signed previous app only for an owner-visible failed OTA."""
    job=get_object_or_404(FirmwareDeployment.objects.select_related('device','previous_release'),
        pk=job_id,device_id=pk,device__owner=request.user,needs_attention=True)
    try:
        policy,_,_,_=service.verified_release(job.previous_release)
        if policy['app']['sha256']!=job.previous_app_sha256:
            raise service.DeploymentError('The recovery image does not match the recorded previous application.')
        app=read_bounded(Path(job.previous_release.directory)/'xiaozhi.bin',policy['app']['size'])
        if len(app)!=policy['app']['size'] or sha256(app)!=job.previous_app_sha256:
            raise service.DeploymentError('The signed recovery artifact changed.')
    except service.DeploymentError:
        raise Http404() from None
    response=FileResponse(BytesIO(app),content_type='application/octet-stream',as_attachment=True,
        filename='ampve-recovery-'+policy['firmware_version']+'.bin')
    response['X-Content-Type-Options']='nosniff'
    response['X-AMPVE-App-SHA256']=job.previous_app_sha256
    return response


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
