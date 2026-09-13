"""Owner-authorized firmware lifecycle. Every mutation serializes on the device row."""
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .hardware_profiles import PROFILE, matches_contract
from .models import Device, DeviceFirmware, FirmwareRelease, FirmwareDeployment, FirmwareDeploymentEvent
from .release_contract import canonical, digest, eligible_upgrade, read_release, sha256


class DeploymentError(ValueError):
    pass


def verified_release(release, purpose=None):
    if release.revoked_at:
        raise DeploymentError('This release has been withdrawn.')
    try:
        policy, identity, public_key, envelope, floor = read_release(Path(release.directory),Path(settings.FIRMWARE_PUBLISHER_TRUST))
        if identity != release.pk or canonical(policy) != canonical(release.policy) or policy['sequence'] != release.sequence or sha256(canonical(policy['compatibility'])) != release.scope or policy['channel'] != release.channel:
            raise ValueError()
        if purpose is not None and policy['purpose'] != purpose:
            raise ValueError()
    except Exception as error:
        raise DeploymentError('The signed release, trust or artifact is no longer available.') from error
    return policy, envelope, public_key, floor


def register_release(directory):
    directory = Path(directory).resolve()
    if any((path/'.git').exists() for path in [directory,*directory.parents]):
        raise DeploymentError('Keep published firmware outside Git.')
    policy, identity, _, _, _ = read_release(directory,Path(settings.FIRMWARE_PUBLISHER_TRUST))
    with transaction.atomic():
        release, created = FirmwareRelease.objects.get_or_create(pk=identity,defaults={
            'scope':sha256(canonical(policy['compatibility'])),'channel':policy['channel'],
            'sequence':policy['sequence'],'policy':policy,'directory':str(directory)})
        if not created and (release.policy != policy or release.directory != str(directory)):
            raise DeploymentError('An imported release is immutable; do not replace its path or metadata.')
    return release


def compatible(device):
    report = device.hardware_report
    return (device.hardware_profile == PROFILE['id'] and matches_contract(report.get('compatibility'))
            and device.chip_revision == '1.3' and device.transport == 'wifi'
            and report.get('flash_bytes') == PROFILE['resources']['flash_bytes']
            and type(report.get('psram_bytes')) is int
            and report['psram_bytes'] >= PROFILE['resources']['minimum_psram_bytes'])


def confirm_initial(device, app_hash):
    """Called under the authenticated device lock after a confirmed-boot report."""
    existing = DeviceFirmware.objects.filter(device=device).first()
    if existing:
        if existing.app_sha256 != app_hash:
            raise DeploymentError('Report a changed image through its authorized deployment.')
        return existing
    if not compatible(device):
        raise DeploymentError('Report the matching hardware profile and resources before confirming firmware.')
    for release in FirmwareRelease.objects.filter(revoked_at=None,policy__purpose='initial-install',policy__app__sha256=app_hash).order_by('-sequence')[:10]:
        try:
            policy, _, _, _ = verified_release(release,'initial-install')
        except DeploymentError:
            continue
        if device.firmware_version != policy['firmware_version']:
            continue
        return DeviceFirmware.objects.create(device=device,release=release,app_sha256=app_hash,
            confirmed_sequence=release.sequence,confirmed_at=timezone.now())
    raise DeploymentError('No trusted initial-install release matches this confirmed image.')


def eligible_releases(device):
    current = DeviceFirmware.objects.filter(device=device).first()
    if not current or device.revoked_at or not device.credential_hash or not compatible(device):
        return []
    results = []
    for release in FirmwareRelease.objects.filter(revoked_at=None,policy__purpose='ota',sequence__gt=current.confirmed_sequence).order_by('-sequence')[:20]:
        try:
            policy, _, _, _ = verified_release(release,'ota')
        except DeploymentError:
            continue
        if eligible_upgrade(policy,current.confirmed_sequence,current.app_sha256):
            results.append(release)
    return results


def expire_queued(job):
    if job.state != 'queued':
        return
    invalid = job.expires_at <= timezone.now() or job.device.revoked_at or not job.device.owner.is_active
    if not invalid:
        try:
            verified_release(job.release,'ota')
        except DeploymentError:
            invalid = True
    if invalid:
        job.state='cancelled';job.error_code='approval_unavailable';job.save()
        FirmwareDeploymentEvent.objects.create(deployment=job,sequence=job.report_sequence+1,
            report={'state':'cancelled','error_code':job.error_code,'source':'server'})


def request_update(owner, device_id, release_id, idempotency_key):
    with transaction.atomic():
        device = Device.objects.select_for_update().select_related('owner').get(pk=device_id,owner=owner)
        if device.revoked_at or not device.owner.is_active or not device.credential_hash:
            raise DeploymentError('This device cannot authorize firmware updates.')
        previous = FirmwareDeployment.objects.filter(device=device,idempotency_key=idempotency_key).first()
        if previous:
            if previous.release_id != release_id:
                raise DeploymentError('This request key already identifies another release.')
            expire_queued(previous)
            return previous
        active = FirmwareDeployment.objects.filter(device=device,state__in=FirmwareDeployment.ACTIVE).select_related('device__owner','release').first()
        if active:
            expire_queued(active)
            if active.state in FirmwareDeployment.ACTIVE:
                raise DeploymentError('An update is already pending for this device.')
        current = DeviceFirmware.objects.filter(device=device).first()
        if not current or not compatible(device):
            raise DeploymentError('A matching confirmed firmware image and hardware report are required.')
        release = FirmwareRelease.objects.select_for_update().get(pk=release_id)
        policy, _, _, _ = verified_release(release,'ota')
        if not eligible_upgrade(policy,current.confirmed_sequence,current.app_sha256):
            raise DeploymentError('This release is not an eligible upgrade from the confirmed image.')
        job = FirmwareDeployment.objects.create(device=device,release=release,previous_release=current.release,
            previous_app_sha256=current.app_sha256,idempotency_key=idempotency_key,
            expires_at=min(datetime.fromisoformat(policy['expires_at'].replace('Z','+00:00')),timezone.now()+timedelta(days=7)))
        FirmwareDeploymentEvent.objects.create(deployment=job,sequence=0,report={'state':'queued','source':'owner'})
        return job


def cancel_update(owner, device_id, job_id):
    with transaction.atomic():
        device=Device.objects.select_for_update().get(pk=device_id,owner=owner)
        job=FirmwareDeployment.objects.get(pk=job_id,device=device)
        if job.state == 'cancelled':
            return job
        if job.state != 'queued':
            raise DeploymentError('The device has started this update. Keep it powered and wait for its report.')
        job.state='cancelled';job.error_code='owner_cancelled';job.save()
        FirmwareDeploymentEvent.objects.create(deployment=job,sequence=1,report={'state':'cancelled','source':'owner'})
        return job


def job_data(job):
    return {'deployment_id':str(job.pk),'release_id':job.release_id,'state':job.state,
            'sequence':job.report_sequence,'bytes_written':job.bytes_written,
            'needs_attention':job.needs_attention,'error_code':job.error_code}


def poll_update(device, app_hash):
    current=DeviceFirmware.objects.filter(device=device).first()
    job=FirmwareDeployment.objects.filter(device=device,state__in=FirmwareDeployment.ACTIVE).select_related('device__owner','release').first()
    resumed_target=job and job.state=='rebooting' and app_hash==job.release.policy['app']['sha256']
    if not current or current.app_sha256 != app_hash and not resumed_target:
        raise DeploymentError('Confirm the running image before polling for an update.')
    if not job:
        return {'deployment':None}
    expire_queued(job)
    result={**job_data(job),'download_allowed':False,'previous_app_sha256':job.previous_app_sha256}
    if job.state in FirmwareDeployment.ACTIVE:
        try:
            policy,envelope,_,_=verified_release(job.release,'ota')
            if not compatible(device) or job.expires_at<=timezone.now():
                raise DeploymentError('Hardware report no longer matches.')
            result.update(envelope=envelope,download_allowed=job.state=='downloading',
                app_url=f'/api/devices/v1/{device.pk}/updates/{job.pk}/artifact/',
                previous_app_sha256=job.previous_app_sha256)
        except DeploymentError:
            result['download_allowed']=False
    return {'deployment':result}


ERRORS={'','network','hash_mismatch','image_rejected','storage','approval_unavailable','boot_failed','local_cancelled'}
TRANSITIONS={'queued':{'downloading','failed'},'downloading':{'downloading','verifying','failed'},
             'verifying':{'rebooting','failed'},'rebooting':{'confirmed','rolled_back','failed'}}


def report_update(device, job_id, report):
    expected={'release_id','sequence','state','bytes_written','app_sha256','boot_confirmed','error_code'}
    if set(report)!=expected or type(report['sequence']) is not int or not 1<=report['sequence']<=128 or type(report['bytes_written']) is not int or type(report['boot_confirmed']) is not bool or not digest(report['app_sha256']) or report['error_code'] not in ERRORS:
        raise DeploymentError('Invalid bounded deployment report.')
    job=FirmwareDeployment.objects.select_related('release').get(pk=job_id,device=device)
    if report['release_id'] != job.release_id:
        raise DeploymentError('The report identifies another release.')
    if report['sequence']==job.report_sequence and report==job.last_report:
        if report['state'] in ('downloading','rebooting'):
            verified_release(job.release,'ota')
            if job.expires_at<=timezone.now() or not compatible(device):
                raise DeploymentError('The repeated authorization is no longer valid.')
        return job
    state=report['state'];written=report['bytes_written'];size=job.release.policy['app']['size']
    if report['sequence']!=job.report_sequence+1 or state not in TRANSITIONS.get(job.state,set()) or not job.bytes_written<=written<=size:
        raise DeploymentError('Stale report or invalid deployment transition.')
    if job.state=='queued' and state=='failed' and written!=0:
        raise DeploymentError('An unclaimed deployment cannot report written bytes.')
    if state=='downloading' and (job.state=='queued' and written!=0 or job.state=='downloading' and (written<=job.bytes_written or written!=size and written-job.bytes_written<65536)):
        raise DeploymentError('Report download progress in bounded 64 KiB increments.')
    if state in ('verifying','rebooting','confirmed','rolled_back') and written!=size:
        raise DeploymentError('The complete app must be downloaded before this transition.')
    expected_app=job.release.policy['app']['sha256'] if state=='confirmed' else job.previous_app_sha256
    if report['app_sha256']!=expected_app or state in ('confirmed','rolled_back') and report['boot_confirmed'] is not True:
        raise DeploymentError('The running image or boot confirmation does not match.')
    if (state in ('failed','rolled_back')) != bool(report['error_code']):
        raise DeploymentError('Use a bounded failure reason only for a failure outcome.')
    if job.state=='rebooting' and state=='failed' and (report['boot_confirmed'] is not True or report['error_code'] not in ('storage','image_rejected','approval_unavailable','local_cancelled')):
        raise DeploymentError('Boot-selection failure requires a confirmed predecessor and bounded reason.')
    if state in ('downloading','rebooting'):
        # Reauthorize both download start and the final boot-selection boundary.
        verified_release(job.release,'ota')
        if job.expires_at<=timezone.now() or not compatible(device):
            raise DeploymentError('Update approval or hardware compatibility is no longer valid.')
    job.state=state;job.report_sequence=report['sequence'];job.bytes_written=written
    job.last_report=report;job.error_code=report['error_code'];job.needs_attention=False;job.save()
    FirmwareDeploymentEvent.objects.create(deployment=job,sequence=report['sequence'],report=report)
    if state=='confirmed':
        current=DeviceFirmware.objects.get(device=device)
        if job.release.sequence<=current.confirmed_sequence:
            raise DeploymentError('Confirmed firmware sequence cannot decrease.')
        current.release=job.release;current.app_sha256=expected_app
        current.confirmed_sequence=job.release.sequence;current.confirmed_at=timezone.now();current.save()
    return job


def device_revoked(device):
    job=FirmwareDeployment.objects.select_related('release','device__owner').filter(device=device,state__in=FirmwareDeployment.ACTIVE).first()
    if job:
        expire_queued(job)
        if job.state in FirmwareDeployment.ACTIVE:
            job.needs_attention=True;job.save(update_fields=['needs_attention'])


def reconcile_deployments():
    """Never infer device success/failure from a timeout or VPS restart."""
    count=0
    device_ids=list(FirmwareDeployment.objects.filter(state__in=FirmwareDeployment.ACTIVE).order_by(F('checked_at').asc(nulls_first=True),'created_at').values_list('device_id',flat=True)[:200])
    for device_id in device_ids:
        with transaction.atomic():
            device=Device.objects.select_for_update().select_related('owner').filter(pk=device_id).first()
            if not device:
                continue
            job=FirmwareDeployment.objects.select_related('device__owner','release').filter(device=device,state__in=FirmwareDeployment.ACTIVE).first()
            if not job:
                continue
            expire_queued(job)
            if job.state!='queued' and job.state in FirmwareDeployment.ACTIVE and (device.revoked_at or not device.owner.is_active or job.expires_at<=timezone.now() or job.updated_at<timezone.now()-timedelta(minutes=15)):
                job.needs_attention=True;job.save(update_fields=['needs_attention'])
            job.checked_at=timezone.now();job.save(update_fields=['checked_at'])
            count+=1
    return count
