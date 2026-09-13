"""Signed software fixtures only. Run with the pinned firmware-tools Python."""
import base64
import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from artifact_archive import archive_tree
from profile_contract import CONTRACT
from publish_release import publish
from workspace.release_contract import canonical, eligible_upgrade, strict_json, validate_policy, verify_envelope, read_release
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.candidate=self.root/'candidate';self.candidate.mkdir()
        app=bytearray(304);app[0]=0xe9;app[1]=1;app[23]=1
        struct.pack_into('<H',app,12,18);struct.pack_into('<HH',app,15,100,199)
        struct.pack_into('<II',app,24,0x4ff00000,256)
        struct.pack_into('<I',app,32,0xabcd5432);app[48:59]=b'fixture-0.1'
        checksum=0xef
        for byte in app[32:288]:checksum^=byte
        app[303]=checksum;app+=hashlib.sha256(app).digest()
        self.app=bytes(app);digest=hashlib.sha256(app).hexdigest()
        for name,content in {'xiaozhi.bin':app,'sdkconfig':b'config fixture','dependencies.lock':b'lock fixture',
                             'LICENSE.xiaozhi':b'fixture notice','provisioning-component/LICENSE':b'fixture notice'}.items():
            path=self.candidate/name;path.parent.mkdir(exist_ok=True);path.write_bytes(content)
        manifest={'installable':False,'installation_profile':'waveshare-7b-stock-v1','compatibility':CONTRACT,
            'repository_commit':'1'*40,'firmware_version':'fixture-0.1','xiaozhi_commit':'2'*40,'esp_idf_commit':'3'*40,
            'sdkconfig_sha256':hashlib.sha256(b'config fixture').hexdigest(),
            'dependency_lock_sha256':hashlib.sha256(b'lock fixture').hexdigest(),
            'bit_reproducibility':{'verified':True,'scope':'Software fixture only'},
            'proposed_regions_not_approved_writes':[{'sha256':digest,'offset':0xe00000}]}
        (self.candidate/'review-manifest.json').write_bytes(canonical(manifest))
        archive_tree(self.candidate,self.root/'candidate.zip')
        self.review=json.loads((ROOT/'tests/fixtures/initial-release-v2.json').read_text())
        self.review={key:self.review[key] for key in ('key_id','sequence','channel','purpose','bootloader_sha256',
                     'table_sha256','bootloader_review','c6_review','recovery_review')}
        self.review.update(app_sha256=digest,expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.key=Ed25519PrivateKey.generate()
        (self.root/'private.key').write_bytes(self.key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
        self.trust={'schema':1,'keys':{'fixture-key':{'public_key':self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),
                    'channels':['development'],'purposes':['initial-install','ota'],'revoked':False}},'minimum_sequence':1,'revoked_releases':[]}
        self.bind_build_sequence(self.review['sequence'])

    def bind_build_sequence(self,sequence):
        from native_trust import generate
        config={'schema':1,'build_sequence':sequence,'trust':self.trust}
        header,public=generate(config=config)
        (self.candidate/'native-public-trust.json').write_bytes(public)
        (self.candidate/'publisher_trust.h').write_text(header)
        path=self.candidate/'review-manifest.json';manifest=json.loads(path.read_bytes())
        manifest.update(native_build_sequence=sequence,native_ota_testing_only=False,native_public_trust_sha256=hashlib.sha256(public).hexdigest(),
            generated_inputs={'main/ampve/publisher_trust.h':hashlib.sha256(header.encode()).hexdigest()})
        path.write_bytes(canonical(manifest));(self.root/'candidate.zip').unlink()
        archive_tree(self.candidate,self.root/'candidate.zip')

    def run_publish(self,name='release'):
        (self.root/'review.json').write_bytes(canonical(self.review))
        output=self.root/name
        policy=publish(self.candidate,self.root/'review.json',self.root/'private.key',output,self.root/'publisher-ledger.sqlite3')
        # Read-only published directories need owner permissions restored for fixture cleanup.
        self.addCleanup(lambda: output.chmod(0o700) if output.exists() else None)
        return policy,output

    def test_signed_identity_artifacts_and_immutable_output(self):
        policy,output=self.run_publish()
        envelope=strict_json((output/'approved-release.json').read_bytes())
        verified,release_id,_=verify_envelope(envelope,self.trust)
        self.assertEqual(verified,policy)
        self.assertEqual(release_id,hashlib.sha256(canonical(policy)).hexdigest())
        self.assertEqual((output/'xiaozhi.bin').read_bytes(),self.app)
        self.assertEqual((output/'review.zip').read_bytes(),(self.root/'candidate.zip').read_bytes())
        self.assertEqual(output.stat().st_mode & 0o222,0)
        trust_path=self.root/'trust.json';trust_path.write_bytes(canonical(self.trust))
        self.assertEqual(read_release(output,trust_path)[1],release_id)
        with self.assertRaises(FileExistsError):self.run_publish()

    def test_corruption_or_missing_evidence_never_publishes(self):
        (self.candidate/'xiaozhi.bin').write_bytes(self.app[:-1]+b'!')
        with self.assertRaises(ValueError):self.run_publish()
        self.assertFalse((self.root/'release').exists())
        (self.candidate/'xiaozhi.bin').write_bytes(self.app)
        self.review['app_sha256']='0'*64
        with self.assertRaises(ValueError):self.run_publish()
        self.review['app_sha256']=hashlib.sha256(self.app).hexdigest()
        (self.root/'candidate.zip').write_bytes(b'not the review archive')
        with self.assertRaises(zipfile.BadZipFile):self.run_publish()
        self.assertFalse((self.root/'release').exists())

    def test_ota_requires_predecessors_and_cannot_be_used_for_usb(self):
        self.review.update(purpose='ota',ota_review='Explicit software fixture, not physical recovery',from_app_sha256=['a'*64])
        policy,output=self.run_publish()
        self.assertNotIn('offset',policy['app'])
        self.assertFalse(policy['installable'])
        self.assertFalse((output/'esp-web-tools-reference.json').exists())
        self.assertTrue(eligible_upgrade(policy,6,'a'*64))
        for old_sequence,old_hash in [(7,'a'*64),(8,'a'*64),(True,'a'*64),(6,'b'*64)]:
            self.assertFalse(eligible_upgrade(policy,old_sequence,old_hash))
        for previous in [[],[policy['app']['sha256']],['a'*64,'a'*64]]:
            with self.assertRaises(ValueError):validate_policy({**policy,'from_app_sha256':previous})

    def test_archive_bytes_ignore_mtime_and_creation_order(self):
        original=(self.root/'candidate.zip').read_bytes()
        for path in self.candidate.rglob('*'):
            os.utime(path,(1700000000,1700000000))
        archive_tree(self.candidate,self.root/'repeat.zip')
        self.assertEqual(original,(self.root/'repeat.zip').read_bytes())

    def test_sequence_cannot_be_reused_or_downgraded_in_a_new_directory(self):
        self.run_publish()
        for number in (7,6):
            self.review['sequence']=number
            with self.assertRaises(ValueError):self.run_publish('another-release')
            self.assertFalse((self.root/'another-release').exists())
        self.review['sequence']=8
        self.bind_build_sequence(8)
        self.run_publish('next-release')

    def test_native_sequence_and_header_must_match_the_reviewed_build(self):
        self.review['sequence']=8
        with self.assertRaises(ValueError):self.run_publish()
        self.review['sequence']=7
        (self.candidate/'publisher_trust.h').write_text('changed')
        with self.assertRaises(ValueError):self.run_publish()
        self.assertFalse((self.root/'release').exists())

    def test_enabled_software_build_fixture_cannot_be_promoted(self):
        from native_trust import generate
        header,public=generate(config={'schema':1,'build_sequence':7,'testing_only':True,'trust':self.trust})
        (self.candidate/'native-public-trust.json').write_bytes(public)
        (self.candidate/'publisher_trust.h').write_text(header)
        path=self.candidate/'review-manifest.json';manifest=json.loads(path.read_bytes())
        manifest.update(native_ota_testing_only=True,native_public_trust_sha256=hashlib.sha256(public).hexdigest(),
            generated_inputs={'main/ampve/publisher_trust.h':hashlib.sha256(header.encode()).hexdigest()})
        path.write_bytes(canonical(manifest));(self.root/'candidate.zip').unlink()
        archive_tree(self.candidate,self.root/'candidate.zip')
        with self.assertRaisesRegex(ValueError,'fixture builds cannot be promoted'):self.run_publish()
        self.assertFalse((self.root/'release').exists())

    def test_concurrent_publishers_cannot_reserve_the_same_sequence(self):
        from concurrent.futures import ThreadPoolExecutor
        (self.root/'review.json').write_bytes(canonical(self.review))
        def attempt(name):
            output=self.root/name
            try:
                publish(self.candidate,self.root/'review.json',self.root/'private.key',output,self.root/'publisher-ledger.sqlite3')
                return 'published'
            except ValueError:
                return 'rejected'
            finally:
                if output.exists():output.chmod(0o700)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,['first','second']))
        self.assertEqual(sorted(results),['published','rejected'])

    def test_noncanonical_duplicate_or_nonfinite_metadata_refused(self):
        for raw in (b'{"schema":1,"schema":2}',b'{"value":NaN}'):
            with self.assertRaises(ValueError):strict_json(raw)
        policy,_=self.run_publish()
        payload=json.dumps(policy,indent=2).encode()
        envelope={'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(self.key.sign(payload)).decode()}
        with self.assertRaises(ValueError):verify_envelope(envelope,self.trust)
