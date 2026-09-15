"""Software fixtures for signed Core apps and authenticated typed diagnostics."""
import base64
import json
import secrets
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from .app_package_contract import verify
from . import app_services
from .device_services import digest
from .hardware_profiles import CONTRACT, PROFILE
from .models import (User, Device, DeviceAdminCommand, DeviceAppAssignment,
                     DeviceCoreStatus, DeviceDiagnosticEvent)
from .release_contract import canonical, sha256


class CoreCapabilityTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.key=Ed25519PrivateKey.generate()
        self.trust={'schema':1,'minimum_sequence':1,'revoked_releases':[],
            'keys':{'fixture-publisher':{'public_key':self.key.public_key().public_bytes(
                Encoding.Raw,PublicFormat.Raw).hex(),'channels':['development'],
                'purposes':['ota'],'revoked':False}}}
        (self.root/'trust.json').write_bytes(canonical(self.trust))
        override=override_settings(FIRMWARE_PUBLISHER_TRUST=str(self.root/'trust.json'))
        override.enable();self.addCleanup(override.disable)
        self.owner=User.objects.create_user('core-owner@example.test','Fixture-pass-42')
        self.other=User.objects.create_user('core-other@example.test','Fixture-pass-43')
        self.admin=User.objects.create_superuser('core-admin@example.test','Fixture-pass-44')
        self.token=secrets.token_urlsafe(32)
        self.device=Device.objects.create(owner=self.owner,name='Core software fixture',
            hardware_profile=PROFILE['id'],credential_hash=digest(self.token),
            chip_revision='1.3',transport='wifi',firmware_version='0.1.23-core-dev',
            hardware_report={'schema':2,'compatibility':CONTRACT,'flash_bytes':33554432,
                'psram_bytes':33554432})
        self.machine=Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        self.policy=self.make_policy('timer','local_timer',120)
        self.timer=app_services.import_package(self.signed(self.policy))
        self.status_policy=self.make_policy('status','show_status',0)
        self.status=app_services.import_package(self.signed(self.status_policy))
        DeviceCoreStatus.objects.create(device=self.device,core_version='0.1.23-core-dev',
            api_version=1,heap_free_bytes=2000000,stack_min_bytes=2500)

    def make_policy(self,kind,action,duration):
        return {'schema':1,'api_version':1,'key_id':'fixture-publisher',
            'name':kind+'-fixture','version':'1.0.0','kind':kind,
            'profile_id':CONTRACT['profile_id'],'profile_version':1,
            'layout_id':CONTRACT['layout_id'],'chip_revision':103,
            'flash_bytes':33554432,'minimum_psram_bytes':33554432,
            'expires_at':(timezone.now()+timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'ui':{'title':'Fixture '+kind,'body':'Local bounded workflow'},
            'workflow':{'action':action,'duration_s':duration,
                        'start_muted':kind!='companion'}}

    def signed(self,policy):
        payload=canonical(policy)
        return {'payload':base64.b64encode(payload).decode(),
                'signature':base64.b64encode(self.key.sign(payload)).decode()}

    def device_post(self,path,payload,token=None,device=None):
        return self.machine.post('/api/devices/v1/'+str((device or self.device).pk)+'/'+path,
            payload,content_type='application/json',
            HTTP_AUTHORIZATION='Bearer '+(token or self.token))

    def sync(self,active_id='',app_version=''):
        return self.device_post('apps/sync/',{'protocol':1,'api_version':1,
            'core_version':'0.1.23-core-dev','active_id':active_id,'app_version':app_version,
            'heap_free_bytes':1000000,'stack_min_bytes':2200})

    def event(self,sequence=0):
        return {'boot_id':'abcdef0123456789','sequence':sequence,'kind':'boot',
            'operation':'idle','error_code':'','reset_reason':'panic',
            'core_version':'0.1.23-core-dev','app_version':'',
            'heap_free_bytes':1000000,'stack_min_bytes':2200}

    def test_signature_size_schema_and_hardware_rejection(self):
        policy, identity=verify(self.signed(self.policy),self.trust)
        self.assertEqual(identity,self.timer.pk)
        self.assertEqual(policy['workflow']['action'],'local_timer')
        bad={**self.signed(self.policy),'signature':base64.b64encode(b'!'*64).decode()}
        with self.assertRaises(Exception):verify(bad,self.trust)
        truncated={**self.signed(self.policy),'payload':base64.b64encode(canonical(self.policy)[:-1]).decode()}
        with self.assertRaises(Exception):verify(truncated,self.trust)
        incompatible={**self.policy,'minimum_psram_bytes':16777216}
        with self.assertRaises(ValueError):verify(self.signed(incompatible),self.trust)
        arbitrary={**self.policy,'workflow':{'action':'execute_native','duration_s':120,'start_muted':True}}
        with self.assertRaises(ValueError):verify(self.signed(arbitrary),self.trust)
        self.device.hardware_report['psram_bytes']=16777216
        self.device.save(update_fields=['hardware_report'])
        with self.assertRaises(app_services.AppError):
            app_services.request(self.owner,self.device.pk,'assign_app',uuid.uuid4(),self.timer.pk)

    def test_one_device_assignment_download_interrupted_payload_and_rollback(self):
        first=app_services.request(self.owner,self.device.pk,'assign_app',uuid.uuid4(),self.timer.pk)
        self.assertEqual(app_services.request(self.owner,self.device.pk,'assign_app',first.idempotency_key,self.timer.pk).pk,first.pk)
        self.assertEqual(self.sync().json()['desired_id'],self.timer.pk)
        response=self.device_post(f'apps/{self.timer.pk}/package/',{'protocol':1})
        self.assertEqual(response.status_code,200)
        self.assertEqual(verify(response.json(),self.trust)[1],self.timer.pk)
        with self.assertRaises(Exception):verify({'payload':response.json()['payload'][:-8],
            'signature':response.json()['signature']},self.trust)
        second=app_services.request(self.owner,self.device.pk,'assign_app',uuid.uuid4(),self.status.pk)
        assignment=DeviceAppAssignment.objects.get(device=self.device)
        self.assertEqual(assignment.previous_package_id,self.timer.pk)
        self.assertEqual(self.sync(self.timer.pk,'1.0.0').json()['desired_id'],self.status.pk)
        self.assertEqual(self.device_post(f'apps/{self.timer.pk}/package/',{'protocol':1}).status_code,200)
        app_services.request(self.owner,self.device.pk,'rollback_app',uuid.uuid4())
        self.assertEqual(self.sync(self.status.pk,'1.0.0').json()['desired_id'],self.timer.pk)
        self.assertEqual(self.device_post(f'core/commands/{second.pk}/ack/',{'protocol':1,'result':'applied'}).status_code,200)
        self.assertEqual(self.device_post(f'core/commands/{second.pk}/ack/',{'protocol':1,'result':'applied'}).status_code,200)
        self.assertEqual(self.device_post(f'core/commands/{second.pk}/ack/',{'protocol':1,'result':'failed'}).status_code,409)

    def test_kill_switch_revocation_and_expiring_snapshot(self):
        app_services.request(self.owner,self.device.pk,'assign_app',uuid.uuid4(),self.timer.pk)
        app_services.request(self.owner,self.device.pk,'kill_app',uuid.uuid4())
        self.assertTrue(self.sync(self.timer.pk,'1.0.0').json()['disabled'])
        self.assertEqual(self.device_post(f'apps/{self.timer.pk}/package/',{'protocol':1}).status_code,409)
        app_services.request(self.owner,self.device.pk,'assign_app',uuid.uuid4(),self.timer.pk)
        snapshot=app_services.request(self.owner,self.device.pk,'snapshot',uuid.uuid4())
        snapshot.expires_at=timezone.now()-timedelta(seconds=1);snapshot.save(update_fields=['expires_at'])
        self.assertNotEqual(self.sync().json().get('command',{}).get('id') if self.sync().json()['command'] else None,str(snapshot.pk))
        app_services.revoke(self.timer.pk)
        self.assertTrue(self.sync(self.timer.pk,'1.0.0').json()['revoked_active'])
        self.assertEqual(self.sync(self.timer.pk,'1.0.0').json()['desired_id'],'')

    def test_diagnostic_authentication_dedup_retention_and_owner_isolation(self):
        payload={'protocol':1,'events':[self.event()]}
        self.assertEqual(self.device_post('diagnostics/events/',payload).status_code,200)
        self.assertEqual(self.device_post('diagnostics/events/',payload).status_code,200)
        self.assertEqual(DeviceDiagnosticEvent.objects.filter(device=self.device).count(),1)
        changed=self.event();changed['operation']='companion_start'
        self.assertEqual(self.device_post('diagnostics/events/',{'protocol':1,'events':[changed]}).status_code,409)
        raw=self.event(1);raw['uart_text']='password=fixture'
        self.assertEqual(self.device_post('diagnostics/events/',{'protocol':1,'events':[raw]}).status_code,409)
        self.assertEqual(self.device_post('diagnostics/events/',payload,token=secrets.token_urlsafe(32)).status_code,401)
        url=reverse('device_core',args=[self.device.pk])
        self.assertContains(self.client.get(url),'abcdef0123456789')
        self.client.force_login(self.other);self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.admin);self.assertEqual(self.client.get(url).status_code,404)
        for sequence in range(1,135):
            DeviceDiagnosticEvent.objects.create(device=self.device,**self.event(sequence))
        self.assertEqual(self.device_post('diagnostics/events/',{'protocol':1,'events':[self.event(200)]}).status_code,200)
        self.assertLessEqual(DeviceDiagnosticEvent.objects.filter(device=self.device).count(),128)

    def test_owner_command_and_package_routes_are_isolated(self):
        url=reverse('device_core_command',args=[self.device.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{'kind':'kill_app','request_key':str(uuid.uuid4())}).status_code,404)
        self.assertEqual(self.device_post(f'apps/{self.timer.pk}/package/',{'protocol':1}).status_code,409)
        self.assertEqual(self.device_post('apps/sync/',{'protocol':1,'api_version':1,
            'core_version':'0.1.23-core-dev','active_id':'','app_version':'',
            'heap_free_bytes':1,'stack_min_bytes':1},token=secrets.token_urlsafe(32)).status_code,401)
