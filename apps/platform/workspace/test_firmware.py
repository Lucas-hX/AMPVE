import base64
import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.test import TestCase, override_settings
from .models import User
from .hardware_profiles import CONTRACT


class FirmwareDeliveryTests(TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.settings=override_settings(FIRMWARE_REVIEW_ROOT=str(self.root),FIRMWARE_RELEASE_ROOT=str(self.root/'release'),FIRMWARE_PUBLISHER_TRUST=str(self.root/'trust.json'))
        self.settings.enable();self.addCleanup(self.settings.disable)
        self.user=User.objects.create_user(email='firmware-fixture@example.test',password='fixture-password-12345')

    def candidate(self):
        content=b'fixture app bytes';digest=hashlib.sha256(content).hexdigest()
        (self.root/'xiaozhi.bin').write_bytes(content)
        manifest={'installation_profile':'waveshare-7b-stock-v1','installable':True,
            'proposed_regions_not_approved_writes':[{'file':'xiaozhi.bin','size':len(content),'sha256':digest,'offset':0xe00000}]}
        (self.root/'review-manifest.json').write_text(json.dumps(manifest))
        return digest

    def test_authenticated_read_only_delivery(self):
        digest=self.candidate()
        self.assertEqual(self.client.get('/devices/firmware/release/').status_code,302)
        self.assertEqual(self.client.get('/devices/firmware/artifacts/'+digest+'.bin').status_code,302)
        self.client.force_login(self.user)
        data=self.client.get('/devices/firmware/release/').json()
        self.assertFalse(data['installable'])  # A candidate cannot self-approve.
        self.assertNotIn('envelope',data)
        response=self.client.get('/devices/firmware/artifacts/'+digest+'.bin')
        self.assertEqual(response.status_code,200)
        self.assertEqual(b''.join(response.streaming_content),b'fixture app bytes')
        self.assertEqual(self.client.post('/devices/firmware/release/',b'private dump',content_type='application/octet-stream').status_code,405)
        self.assertEqual(self.client.get('/devices/firmware/artifacts/backup-a.bin').status_code,404)

    def test_corrupt_artifact_not_served(self):
        digest=self.candidate();self.client.force_login(self.user)
        (self.root/'xiaozhi.bin').write_bytes(b'changed')
        self.assertEqual(self.client.get('/devices/firmware/artifacts/'+digest+'.bin').status_code,404)

    def approved(self, **changes):
        from django.conf import settings
        from .release_contract import canonical
        self.client.force_login(self.user)
        root=self.root/'release';root.mkdir(exist_ok=True)
        self.key=Ed25519PrivateKey.generate()
        self.trust={'schema':1,'minimum_sequence':1,'revoked_releases':[],
            'keys':{'fixture-key':{'public_key':self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),
                     'channels':['development'],'purposes':['initial-install','ota'],'revoked':False}}}
        (self.root/'trust.json').write_text(json.dumps(self.trust))
        self.policy=json.loads((settings.REPO_DIR/'tests/fixtures/initial-release-v2.json').read_text())
        app=b'fixture-only-app'.ljust(4096,b'0');archive=b'fixture provenance archive'
        (root/'xiaozhi.bin').write_bytes(app);(root/'review.zip').write_bytes(archive)
        self.policy['app']['sha256']=hashlib.sha256(app).hexdigest()
        self.policy['provenance']['archive_sha256']=hashlib.sha256(archive).hexdigest()
        self.policy.update(changes)
        payload=canonical(self.policy)
        self.envelope={'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(self.key.sign(payload)).decode()}
        (root/'approved-release.json').write_text(json.dumps(self.envelope))
        self.release_id=hashlib.sha256(payload).hexdigest()
        return root

    def assert_blocked(self):
        data=self.client.get('/devices/firmware/release/').json()
        self.assertEqual(data['status'],'release-verification-failed')
        self.assertFalse(data['installable'])
        self.assertEqual(self.client.get('/devices/firmware/artifacts/'+self.policy['app']['sha256']+'.bin').status_code,404)

    def test_signature_identity_and_provenance_verified(self):
        root=self.approved()
        data=self.client.get('/devices/firmware/release/').json()
        self.assertEqual(data['status'],'reviewed-development-release')
        self.assertEqual(data['release_id'],self.release_id)
        self.assertEqual(data['minimum_sequence'],1)
        response=self.client.get('/devices/firmware/artifacts/'+self.policy['app']['sha256']+'.bin')
        self.assertEqual(response.status_code,200);b''.join(response.streaming_content)
        (root/'review.zip').write_bytes(b'changed provenance')
        self.assert_blocked()

    def test_tamper_wrong_key_and_missing_trust_block(self):
        root=self.approved()
        self.envelope['payload']=base64.b64encode(b'{}').decode()
        (root/'approved-release.json').write_text(json.dumps(self.envelope))
        self.assert_blocked()
        self.approved()
        self.trust['keys']['fixture-key']['public_key']='0'*64
        (self.root/'trust.json').write_text(json.dumps(self.trust));self.assert_blocked()
        (self.root/'trust.json').unlink();self.assert_blocked()

    def test_expiry_and_invalid_signed_policy_block(self):
        cases=[{'expires_at':v} for v in ['2000-01-01T00:00:00Z','2099-01-01T00:00:00','invalid',None]]
        cases += [{'compatibility':v} for v in [None,{**CONTRACT,'profile_id':'waveshare-esp32-p4-wifi6-touch-lcd-4b'},
                  {**CONTRACT,'profile_version':True},{**CONTRACT,'profile_version':2},{**CONTRACT,'layout_id':'other-layout'}]]
        cases += [{'schema':1},{'sequence':True},{'sequence':0},{'channel':'stable'}, {'c6_review':''},
                  {'extra':'not-allowed'},{'repository_commit':'moving-main'},{'flash_bytes':8388608}]
        for change in cases:
            with self.subTest(change=change):
                self.approved(**change);self.assert_blocked()

    def test_key_release_revocation_and_sequence_floor_stop_new_downloads(self):
        for change in ['key','release','floor','scope']:
            with self.subTest(change=change):
                self.approved()
                if change=='key':self.trust['keys']['fixture-key']['revoked']=True
                if change=='release':self.trust['revoked_releases']=[self.release_id]
                if change=='floor':self.trust['minimum_sequence']=8
                if change=='scope':self.trust['keys']['fixture-key']['purposes']=['ota']
                (self.root/'trust.json').write_text(json.dumps(self.trust));self.assert_blocked()

    def test_ota_release_is_not_a_usb_installation(self):
        self.approved()
        app={key:value for key,value in self.policy['app'].items() if key!='offset'}
        self.approved(purpose='ota',installable=False,app=app,ota_review='Software fixture only',from_app_sha256=['a'*64])
        data=self.client.get('/devices/firmware/release/').json()
        self.assertEqual(data['status'],'ota-release-only')
        self.assertFalse(data['installable'])
        self.assertEqual(self.client.get('/devices/firmware/artifacts/'+app['sha256']+'.bin').status_code,404)
