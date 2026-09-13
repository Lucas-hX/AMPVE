"""Synthetic bytes only: safety checks must fail closed before hardware access."""
import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from audit import analyze, partition_table, private_directory, security_is_unprotected


def entry(offset=0x10000, size=0x100000, name=b'factory'):
    return struct.pack('<HBBII16sI', 0x50AA, 0, 0, offset, size, name, 0)


def table(entries):
    return entries+b'\xeb\xeb'+b'\xff'*14+hashlib.md5(entries).digest()


def flash(entries=None):
    data = bytearray(b'\xff'*(2*1024*1024))
    block = table(entries or entry())
    data[0x8000:0x8000+len(block)] = block
    return data


class AuditSafetyTests(unittest.TestCase):
    def test_valid_table_is_not_installation_approval(self):
        report = analyze(flash())
        self.assertEqual(report['partition_table_offset'], 0x8000)
        self.assertFalse(report['installable'])

    def test_corrupt_md5_rejected(self):
        data = flash(); data[0x8030] ^= 1
        with self.assertRaises(ValueError): analyze(data)

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError): analyze(flash(entry()+entry(0x20000, name=b'ota_0')))

    def test_outside_flash_rejected(self):
        with self.assertRaises(ValueError): analyze(flash(entry(size=0x200000)))

    def test_partial_dump_rejected(self):
        with self.assertRaises(ValueError): analyze(flash()[:-1])

    def test_ambiguous_tables_rejected(self):
        data = flash(); second = table(entry())
        data[0x9000:0x9000+len(second)] = second
        with self.assertRaises(ValueError): analyze(data)

    def test_security_unknown_or_enabled_rejected(self):
        self.assertFalse(security_is_unprotected({}))
        info = {'flash_crypt_cnt': 0, 'parsed_flags': {'SECURE_BOOT_EN': False,
                'SECURE_DOWNLOAD_ENABLE': False, 'SECURE_BOOT_AGGRESSIVE_REVOKE': False}}
        self.assertTrue(security_is_unprotected(info))
        info['flash_crypt_cnt'] = 1
        self.assertFalse(security_is_unprotected(info))

    def test_private_output_cannot_be_in_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'.git').mkdir()
            with self.assertRaises(ValueError): private_directory(root/'private')


class ReleaseGateTests(unittest.TestCase):
    def test_security_and_shared_asset_config_rejected(self):
        from release import validate_config
        good = {'CONFIG_IDF_TARGET': '"esp32p4"', 'CONFIG_ESP32P4_REV_MIN_FULL': '100',
                'CONFIG_ESP32P4_REV_MAX_FULL': '199', 'CONFIG_ESPTOOLPY_FLASHSIZE': '"32MB"',
                'CONFIG_BOARD_TYPE_WAVESHARE_ESP32_P4_WIFI6_TOUCH_LCD_7B': 'y',
                'CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE': 'y', 'CONFIG_FLASH_NONE_ASSETS': 'y',
                'CONFIG_LANGUAGE_EN_US': 'y', 'CONFIG_APP_REPRODUCIBLE_BUILD': 'y'}
        validate_config(good)
        for key in ['CONFIG_SECURE_BOOT', 'CONFIG_SECURE_FLASH_ENC_ENABLED',
                    'CONFIG_BOOTLOADER_APP_ANTI_ROLLBACK', 'CONFIG_APP_COMPILE_TIME_DATE',
                      'CONFIG_LIBSODIUM_USE_MBEDTLS_SHA']:
            with self.subTest(key=key), self.assertRaises(ValueError): validate_config({**good, key: 'y'})
        with self.assertRaises(ValueError): validate_config({**good, 'CONFIG_FLASH_NONE_ASSETS': 'n'})

if __name__ == '__main__': unittest.main()
