"""Software fixtures only; no physical hardware or external provider calls."""
import secrets
from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from .models import User, Device, DeviceEnrollment, DeviceRateBucket
from .device_services import PROFILE, begin_enrollment, claim, digest


class DeviceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user('device-owner@example.com','Fixture-password-42')
        cls.other = User.objects.create_user('device-other@example.com','Fixture-password-43')
        cls.admin = User.objects.create_superuser('device-admin@example.com','Fixture-password-44')

    def setUp(self):
        self.client.force_login(self.owner)
        self.machine = Client(enforce_csrf_checks=True)
        self.credential = secrets.token_urlsafe(32)

    def start(self):
        response = self.machine.post('/api/devices/v1/enroll/',
            {'protocol':1,'hardware_profile':PROFILE}, content_type='application/json')
        self.assertEqual(response.status_code,201)
        self.ticket = response.json()
        return self.ticket

    def claim(self):
        ticket=self.start()
        response=self.client.post(reverse('onboarding'), {'code':ticket['code'],
            'name':'Software fixture P4','confirm':'on','owner':self.other.pk})
        self.assertEqual(response.status_code,302)
        self.device=Device.objects.get()
        return self.device

    def exchange(self, credential=None, proof=None):
        return self.machine.post('/api/devices/v1/enroll/'+self.ticket['enrollment_id']+'/exchange/',
            {'credential':credential or self.credential}, content_type='application/json',
            HTTP_AUTHORIZATION='Bearer '+(proof or self.ticket['bootstrap_proof']))

    def beat(self, **changes):
        payload={'protocol':1,'firmware_version':'fixture-0.1','chip_revision':'1.3',
            'transport':'wifi','acknowledged_version':0,**changes}
        return self.machine.post(f'/api/devices/v1/{self.device.pk}/heartbeat/',payload,
            content_type='application/json',HTTP_AUTHORIZATION='Bearer '+self.credential)

    def test_complete_pairing_and_acknowledgement(self):
        device=self.claim()
        self.assertEqual(device.owner,self.owner)
        self.assertEqual(device.connection_state,'Awaiting device')
        self.assertEqual(self.exchange().status_code,200)
        device.refresh_from_db()
        self.assertEqual(device.credential_hash,digest(self.credential))
        self.assertNotEqual(device.credential_hash,self.credential)
        first=self.beat();self.assertEqual(first.status_code,200)
        self.assertNotIn('credential',first.content.decode())
        self.assertFalse(first.json()['audio_available'])
        self.client.post(reverse('device_detail',args=[device.pk]),{'name':'Desk','volume':50,'microphone_muted':'on'})
        device.refresh_from_db();self.assertEqual(device.config_version,2)
        self.assertEqual(device.acknowledged_version,0)
        Device.objects.update(last_seen=timezone.now()-timedelta(seconds=31))
        self.assertEqual(self.beat(acknowledged_version=2).status_code,200)
        device.refresh_from_db();self.assertEqual(device.acknowledged_version,2)
        self.assertEqual(device.connection_state,'Online')

    def test_codes_and_proofs_hashed_and_single_claim(self):
        self.claim();row=DeviceEnrollment.objects.get()
        self.assertEqual(row.code_hash,digest(self.ticket['code']))
        self.assertEqual(row.proof_hash,digest(self.ticket['bootstrap_proof']))
        with self.assertRaises(ValueError):claim(self.other,self.ticket['code'],'Stolen')
        self.assertEqual(Device.objects.count(),1)

    def test_pending_wrong_proof_retry_and_changed_credential(self):
        self.start();self.assertEqual(self.exchange().status_code,202)
        self.assertEqual(self.exchange(proof=secrets.token_urlsafe(32)).status_code,400)
        claim(self.owner,self.ticket['code'],'Fixture')
        self.assertEqual(self.exchange().status_code,200)
        self.assertEqual(self.exchange().status_code,200)
        self.assertEqual(self.exchange(credential=secrets.token_urlsafe(32)).status_code,400)

    def test_expiry_blocks_claim_and_exchange(self):
        self.start();DeviceEnrollment.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValueError):claim(self.owner,self.ticket['code'],'Late')
        self.assertEqual(self.exchange().status_code,400)

    def test_normal_and_admin_owner_isolation(self):
        device=self.claim()
        for user in [self.other,self.admin]:
            client=Client();client.force_login(user)
            self.assertNotContains(client.get(reverse('devices')),'Software fixture P4')
            for route in ['device_detail','device_revoke']:
                self.assertEqual(client.post(reverse(route,args=[device.pk]),{'name':'Stolen','volume':70}).status_code,404)
            self.assertEqual(client.get(reverse('device_detail',args=[device.pk])).status_code,404)

    def test_browser_csrf_and_revoke_post_only(self):
        device=self.claim();client=Client(enforce_csrf_checks=True);client.force_login(self.owner)
        for route,args in [('onboarding',[]),('device_detail',[device.pk]),('device_revoke',[device.pk])]:
            self.assertEqual(client.post(reverse(route,args=args),{}).status_code,403)
        self.assertEqual(client.get(reverse('device_revoke',args=[device.pk])).status_code,405)

    def test_revocation_blocks_heartbeat_and_reissue(self):
        device=self.claim();self.exchange();self.beat()
        self.client.post(reverse('device_revoke',args=[device.pk]))
        self.assertEqual(self.beat().status_code,401)
        self.assertEqual(self.exchange().status_code,400)
        device.refresh_from_db();self.assertEqual(device.connection_state,'Revoked')
        self.client.post(reverse('device_detail',args=[device.pk]),{'name':'Changed','volume':70})
        device.refresh_from_db();self.assertEqual(device.name,'Software fixture P4')

    def test_browser_cookie_is_not_device_credential(self):
        device=self.claim();self.exchange()
        response=self.client.post(f'/api/devices/v1/{device.pk}/heartbeat/',{},content_type='application/json')
        self.assertEqual(response.status_code,400)
        self.credential=secrets.token_urlsafe(32)
        self.assertEqual(self.beat().status_code,401)

    def test_inactive_owner_blocked(self):
        self.claim();self.exchange();User.objects.filter(pk=self.owner.pk).update(is_active=False)
        self.assertEqual(self.beat().status_code,401)
        self.assertEqual(self.exchange().status_code,400)

    def test_heartbeat_limits_schema_and_ack(self):
        self.claim();self.exchange()
        for payload in [{'acknowledged_version':99},{'acknowledged_version':-1},
                        {'acknowledged_version':True},{'firmware_version':'secret\nlog'}, {'transport':'usb'}, {'extra':'ignored'}]:
            self.assertEqual(self.beat(**payload).status_code,400)
        self.assertEqual(self.beat(acknowledged_version=1).status_code,200)
        Device.objects.update(last_seen=timezone.now()-timedelta(seconds=31))
        self.assertEqual(self.beat().status_code,400)
        self.assertEqual(self.beat(acknowledged_version=1).status_code,200)
        self.assertEqual(self.beat(acknowledged_version=1).status_code,429)

    def test_last_seen_staleness(self):
        self.claim();self.exchange();self.beat()
        Device.objects.update(last_seen=timezone.now()-timedelta(seconds=91))
        self.device.refresh_from_db();self.assertEqual(self.device.connection_state,'Offline')

    def test_pairing_limits_and_unknown_uuid_no_bucket_growth(self):
        for _ in range(5):self.start()
        response=self.machine.post('/api/devices/v1/enroll/',{'protocol':1,'hardware_profile':PROFILE},content_type='application/json')
        self.assertEqual(response.status_code,429)
        before=DeviceRateBucket.objects.count()
        import uuid
        self.ticket['enrollment_id']=str(uuid.uuid4())
        self.assertEqual(self.exchange().status_code,400)
        self.assertEqual(DeviceRateBucket.objects.count(),before)
        for _ in range(6):self.client.post(reverse('onboarding'),{'code':'A'*12,'name':'Fixture','confirm':'on'})
        self.assertContains(self.client.post(reverse('onboarding'),{}),'Too many pairing attempts')

    def test_invalid_profile_and_oversized_request(self):
        for profile in ['raspberry-pi','esp32-c6']:
            self.assertEqual(self.machine.post('/api/devices/v1/enroll/',{'protocol':1,'hardware_profile':profile},content_type='application/json').status_code,400)
        self.assertEqual(self.machine.post('/api/devices/v1/enroll/','x'*3000,content_type='application/json').status_code,413)

    def test_capability_report_preserves_unknown_and_driver_vs_functional_states(self):
        self.claim();self.exchange()
        report={'schema':1,'flash_bytes':33554432,'psram_bytes':None,
            'display':{'width':1024,'height':600},
            'capabilities':{'display':'initialized','touch':'configured','speaker':'configured',
                'microphone':'unknown','wifi':'passed'}}
        self.assertEqual(self.beat(hardware_report=report).status_code,200)
        self.device.refresh_from_db()
        self.assertEqual(self.device.hardware_report,report)
        page=self.client.get(reverse('device_detail',args=[self.device.pk]))
        self.assertContains(page,'Driver initialized')
        self.assertContains(page,'Expected by profile')
        self.assertContains(page,'Not reported')
        self.assertContains(page,'Not checked')
        Device.objects.update(last_seen=timezone.now()-timedelta(seconds=31))
        self.assertEqual(self.beat().status_code,200)
        self.device.refresh_from_db()
        self.assertEqual(self.device.hardware_report,report)

    def test_capability_report_rejects_unbounded_or_secret_fields(self):
        from copy import deepcopy
        self.claim();self.exchange()
        report={'schema':1,'flash_bytes':None,'psram_bytes':None,'display':None,
            'capabilities':dict.fromkeys(['display','touch','speaker','microphone','wifi'],'unknown')}
        bad=[]
        for field,value in [('flash_bytes',True),('psram_bytes',2**31),('schema',True),('api_key','must-not-be-persisted')]:
            item=deepcopy(report);item[field]=value;bad.append(item)
        item=deepcopy(report);item['capabilities']['speaker']='automatic-detection-proven';bad.append(item)
        item=deepcopy(report);item['display']={'width':100000,'height':1};bad.append(item)
        for item in bad:
            self.assertEqual(self.beat(hardware_report=item).status_code,400)
        self.device.refresh_from_db();self.assertEqual(self.device.hardware_report,{})

    def test_interface_concept_is_private_and_does_not_create_devices(self):
        self.assertEqual(Client().get(reverse('interface_preview')).status_code,302)
        self.assertContains(self.client.get(reverse('interface_preview')),'Interactive concept')
        self.assertEqual(Device.objects.count(),0)

    def test_versioned_report_is_stored_without_promising_ota(self):
        from .hardware_profiles import CONTRACT, runtime_reasons
        self.claim();self.exchange()
        report={'schema':2,'compatibility':CONTRACT,'flash_bytes':33554432,'psram_bytes':33554432,
            'display':{'width':1024,'height':600},
            'capabilities':dict.fromkeys(['display','touch','speaker','microphone','wifi'],'configured')}
        response=self.beat(hardware_report=report)
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()['ota_available'])
        self.device.refresh_from_db()
        self.assertEqual(runtime_reasons(self.device),['security_unverified','c6_compatibility_unverified','recovery_unverified'])
        page=self.client.get(reverse('device_detail',args=[self.device.pk]))
        self.assertContains(page,'installed ESP32-C6 firmware still needs review')
        for field,value,reason in [('compatibility',{**CONTRACT,'profile_id':'waveshare-esp32-p4-wifi6-touch-lcd-4b'},'profile_contract_unverified'),
                                  ('psram_bytes',8*1024*1024,'psram_insufficient_or_unverified'),
                                  ('flash_bytes',16*1024*1024,'flash_capacity_mismatch')]:
            with self.subTest(field=field):
                self.device.hardware_report={**report,field:value}
                self.assertIn(reason,runtime_reasons(self.device))

    def test_versioned_report_cannot_smuggle_unbounded_fields(self):
        from .hardware_profiles import CONTRACT
        self.claim();self.exchange()
        report={'schema':2,'compatibility':CONTRACT,'flash_bytes':33554432,'psram_bytes':33554432,
            'display':None,'capabilities':dict.fromkeys(['display','touch','speaker','microphone','wifi'],'unknown')}
        for changes in [{'profile_version':True},{'profile_id':'x'*81},{'credential':'secret-fixture'}]:
            self.assertEqual(self.beat(hardware_report={**report,'compatibility':{**CONTRACT,**changes}}).status_code,400)
        self.assertEqual(self.beat(hardware_report={**report,'schema':1}).status_code,400)
        del report['compatibility']
        self.assertEqual(self.beat(hardware_report=report).status_code,400)
