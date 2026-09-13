"""Signed software fixtures; no hardware writes or upstream provider requests."""
import base64
import json
import secrets
import tempfile
import uuid
import zipfile
from io import BytesIO
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from .models import User, Device, DeviceFirmware, FirmwareRelease, FirmwareDeployment, FirmwareDeploymentEvent
from .hardware_profiles import CONTRACT, PROFILE
from .release_contract import canonical, sha256
from .device_services import digest
from . import deployment_services as service


class DeploymentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_user('update-owner@example.test','Fixture-password-42')
        cls.other=User.objects.create_user('update-other@example.test','Fixture-password-43')
        cls.admin=User.objects.create_superuser('update-admin@example.test','Fixture-password-44')

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.key=Ed25519PrivateKey.generate()
        self.trust={'schema':1,'minimum_sequence':1,'revoked_releases':[],
            'keys':{'fixture-key':{'public_key':self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),
                    'channels':['development'],'purposes':['initial-install','ota'],'revoked':False}}}
        (self.root/'trust.json').write_bytes(canonical(self.trust))
        override=override_settings(FIRMWARE_PUBLISHER_TRUST=str(self.root/'trust.json'))
        override.enable();self.addCleanup(override.disable)
        self.initial=self.release(1,'initial-install')
        self.target=self.release(2,'ota')
        self.token=secrets.token_urlsafe(32)
        self.device=Device.objects.create(owner=self.owner,name='Firmware software fixture',hardware_profile=PROFILE['id'],
            credential_hash=digest(self.token),chip_revision='1.3',firmware_version='fixture-1',transport='wifi',
            hardware_report={'schema':2,'compatibility':CONTRACT,'flash_bytes':33554432,'psram_bytes':33554432,
                'display':{'width':1024,'height':600},'capabilities':dict.fromkeys(['display','touch','speaker','microphone','wifi'],'configured')})
        self.machine=Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.assertEqual(self.api('firmware/identity/',self.running()).status_code,200)

    def release(self,sequence,purpose,notes=None):
        policy=json.loads((settings.REPO_DIR/'tests/fixtures/initial-release-v2.json').read_text())
        content=('firmware-fixture-'+str(sequence)).encode().ljust(131072,b'!')
        archive=b'fixture-only-archive'
        if notes is not None:
            buffer=BytesIO()
            with zipfile.ZipFile(buffer,'w') as bundle:bundle.writestr('release-notes.txt',notes)
            archive=buffer.getvalue()
        policy.update(sequence=sequence,purpose=purpose,installable=purpose=='initial-install',firmware_version='fixture-'+str(sequence),
            expires_at=(timezone.now()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        policy['app'].update(size=len(content),sha256=sha256(content))
        policy['provenance']['archive_sha256']=sha256(archive)
        if purpose=='ota':
            del policy['app']['offset'];policy.update(ota_review='Software fixture only',from_app_sha256=[self.initial.policy['app']['sha256']])
        payload=canonical(policy);envelope={'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(self.key.sign(payload)).decode()}
        root=self.root/str(sequence);root.mkdir()
        (root/'approved-release.json').write_bytes(canonical(envelope));(root/'xiaozhi.bin').write_bytes(content);(root/'review.zip').write_bytes(archive)
        return service.register_release(root)

    def running(self):
        return {'protocol':1,'app_sha256':self.initial.policy['app']['sha256'],'boot_confirmed':True}

    def api(self,path,payload,device=None,token=None):
        return self.machine.post(f'/api/devices/v1/{(device or self.device).pk}/'+path,payload,
            content_type='application/json',HTTP_AUTHORIZATION='Bearer '+(token or self.token))

    def queue(self,key=None,target=None):
        return service.request_update(self.owner,self.device.pk,(target or self.target).pk,key or uuid.uuid4())

    def report(self,job,state,**changes):
        job.refresh_from_db()
        data={'release_id':job.release_id,'sequence':job.report_sequence+1,'state':state,
            'bytes_written':0 if state=='downloading' else self.target.policy['app']['size'],
            'app_sha256':self.target.policy['app']['sha256'] if state=='confirmed' else self.initial.policy['app']['sha256'],
            'boot_confirmed':True,'error_code':'boot_failed' if state=='rolled_back' else '',**changes}
        return self.api(f'updates/{job.pk}/report/',data),data

    def rebooting(self):
        job=self.queue()
        for state in ['downloading','verifying','rebooting']:
            self.assertEqual(self.report(job,state)[0].status_code,200)
        return job

    def test_import_is_idempotent_and_detects_tampering(self):
        self.assertEqual(service.register_release(self.target.directory).pk,self.target.pk)
        self.assertEqual(FirmwareRelease.objects.count(),2)
        (Path(self.target.directory)/'xiaozhi.bin').write_bytes(b'changed')
        with self.assertRaises(service.DeploymentError):self.queue()
        self.assertEqual(FirmwareDeployment.objects.count(),0)

    def test_verified_notes_are_escaped_and_archive_changes_hide_the_release(self):
        release=self.release(3,'ota',notes='Fixture change\n<script>alert(1)</script>')
        url=reverse('device_updates',args=[self.device.pk])
        response=self.client.get(url)
        self.assertContains(response,'Fixture change<br>')
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        (Path(release.directory)/'review.zip').write_bytes(b'tampered notes archive')
        response=self.client.get(url)
        self.assertNotContains(response,'Fixture change')
        self.assertNotContains(response,release.pk)

    def test_update_page_shows_verified_release_details(self):
        response=self.client.get(reverse('device_updates',args=[self.device.pk]))
        self.assertContains(response,'Queue firmware update')
        self.assertContains(response,'128.0\u00a0KB')
        self.assertContains(response,self.target.pk)
        self.assertContains(response,self.target.policy['app']['sha256'])
        self.assertContains(response,'Software fixture only')
        self.assertContains(response,self.target.policy['expires_at'])

    def test_update_page_distinguishes_missing_identity_and_incompatible_reports(self):
        DeviceFirmware.objects.filter(device=self.device).delete()
        url=reverse('device_updates',args=[self.device.pk])
        response=self.client.get(url)
        self.assertContains(response,'version name alone cannot enable updates')
        self.assertNotContains(response,'Queue firmware update')
        self.device.transport='serial';self.device.save(update_fields=['transport'])
        response=self.client.get(url)
        self.assertContains(response,'does not match this update profile')
        self.assertNotContains(response,'Queue firmware update')

    def test_update_page_distinguishes_revocation_and_unavailable_upgrade(self):
        url=reverse('device_updates',args=[self.device.pk])
        self.target.revoked_at=timezone.now();self.target.save(update_fields=['revoked_at'])
        response=self.client.get(url)
        self.assertContains(response,'No newer verified release is eligible')
        self.assertNotContains(response,'Queue firmware update')
        self.device.revoked_at=timezone.now();self.device.save(update_fields=['revoked_at'])
        response=self.client.get(url)
        self.assertContains(response,'This device has been revoked')
        self.assertNotContains(response,'Queue firmware update')
        self.device.revoked_at=None;self.device.credential_hash='';self.device.save(update_fields=['revoked_at','credential_hash'])
        response=self.client.get(url)
        self.assertContains(response,'no active pairing credential')
        self.assertNotContains(response,'Queue firmware update')

    def test_update_history_does_not_turn_pending_or_failed_states_into_success(self):
        # Rendering fixtures only. Device/API state-transition tests below remain authoritative.
        job=self.queue();url=reverse('device_updates',args=[self.device.pk])
        cases={'queued':'Waiting for the device to claim',
               'downloading':'An update is already pending',
               'verifying':'An update is already pending',
               'rebooting':'Waiting for a confirmed startup',
               'confirmed':'expected image and a confirmed startup',
               'rolled_back':'confirmed return to its previous image',
               'failed':'Check the board locally before requesting',
               'cancelled':'cancelled before download'}
        for state,message in cases.items():
            job.state=state;job.error_code='network' if state=='failed' else '';job.save()
            response=self.client.get(url)
            self.assertContains(response,message)
            if state!='confirmed':self.assertNotContains(response,'expected image and a confirmed startup')
            if state in FirmwareDeployment.ACTIVE:self.assertNotContains(response,'Queue firmware update')
            if state=='failed':self.assertContains(response,'The network connection was interrupted.')

    def test_queue_is_idempotent_offline_and_rejects_conflicts(self):
        key=uuid.uuid4();job=self.queue(key)
        self.assertEqual(self.queue(key).pk,job.pk)
        self.assertEqual(job.state,'queued')
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).confirmed_sequence,1)
        with self.assertRaises(service.DeploymentError):self.queue(uuid.uuid4())
        with self.assertRaises(service.DeploymentError):self.queue(key,self.initial)
        self.assertEqual(FirmwareDeployment.objects.count(),1)

    def test_owner_and_admin_isolation_and_csrf(self):
        job=self.queue()
        for user in [self.other,self.admin]:
            client=Client();client.force_login(user)
            for method in ['get','post']:
                self.assertEqual(getattr(client,method)(reverse('device_updates',args=[self.device.pk])).status_code,404)
            self.assertEqual(client.post(reverse('device_update_cancel',args=[self.device.pk,job.pk])).status_code,404)
        client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        self.assertEqual(client.post(reverse('device_updates',args=[self.device.pk]),{}).status_code,403)
        self.assertEqual(client.post(reverse('device_update_cancel',args=[self.device.pk,job.pk]),{}).status_code,403)
        self.assertEqual(client.get(reverse('device_update_cancel',args=[self.device.pk,job.pk])).status_code,405)

    def test_cookie_wrong_credential_and_cross_device_cannot_poll_report_or_download(self):
        job=self.queue()
        other_device=Device.objects.create(owner=self.other,name='Other fixture',hardware_profile=PROFILE['id'],credential_hash=digest(secrets.token_urlsafe(32)))
        for path,body in [('updates/poll/',self.running()),(f'updates/{job.pk}/artifact/',{'release_id':job.release_id})]:
            self.assertEqual(self.api(path,body,token=secrets.token_urlsafe(32)).status_code,401)
            self.assertEqual(self.api(path,body,device=other_device).status_code,401)
            self.assertEqual(self.client.post(f'/api/devices/v1/{self.device.pk}/'+path,body,content_type='application/json').status_code,400)
        other_device.credential_hash=digest(self.token);other_device.save()
        self.assertEqual(self.api(f'updates/{job.pk}/artifact/',{'release_id':job.release_id},device=other_device).status_code,404)

    def test_complete_lifecycle_download_identity_and_replay(self):
        job=self.queue()
        polled=self.api('updates/poll/',self.running()).json()['deployment']
        self.assertEqual(polled['release_id'],job.release_id);self.assertFalse(polled['download_allowed'])
        path=f'updates/{job.pk}/artifact/'
        self.assertEqual(self.api(path,{'release_id':job.release_id}).status_code,409)
        response,report=self.report(job,'downloading');self.assertEqual(response.status_code,200)
        self.assertEqual(self.api(f'updates/{job.pk}/report/',report).status_code,200)
        self.assertEqual(FirmwareDeploymentEvent.objects.filter(deployment=job).count(),2)
        response=self.api(path,{'release_id':job.release_id});self.assertEqual(response.status_code,200)
        self.assertEqual(sha256(b''.join(response.streaming_content)),self.target.policy['app']['sha256'])
        for state in ['verifying','rebooting','confirmed']:
            self.assertEqual(self.report(job,state)[0].status_code,200)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).confirmed_sequence,2)
        self.assertEqual(self.api(f'updates/{job.pk}/report/',report).status_code,409)
        self.assertEqual(self.api(path,{'release_id':job.release_id}).status_code,409)

    def test_boot_confirmation_and_expected_image_are_required(self):
        job=self.queue()
        self.assertEqual(self.report(job,'confirmed')[0].status_code,409)
        for state in ['downloading','verifying','rebooting']:
            self.assertEqual(self.report(job,state)[0].status_code,200)
        self.assertEqual(self.report(job,'confirmed',boot_confirmed=False)[0].status_code,409)
        self.assertEqual(self.report(job,'confirmed',app_sha256='0'*64)[0].status_code,409)
        self.assertEqual(self.report(job,'confirmed',release_id=self.initial.pk)[0].status_code,409)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).confirmed_sequence,1)

    def test_rollback_keeps_previous_confirmed_image(self):
        job=self.rebooting()
        self.assertEqual(self.report(job,'rolled_back')[0].status_code,200)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).release_id,self.initial.pk)
        job.refresh_from_db();self.assertEqual(job.state,'rolled_back')

    def test_rebooted_target_can_resume_reporting_without_being_prematurely_confirmed(self):
        job=self.rebooting()
        response=self.api('updates/poll/',{**self.running(),'app_sha256':self.target.policy['app']['sha256']})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['deployment']['state'],'rebooting')
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).release_id,self.initial.pk)

    def test_cancellation_only_before_download_claim(self):
        job=self.queue();service.cancel_update(self.owner,self.device.pk,job.pk)
        self.assertEqual(self.report(job,'downloading')[0].status_code,409)
        job=self.queue();self.assertEqual(self.report(job,'downloading')[0].status_code,200)
        with self.assertRaises(service.DeploymentError):service.cancel_update(self.owner,self.device.pk,job.pk)

    def test_revocation_stops_download_and_boot_selection_but_preserves_outcome_reports(self):
        job=self.queue();self.assertEqual(self.report(job,'downloading')[0].status_code,200)
        self.trust['revoked_releases']=[self.target.pk];(self.root/'trust.json').write_bytes(canonical(self.trust))
        self.assertEqual(self.api(f'updates/{job.pk}/artifact/',{'release_id':job.release_id}).status_code,409)
        self.assertEqual(self.report(job,'verifying')[0].status_code,200)
        self.assertEqual(self.report(job,'rebooting')[0].status_code,409)
        self.trust['revoked_releases']=[];(self.root/'trust.json').write_bytes(canonical(self.trust))
        self.assertEqual(self.report(job,'rebooting')[0].status_code,200)
        job.refresh_from_db();last_report=job.last_report
        self.trust['revoked_releases']=[self.target.pk];(self.root/'trust.json').write_bytes(canonical(self.trust))
        self.assertEqual(self.api(f'updates/{job.pk}/report/',last_report).status_code,409)
        self.assertEqual(self.report(job,'confirmed')[0].status_code,200)

    def test_device_revocation_blocks_all_future_operations_without_inventing_failure(self):
        job=self.queue();self.assertEqual(self.report(job,'downloading')[0].status_code,200)
        self.client.post(reverse('device_revoke',args=[self.device.pk]))
        self.assertEqual(self.api('updates/poll/',self.running()).status_code,401)
        self.assertEqual(self.report(job,'verifying')[0].status_code,401)
        job.refresh_from_db();self.assertEqual(job.state,'downloading');self.assertTrue(job.needs_attention)
        with self.assertRaises(service.DeploymentError):self.queue()

    def test_stale_and_expired_jobs_do_not_imply_success(self):
        job=self.queue();FirmwareDeployment.objects.filter(pk=job.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        service.reconcile_deployments();job.refresh_from_db();self.assertEqual(job.state,'cancelled')
        job=self.rebooting();FirmwareDeployment.objects.filter(pk=job.pk).update(updated_at=timezone.now()-timedelta(minutes=16))
        service.reconcile_deployments();service.reconcile_deployments()
        job.refresh_from_db();self.assertEqual(job.state,'rebooting');self.assertTrue(job.needs_attention)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).confirmed_sequence,1)

    def test_progress_is_bounded_and_failure_never_advances_firmware(self):
        job=self.queue();self.report(job,'downloading')
        for changes in [{'bytes_written':1},{'bytes_written':2**31},{'sequence':True},{'error_code':'secret log'}, {'extra':'secret'}]:
            self.assertEqual(self.report(job,'downloading',**changes)[0].status_code,409)
        self.assertEqual(self.report(job,'downloading',bytes_written=65536)[0].status_code,200)
        self.assertEqual(self.report(job,'failed',bytes_written=65536,error_code='network')[0].status_code,200)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).confirmed_sequence,1)

    def test_untrusted_identity_and_changed_resources_never_allow_queue(self):
        DeviceFirmware.objects.filter(device=self.device).delete()
        for data in [{**self.running(),'app_sha256':'0'*64},{**self.running(),'boot_confirmed':False}]:
            self.assertIn(self.api('firmware/identity/',data).status_code,[400,409])
        with self.assertRaises(service.DeploymentError):self.queue()
        self.assertEqual(self.api('firmware/identity/',self.running()).status_code,200)
        self.device.hardware_report['psram_bytes']=8388608;self.device.save()
        with self.assertRaises(service.DeploymentError):self.queue()

    def test_rejected_boot_selection_can_fail_without_claiming_rollback(self):
        job=self.rebooting()
        self.assertEqual(self.report(job,'failed',error_code='storage',boot_confirmed=False)[0].status_code,409)
        self.assertEqual(self.report(job,'failed',error_code='network')[0].status_code,409)
        response,payload=self.report(job,'failed',error_code='image_rejected')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.api(f'updates/{job.pk}/report/',payload).status_code,200)
        self.assertEqual(DeviceFirmware.objects.get(device=self.device).release_id,self.initial.pk)

    def test_local_cancellation_and_status_reconciliation(self):
        job=self.queue()
        self.assertEqual(self.report(job,'failed',bytes_written=0,error_code='local_cancelled')[0].status_code,200)
        status=self.api(f'updates/{job.pk}/status/',{'release_id':job.release_id})
        self.assertEqual(status.status_code,200);self.assertEqual(status.json()['state'],'failed')
        self.assertEqual(self.api(f'updates/{job.pk}/status/',{'release_id':self.initial.pk}).status_code,409)
        self.assertEqual(self.api(f'updates/{job.pk}/status/',{'release_id':job.release_id},token=secrets.token_urlsafe(32)).status_code,401)
        job=self.queue();service.cancel_update(self.owner,self.device.pk,job.pk)
        self.assertEqual(self.api(f'updates/{job.pk}/status/',{'release_id':job.release_id}).json()['state'],'cancelled')
