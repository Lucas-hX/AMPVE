"""Exercise capture sequencing with a strict read-only fake, never a serial device."""
import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from audit import capture
from test_audit import flash


class CaptureTests(unittest.TestCase):
    def fake(self, protected=False):
        esp = types.SimpleNamespace(CHIP_NAME='ESP32-P4', _port=types.SimpleNamespace(close=Mock()),
            get_chip_revision=lambda: 103, flash_id=lambda: 0x190000,
            get_security_info=lambda: {'flash_crypt_cnt': 0, 'parsed_flags': {
                'SECURE_BOOT_EN': protected, 'SECURE_DOWNLOAD_ENABLE': False, 'SECURE_BOOT_AGGRESSIVE_REVOKE': False}},
            change_baud=Mock())
        calls = []
        def attach(device): self.assertIs(device, esp); calls.append('attach')
        def read(device, address, size, output, **kwargs):
            self.assertIn('attach', calls); self.assertEqual(address, 0); self.assertEqual(size, 32*1024*1024)
            data = flash()+b'\xff'*(30*1024*1024)
            Path(output).write_bytes(data); calls.append('read')
        cmds = types.SimpleNamespace(detect_chip=lambda **kwargs: esp, attach_flash=attach,
                                     read_flash=read, run_stub=lambda device: device)
        return esp, calls, types.SimpleNamespace(__version__='5.4.0', cmds=cmds)

    def test_matching_reads_close_port_and_preserve_non_installable_state(self):
        esp, calls, module = self.fake()
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'esptool': module}), contextlib.redirect_stdout(io.StringIO()):
            output = Path(folder)/'audit'; capture('FIXTURE', output, 115200, True)
            self.assertEqual(calls, ['attach', 'attach', 'read', 'read'])
            report = json.loads((output/'audit-private.json').read_text())
            self.assertFalse(report['installable']); self.assertTrue(report['independent_reads_match'])
        esp._port.close.assert_called_once()

    def test_security_failure_prevents_all_flash_operations(self):
        esp, calls, module = self.fake(True)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'esptool': module}):
            with self.assertRaises(ValueError): capture('FIXTURE', Path(folder)/'audit', 115200, False)
        self.assertEqual(calls, []); esp._port.close.assert_called_once()


if __name__ == '__main__': unittest.main()
