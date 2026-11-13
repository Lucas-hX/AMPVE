"""Offline tests of boot selection: no port, flash write or bootloader emulation."""
import binascii
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from installation_plan import inactive_slot_mode, next_selection, partition_for_sequence, select_record


def selection(seq,state=2,index=0):
    data=bytearray(b'\xff'*8192)
    struct.pack_into('<I',data,index*4096,seq)
    struct.pack_into('<II',data,index*4096+24,state,binascii.crc32(struct.pack('<I',seq),0xFFFFFFFF)&0xFFFFFFFF)
    return data


class BootSelectionTests(unittest.TestCase):
    def test_occupied_slot_requires_confirmed_ota0_and_is_recorded_as_replacement(self):
        self.assertEqual(inactive_slot_mode(b'old-image',(9,0,2),'ota_1'),
                         'replace-confirmed-inactive-ota1')
        for current,target in [(None,'ota_1'),((8,0,2),'ota_1'),
                               ((9,0,0),'ota_1'),((9,0,1),'ota_1')]:
            with self.subTest(current=current),self.assertRaises(ValueError):
                inactive_slot_mode(b'old-image',current,target)

    def test_blank_slot_remains_allowed_for_factory_fallback(self):
        self.assertEqual(inactive_slot_mode(b'\xff'*32,None,'ota_1'),'blank')

    def test_confirmed_ota1_can_safely_target_ota0_on_the_next_upgrade(self):
        old=selection(10,index=1)
        index,new,current=next_selection(old)
        self.assertEqual((index,current),(0,(10,1,2)))
        self.assertEqual(partition_for_sequence(struct.unpack_from('<I',new)[0]),'ota_0')
        self.assertEqual(inactive_slot_mode(b'old-image',current,'ota_0'),
                         'replace-confirmed-inactive-ota0')

    def test_sequence_partition_mapping(self):
        self.assertEqual(partition_for_sequence(9),'ota_0')
        self.assertEqual(partition_for_sequence(10),'ota_1')

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

    def test_rejects_pending_unknown_and_corrupt_selection(self):
        for data in [selection(1,0),selection(1,1),selection(1,9),selection(0),b'\0'*8192,b'\xff'*4096]:
            with self.subTest(data=data[:4]),self.assertRaises(ValueError):next_selection(data)

    def test_crc_corruption_is_not_factory_fallback(self):
        data=selection(1);data[28]^=1
        with self.assertRaises(ValueError):select_record(data)

    def test_no_sequence_overflow(self):
        with self.assertRaises(ValueError):next_selection(selection(0xFFFFFFFD))
