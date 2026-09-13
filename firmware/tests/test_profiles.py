"""Contract consistency fixtures; no hardware detection or physical write evidence."""
import csv
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'firmware/tools'))
from profile_contract import CONTRACT, PROFILE, matches_contract, matches_layout, native_header


class ProfileContractTests(unittest.TestCase):
    def test_checked_in_csv_matches_every_canonical_entry(self):
        rows = []
        aliases = {'app':0, 'data':1, 'nvs':2, 'ota':0, 'phy':1,
                   'factory':0, 'ota_0':16, 'ota_1':17, 'spiffs':130}
        lines = (ROOT/'firmware/xiaozhi/partitions/7b-stock-v1.csv').read_text().splitlines()
        for row in csv.reader(line for line in lines if not line.startswith('#')):
            name, kind, subtype, offset, size, flags = (part.strip() for part in row)
            rows.append(dict(name=name,type=aliases[kind],subtype=aliases[subtype],
                offset=int(offset,0),size=int(size,0),flags=int(flags or '0',0)))
        self.assertTrue(matches_layout(rows, 0x8000))
        altered=deepcopy(rows);altered[6]['size']+=4096
        self.assertFalse(matches_layout(altered,0x8000))
        self.assertFalse(matches_layout(rows,0x9000))
        self.assertFalse(matches_layout(rows[:-1],0x8000))

    def test_same_chip_family_is_not_a_matching_board(self):
        other={**CONTRACT,'profile_id':'waveshare-esp32-p4-wifi6-touch-lcd-4b'}
        self.assertFalse(matches_contract(other))
        for changes in ({'profile_version':True},{'profile_version':2},
                        {'layout_id':'replacement-layout'},{'firmware_lineage':'stock-xiaozhi'},
                        {'usb_vid':0x1a86}):
            self.assertFalse(matches_contract({**CONTRACT,**changes}))
        self.assertTrue(matches_contract(CONTRACT))
        self.assertFalse(matches_contract(None))

    def test_native_constants_and_source_identity_remain_bound(self):
        upstream=json.loads((ROOT/'firmware/xiaozhi/upstream.json').read_text())
        self.assertEqual(PROFILE['source']['commit'],upstream['commit'])
        self.assertEqual(PROFILE['id'],upstream['hardware_profile'])
        header=native_header()
        self.assertIn('AMPVE_MIN_PSRAM_BYTES 33554432',header)
        self.assertIn('static_assert(DISPLAY_WIDTH == 1024',header)
        self.assertIn('static_assert(CONFIG_ESP_HOSTED_SDIO_PIN_CMD == 19',header)
        self.assertEqual(PROFILE['connectivity']['compatibility'],'unverified')
        self.assertEqual(PROFILE['recovery']['stock_bootloader_rollback'],'unverified')
