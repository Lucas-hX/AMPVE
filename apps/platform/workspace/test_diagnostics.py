import hashlib
import json
import tempfile
from pathlib import Path
from django.test import TestCase, override_settings
from .models import User


class DiagnosticDeliveryTests(TestCase):
    def test_curated_ram_probe_requires_login_and_rechecks_bytes(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(C6_PROBE_ROOT=directory):
            root=Path(directory);data=b'RAM diagnostic fixture only'.ljust(32,b'0')
            manifest={'schema':1,'kind':'ampve-c6-ram-probe','chip_revision':103,'flash_writes':False,
                      'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            (root/'manifest.json').write_text(json.dumps(manifest));(root/'probe.bin').write_bytes(data)
            self.assertEqual(self.client.get('/devices/diagnostics/c6/').status_code,302)
            self.client.force_login(User.objects.create_user(email='diagnostic-fixture@example.test',password='fixture-password-12345'))
            self.assertEqual(self.client.get('/devices/diagnostics/c6/').json(),manifest)
            self.assertEqual(self.client.get('/devices/diagnostics/c6/?artifact=1').content,data)
            self.assertEqual(self.client.post('/devices/diagnostics/c6/',{}).status_code,405)
            (root/'probe.bin').write_bytes(b'0'*len(data))
            self.assertEqual(self.client.get('/devices/diagnostics/c6/?artifact=1').status_code,404)
            (root/'probe.bin').write_bytes(data)
            for changed in [{**manifest,'flash_writes':True},{**manifest,'chip_revision':300},{**manifest,'size':True},[]]:
                (root/'manifest.json').write_text(json.dumps(changed))
                self.assertEqual(self.client.get('/devices/diagnostics/c6/').status_code,404)
