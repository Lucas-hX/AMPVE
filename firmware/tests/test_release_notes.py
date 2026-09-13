"""Bounded note parsing fixtures; signature/archive binding is tested by the publisher suite."""
from io import BytesIO
from pathlib import Path
import sys
import unittest
import warnings
import zipfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/platform'))
from workspace.release_notes import archived_notes,decode_notes,MAX_BYTES,NAME

def archive(entries):
    output=BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
            for name,data in entries:bundle.writestr(name,data)
    return output.getvalue()

class NoteTests(unittest.TestCase):
    def test_plain_unicode_multiline_and_absent_notes(self):
        raw='Fixture changes\nWi-Fi café <literal>\n'.encode()
        self.assertEqual(archived_notes(archive([(NAME,raw)])),raw.decode())
        self.assertIsNone(archived_notes(archive([('other.txt',raw)])))
    def test_byte_bounds_and_invalid_text(self):
        self.assertEqual(len(decode_notes(b'x'*MAX_BYTES)),MAX_BYTES)
        for raw in [b'',b'   ',b'x'*(MAX_BYTES+1),b'a\x00b',b'\xff',b'a\x1bb']:
            with self.subTest(raw_length=len(raw)),self.assertRaises(ValueError):decode_notes(raw)
    def test_archive_bounds_duplicates_and_fixed_member_path(self):
        for entries in [[(NAME,b'x'*(MAX_BYTES+1))],[(NAME,b'a'),(NAME,b'b')]]:
            with self.assertRaises(ValueError):archived_notes(archive(entries))
        self.assertIsNone(archived_notes(archive([('../'+NAME,b'ignored')])))
