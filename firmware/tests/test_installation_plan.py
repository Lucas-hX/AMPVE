"""Offline tests of boot selection: no port, flash write or bootloader emulation."""
import binascii
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from installation_plan import next_selection, select_record


def selection(seq,state=2,index=0):
    data=bytearray(b'\xff'*8192)
    struct.pack_into('<I',data,index*4096,seq)
    struct.pack_into('<II',data,index*4096+24,state,binascii.crc32(struct.pack('<I',seq),0xFFFFFFFF)&0xFFFFFFFF)
    return data


class BootSelectionTests(unittest.TestCase):
    def test_retains_valid_stock_record_and_changes_other_sector(self):
        old=selection(5)
        index,new,current=next_selection(old)
        self.assertEqual((index,current),(1,(5,0,2)))
        self.assertEqual(struct.unpack_from('<I',new)[0],6)
        self.assertEqual(struct.unpack_from('<I',new,24)[0],0)
        self.assertEqual(old[:4096],selection(5)[:4096])
        self.assertEqual(new[32:],old[4096+32:])

    def test_factory_blank_selection_targets_ota1(self):
        index,new,current=next_selection(b'\xff'*8192)
        self.assertIsNone(current)
        self.assertEqual(index,0)
        self.assertEqual(struct.unpack_from('<I',new)[0],2)
        self.assertEqual(struct.unpack_from('<I',new,28)[0],binascii.crc32(struct.pack('<I',2),0xFFFFFFFF)&0xFFFFFFFF)

    def test_rejects_target_active_pending_unknown_and_corrupt(self):
        for data in [selection(2),selection(1,0),selection(1,1),selection(1,9),selection(0),b'\0'*8192,b'\xff'*4096]:
            with self.subTest(data=data[:4]),self.assertRaises(ValueError):next_selection(data)

    def test_crc_corruption_is_not_factory_fallback(self):
        data=selection(1);data[28]^=1
        with self.assertRaises(ValueError):select_record(data)

    def test_no_sequence_overflow(self):
        with self.assertRaises(ValueError):next_selection(selection(0xFFFFFFFD))
