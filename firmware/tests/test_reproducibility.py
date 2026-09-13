"""Synthetic directory/hash failures; these fixtures do not invoke a compiler."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'firmware/tools'))
from reproducibility import compare

class ReproductionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.a=self.base/'a';self.b=self.base/'b'
        for root in [self.a,self.b]:
            (root/'build').mkdir(parents=True)
            (root/'build/CMakeCache.txt').write_text('CMAKE_HOME_DIRECTORY:INTERNAL='+str(root)+'\n')
            (root/'build/app.bin').write_bytes(b'synthetic fixture')
        self.items=[{'file':'app.bin','sha256':hashlib.sha256(b'synthetic fixture').hexdigest()}]
    def test_distinct_matching_artifacts(self):
        result=compare(self.a,self.b,self.items)
        self.assertTrue(result['verified']);self.assertIn('do not prove compiler execution',result['scope'])
    def test_same_directory_and_alias(self):
        alias=self.base/'alias';alias.symlink_to(self.a,target_is_directory=True)
        for target in [self.a,alias,self.a/'nested']:
            with self.assertRaisesRegex(ValueError,'separate'):compare(self.a,target,self.items)
    def test_wrong_source_configuration(self):
        (self.b/'build/CMakeCache.txt').write_text('CMAKE_HOME_DIRECTORY:INTERNAL='+str(self.a)+'\n')
        with self.assertRaisesRegex(ValueError,'different source'):compare(self.a,self.b,self.items)
    def test_shared_file_and_external_symlink(self):
        file=self.b/'build/app.bin';file.unlink();os.link(self.a/'build/app.bin',file)
        with self.assertRaisesRegex(ValueError,'same file'):compare(self.a,self.b,self.items)
        file.unlink();file.symlink_to(self.a/'build/app.bin')
        with self.assertRaisesRegex(ValueError,'outside'):compare(self.a,self.b,self.items)
    def test_corruption_in_either_build(self):
        for root in [self.a,self.b]:
            file=root/'build/app.bin';file.write_bytes(b'corruption')
            with self.assertRaisesRegex(ValueError,'mismatch'):compare(self.a,self.b,self.items)
            file.write_bytes(b'synthetic fixture')
    def test_missing_and_unsafe_inputs(self):
        for items in [[],self.items*2,[{'file':'../app.bin','sha256':'x'}],[{'file':'missing.bin','sha256':'x'}]]:
            with self.assertRaises(ValueError):compare(self.a,self.b,items)
        (self.b/'build/CMakeCache.txt').unlink()
        with self.assertRaisesRegex(ValueError,'Missing CMake'):compare(self.a,self.b,self.items)
