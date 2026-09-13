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


class FirmwareDeliveryTests(TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.settings=override_settings(FIRMWARE_REVIEW_ROOT=str(self.root),FIRMWARE_RELEASE_ROOT=str(self.root/'release'),FIRMWARE_PUBLISHER_PUBLIC_KEY=str(self.root/'public'))
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

    def test_signature_required_and_verified_separately(self):
        self.client.force_login(self.user);root=self.root/'release';root.mkdir()
        key=Ed25519PrivateKey.generate()
        (self.root/'public').write_text(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex())
        payload=json.dumps({'profile':'waveshare-7b-stock-v1','installable':True,
            'expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}).encode()
        envelope={'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(key.sign(payload)).decode()}
        (root/'approved-release.json').write_text(json.dumps(envelope))
        self.assertEqual(self.client.get('/devices/firmware/release/').json()['status'],'reviewed-development-release')
        envelope['payload']=base64.b64encode(b'{}').decode()
        (root/'approved-release.json').write_text(json.dumps(envelope))
        data=self.client.get('/devices/firmware/release/').json()
        self.assertEqual(data['status'],'release-verification-failed');self.assertFalse(data['installable'])

    def test_expired_or_invalid_approval_blocks_metadata_and_artifacts(self):
        self.client.force_login(self.user)
        root=self.root/'release';root.mkdir()
        key=Ed25519PrivateKey.generate()
        (self.root/'public').write_text(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex())
        app=b'expiry fixture';digest=hashlib.sha256(app).hexdigest()
        (root/'xiaozhi.bin').write_bytes(app)
        for expiry in ['2000-01-01T00:00:00Z', '2099-01-01T00:00:00', 'invalid', None]:
            with self.subTest(expiry=expiry):
                policy={'profile':'waveshare-7b-stock-v1','installable':True,
                    'app':{'sha256':digest,'size':len(app)},'expires_at':expiry}
                payload=json.dumps(policy).encode()
                (root/'approved-release.json').write_text(json.dumps({
                    'payload':base64.b64encode(payload).decode(),
                    'signature':base64.b64encode(key.sign(payload)).decode()}))
                data=self.client.get('/devices/firmware/release/').json()
                self.assertEqual(data['status'],'release-verification-failed')
                self.assertFalse(data['installable'])
                self.assertEqual(self.client.get('/devices/firmware/artifacts/'+digest+'.bin').status_code,404)

    def test_publisher_binds_exact_app_and_refuses_reuse_or_wrong_digest(self):
        import importlib.util
        from datetime import datetime,timedelta,timezone
        from django.conf import settings
        from cryptography.hazmat.primitives.serialization import PrivateFormat,NoEncryption
        spec=importlib.util.spec_from_file_location('fixture_publisher',settings.REPO_DIR/'firmware/tools/publish_release.py')
        publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
        app=b'fixture image bytes only; not hardware firmware';digest=hashlib.sha256(app).hexdigest()
        (self.root/'xiaozhi.bin').write_bytes(app)
        (self.root/'review-manifest.json').write_text(json.dumps({'installation_profile':'waveshare-7b-stock-v1','repository_commit':'fixture',
            'proposed_regions_not_approved_writes':[{'sha256':digest,'offset':0xe00000}]}))
        review={'bootloader_sha256':'a'*64,'table_sha256':'b'*64,'app_sha256':digest,'bootloader_review':'software fixture only','c6_review':'software fixture only','recovery_review':'software fixture only','expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
        (self.root/'review.json').write_text(json.dumps(review))
        key=Ed25519PrivateKey.generate()
        (self.root/'private').write_bytes(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        output=self.root/'published-fixture'
        publisher.publish(self.root,self.root/'review.json',self.root/'private',output)
        envelope=json.loads((output/'approved-release.json').read_text())
        key.public_key().verify(base64.b64decode(envelope['signature']),base64.b64decode(envelope['payload']))
        self.assertEqual(json.loads(base64.b64decode(envelope['payload']))['app']['sha256'],digest)
        with self.assertRaises(ValueError):publisher.publish(self.root,self.root/'review.json',self.root/'private',output)
        review['app_sha256']='0'*64;(self.root/'review.json').write_text(json.dumps(review))
        with self.assertRaises(ValueError):publisher.publish(self.root,self.root/'review.json',self.root/'private',self.root/'wrong-fixture')
